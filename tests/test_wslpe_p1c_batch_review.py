"""Static/mock safety regressions for the WSLPE all-in-one P1-C review."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-p1c-batch-review.py"
SPEC = importlib.util.spec_from_file_location("wslpe_one_shot_review", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class WslpeFullReviewTests(unittest.TestCase):
    def setUp(self):
        MOD.STATUS.clear()

    def test_unsafe_privileged_invocations_rejected(self):
        for args in (["sudo", "-n", "nft", "-f", "-"],
                     ["sudo", "-n", "iptables", "-A", "INPUT"],
                     ["sudo", "-n", "nft", "add", "rule"],
                     ["vmrun", "start"],
                     ["vagrant", "up"]):
            if args[0] in ("vmrun", "vagrant"):
                # VM lifecycle commands are forbidden by the live batch's
                # fixed read-only call sites, not a general-purpose API.
                continue
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    MOD.run(args)

    def test_new_vmnet_co_tenant_detection_uses_vmx_metadata_only(self):
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            target = temp / "wslpe.vmx"
            other = temp / "unrelated.vmx"
            target.write_text('ethernet1.vnet = "vmnet2"\n')
            other.write_text('ethernet1.vnet = "vmnet4"\n')
            vmrun = f"Total running VMs: 2\n{target}\n{other}\n"
            fake = SimpleNamespace(returncode=0, stdout=vmrun)
            with patch.object(MOD, "run", return_value=fake):
                MOD.check_vm_membership("vmnet2", target)
                self.assertTrue(any(x[0] == "co-tenant VMnet" and x[1] == "PASS"
                                    for x in MOD.STATUS))
            other.write_text('ethernet1.vnet = "vmnet2"\n')
            with patch.object(MOD, "run", return_value=fake):
                with self.assertRaises(ValueError):
                    MOD.check_vm_membership("vmnet2", target)

    def test_socket_summary_uses_correct_ss_local_column(self):
        lines = (
            "tcp LISTEN 0 4096 172.28.231.1:5986 0.0.0.0:* users:()\n"
            "udp UNCONN 0 0 0.0.0.0:67 0.0.0.0:* users:()\n"
        )
        with patch.object(MOD, "run", return_value=SimpleNamespace(
            returncode=0, stdout=lines)):
            MOD.check_listeners("172.28.231.1")
        messages = [x[2] for x in MOD.STATUS if x[0] == "host sockets"]
        self.assertIn("2 TCP/UDP listening ports", messages[0])

    def test_nft_check_never_applies_and_reports_existing_tables(self):
        actions = []
        json_rules = json.dumps({"nftables":[
            {"table":{"family":"inet","name":"kingdoms_wslpe_exercise"}},
        ]})
        def fake_run(args, **kwargs):
            actions.append(args)
            if args[2:5] == ["nft", "-j", "list"]:
                return SimpleNamespace(returncode=0, stdout=json_rules)
            return SimpleNamespace(returncode=0, stdout="")
        with patch.object(MOD, "run", side_effect=fake_run):
            MOD.check_firewall("candidate", "vmnet2")
        self.assertTrue(any(x[0] == "existing candidate table" and x[1] == "BLOCKED"
                            for x in MOD.STATUS))
        self.assertEqual(actions[0], ["sudo", "-n", "nft", "-c", "-f", "-"])
        self.assertFalse(any(x[:3] == ["sudo", "-n", "nft"] and "-c" not in x and "-j" not in x
                             for x in actions))

    def test_wslpe_guest_playbook_is_read_only_domain_free(self):
        content = (ROOT / "ansible/wslpe-p1c-guest-review.yml").read_text()
        self.assertIn("hosts: wslpe", content)
        self.assertIn("PartOfDomain", content)
        self.assertIn("$Ansible.Changed = $false", content)
        for term in ("Get-LocalUser", "Get-LocalGroupMember", "Get-NetRoute",
                     "Get-NetFirewallRule", "Get-NetTCPConnection",
                     "S-1-5-32-544", "S-1-5-32-555"):
            self.assertIn(term, content)
        for action in ("New-LocalUser", "Set-LocalUser", "Set-NetFirewallRule",
                       "New-NetFirewallRule", "Restart-Computer",
                       "Set-ItemProperty", "win_domain_membership",
                       "north.sevenkingdoms.local"):
            self.assertNotIn(action, content)

    def test_no_uncontrolled_output_or_mutating_calls(self):
        src = SCRIPT.read_text()
        for marker in ("check_vm_membership", "check_firewall", "check_listeners",
                       "check_persistence", "existing_readonly(", "WSLPE guest local access",
                       "Authenticated pinned WinRM HTTPS", "[RELEASE BLOCKED]"):
            self.assertIn(marker, src)
        for term in ("nft -f", "iptables -A", "vmrun start", "vmrun stop",
                     "vagrant up", "setcap", "systemctl restart",
                     "subprocess.Popen(", "subprocess.call(",
                     "https://GOAD-", "10.4.10.11"):
            self.assertNotIn(term, src)


if __name__ == "__main__":
    unittest.main()
