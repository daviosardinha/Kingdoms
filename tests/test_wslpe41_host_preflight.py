"""WSLPE41 host-plan regression tests: all host probes mocked, no guest writes."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kingdoms import wslpe41_host_preflight as host


VMNET = """answer VNET_2_HOSTONLY_SUBNET 172.28.231.0
answer VNET_2_HOSTONLY_NETMASK 255.255.255.0
answer VNET_10_HOSTONLY_SUBNET 10.4.10.0
answer VNET_10_HOSTONLY_NETMASK 255.255.255.0
"""


class HostReadOnlyPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.vmnet = self.root / "networking"
        self.vmnet.write_text(VMNET, encoding="utf-8")

    def add_instance(self, name, prefix):
        instance = self.workspace / name
        instance.mkdir()
        (instance / "instance.json").write_text(
            json.dumps({"lab": "WSLPE", "ip_range": prefix}), encoding="utf-8")

    def test_live_plan_skips_vmnet_vpn_route_and_stopped_native_guest(self):
        self.add_instance("wslpe-registered-stopped", "172.28.234")
        addresses = [{"ifname": "tun0", "addr_info": [
            {"family": "inet", "local": "172.28.232.254", "prefixlen": 24}]}]
        routes = [{"dst": "172.28.233.0/24", "dev": "tun0"}]
        with patch.object(host, "ipv4_json", side_effect=[addresses, routes]) as ip_probe, \
             patch.object(host, "read_only_command", return_value="Total running VMs: 2\n/one.vmx\n/two.vmx\n") as vmrun:
            result = host.host_plan(
                workspaces=(self.workspace,), vmware_networking=self.vmnet)
        self.assertEqual(result.subnet, "172.28.235.0/24")
        self.assertEqual(result.guest_address, "172.28.235.31")
        self.assertEqual(result.running_vm_count, 2)
        self.assertEqual(result.registered_instance_count, 1)
        self.assertEqual(ip_probe.call_count, 2)
        vmrun.assert_called_once_with("vmrun", "-T", "ws", "list")

    def test_clean_workspace_can_be_absent(self):
        with patch.object(host, "ipv4_json", side_effect=[[], []]), \
             patch.object(host, "read_only_command", return_value="Total running VMs: 0\n"):
            plan = host.host_plan(
                workspaces=(self.root / "new-workspace",),
                vmware_networking=self.vmnet)
        self.assertEqual(plan.prefix, "172.28.232")
        self.assertEqual(plan.registered_instance_count, 0)

    def test_vmrun_output_must_match_declared_count(self):
        for output in ("", "Total running VMs: 2\n/one.vmx\n",
                       "Total running VMs: 2\n/one.vmx\n/one.vmx\n",
                       "Total running VMs: 0\n/one.vmx\n"):
            with self.subTest(output=output), self.assertRaises(host.HostEvidenceBlocked):
                host.running_vm_count(output)

    def test_existing_instance_manifest_cannot_be_ambiguous(self):
        instance = self.workspace / "bad"
        instance.mkdir()
        (instance / "instance.json").write_text('{"lab":"WSLPE"}')
        with self.assertRaisesRegex(host.HostEvidenceBlocked, "subnet is unknown"):
            host.native_instance_prefixes((self.workspace,))

    def test_instance_manifest_symlink_is_blocked(self):
        source = self.root / "manifest.json"
        source.write_text('{"ip_range":"172.28.240"}')
        instance = self.workspace / "bad"
        instance.mkdir()
        (instance / "instance.json").symlink_to(source)
        with self.assertRaisesRegex(host.HostEvidenceBlocked, "Symlinked"):
            host.native_instance_prefixes((self.workspace,))

    def test_duplicate_workspace_is_blocked(self):
        with self.assertRaisesRegex(host.HostEvidenceBlocked, "Duplicate"):
            host.native_instance_prefixes((self.workspace, self.workspace))

    def test_networking_symlink_is_blocked(self):
        linked = self.root / "networking-link"
        linked.symlink_to(self.vmnet)
        with self.assertRaisesRegex(host.HostEvidenceBlocked, "symlinked"):
            host.host_plan(workspaces=(self.workspace,), vmware_networking=linked)

    def test_host_cli_only_uses_read_only_planner(self):
        source = Path(__file__).resolve().parents[1] / "scripts/wslpe41-install.py"
        spec = importlib.util.spec_from_file_location("wslpe41_host_cli", source)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        output = io.StringIO()
        expected = host.HostInstallPlan("172.28.232", "172.28.232.0/24",
                                        "172.28.232.31", 5, 0, 1)
        with patch.object(host, "host_plan", return_value=expected) as planner, \
             redirect_stdout(output):
            rc = mod.main(["--host-plan"])
        self.assertEqual(rc, 0)
        self.assertIn("172.28.232.0/24", output.getvalue())
        self.assertIn("5 (not stopped)", output.getvalue())
        self.assertIn("No VMware, Windows, Ansible", output.getvalue())
        self.assertEqual(planner.call_count, 1)

    def test_execute_never_invokes_host_probe(self):
        source = Path(__file__).resolve().parents[1] / "scripts/wslpe41-install.py"
        spec = importlib.util.spec_from_file_location("wslpe41_execute_cli", source)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with patch.object(host, "host_plan") as planner, redirect_stdout(io.StringIO()):
            rc = mod.main(["--execute"])
        self.assertEqual(rc, 2)
        planner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
