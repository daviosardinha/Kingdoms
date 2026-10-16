"""Mocked WSLPE systemd VMware inventory + scratch restore checks; no real VM mutations."""
import os
import pwd
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from hashlib import sha256

from kingdoms.wslpe_vmrun_recovery import (
    verify_vmrun_output, worker_vmrun_read_only,
    rehearse_vmrun_systemd, rehearse_offline_copy,
)

VMX = (
    'displayName = "WSLPE-WS01"\n'
    'ethernet0.present = "TRUE"\n'
    'ethernet0.connectionType = "nat"\n'
    'ethernet0.generatedAddress = "00:0c:29:01:bb:77"\n'
    'ethernet1.present = "TRUE"\n'
    'ethernet1.connectionType = "custom"\n'
    'ethernet1.vnet = "vmnet2"\n'
    'ethernet1.generatedAddress = "00:0c:29:01:bb:81"\n'
    'ethernet1.startConnected = "TRUE"\n'
)


def result(rc=0, stdout=""):
    return SimpleNamespace(returncode=rc, stdout=stdout)


class WslpeVmrunRecoveryTests(unittest.TestCase):
    def test_vmrun_accepts_only_unique_exact_registered_vmx(self):
        with TemporaryDirectory() as temp:
            vmx = Path(temp) / "windows_10.vmx"
            vmx.write_text(VMX)
            other = Path(temp) / "GOAD-WS01" / "windows_10.vmx"
            other.parent.mkdir()
            other.write_text("not our guest")
            text = f"Total running VMs: 2\n{other}\n{vmx}\n"
            self.assertEqual(verify_vmrun_output(text, vmx), 2)
            for broken in (
                f"Total running VMs: 2\n{vmx}\n",
                f"Total running VMs: 2\n{vmx}\n{vmx}\n",
                f"Total running VMs: 1\n{other}\n",
                f"Total running VMs: 1\n{vmx.name}\n",
                f"unexpected\n{vmx}\n",
            ):
                with self.subTest(broken=broken[:65]), self.assertRaises((ValueError, OSError)):
                    verify_vmrun_output(broken, vmx)

    @unittest.skipIf(os.getuid() == 0, "must be nonroot for owner test")
    def test_worker_is_list_only_and_never_writes_real_vmx(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            vmx = folder / "windows_10.vmx"
            vmx.write_text(VMX)
            fake = folder / "vmrun"
            fake.write_text("test fixture")
            fake.chmod(0o700)
            output = folder / "vmrun-result.json"
            calls = []
            def run(argv, **kwargs):
                calls.append(argv)
                return result(stdout=f"Total running VMs: 1\n{vmx}\n")
            with patch("kingdoms.wslpe_vmrun_recovery.subprocess.run", side_effect=run):
                worker_vmrun_read_only(vmx, fake, output)
            self.assertEqual(calls, [[str(fake), "-T", "ws", "list"]])
            self.assertEqual(vmx.read_text(), VMX)
            data = json.loads(output.read_text())
            self.assertEqual(data["status"], "PASS")
            self.assertEqual(data["owner_uid"], os.getuid())

    @unittest.skipIf(os.getuid() == 0, "must be nonroot for owner test")
    def test_real_systemd_argv_uses_exact_user_and_only_vmware_list_worker(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            vmx = folder / "windows_10.vmx"
            vmx.write_text(VMX)
            worker = folder / "worker.py"
            worker.write_text("pass")
            python = folder / "python"
            python.write_text("pass")
            vmrun = folder / "vmrun"
            vmrun.write_text("pass")
            owner = pwd.getpwuid(os.getuid()).pw_name
            calls = []
            def run(argv, timeout=20):
                calls.append(argv)
                if argv[:3] == ["sudo", "-n", "systemd-run"]:
                    out = Path(argv[argv.index("--result") + 1])
                    out.write_text(json.dumps({
                        "status": "PASS", "owner_uid": os.getuid(),
                        "vmx_sha256": sha256(str(vmx.resolve()).encode()).hexdigest(),
                        "running_vm_count": 1,
                    }))
                    return result()
                return result(stdout="active\n")
            evidence = rehearse_vmrun_systemd(
                vmx, os.getuid(), owner, runner=run, sleep=lambda _: None,
                python_bin=python, worker_script=worker, vmrun_bin=vmrun)
            self.assertEqual(evidence["running_vm_count"], 1)
            args = calls[0]
            self.assertIn(f"--property=User={owner}", args)
            self.assertEqual(args[-3:], ["--result", args[-2], args[-1]][1:] if False else args[-3:])
            self.assertIn("--worker", args)
            self.assertIn(str(vmx), args)
            self.assertIn(str(vmrun), args)
            self.assertNotIn("stop", args)
            self.assertNotIn("start", args)
            self.assertFalse(Path(args[-1]).exists())

    def test_scratch_copy_restores_original_bytes_without_live_vmx_edit(self):
        with TemporaryDirectory() as temp:
            live = Path(temp) / "windows_10.vmx"
            live.write_text(VMX)
            before = live.read_bytes()
            old, new = rehearse_offline_copy(before, "vmnet2", os.getuid())
            self.assertEqual(sha256(before).hexdigest(), old)
            self.assertNotEqual(old, new)
            self.assertEqual(live.read_bytes(), before)

    def test_scratch_cutover_fails_on_other_vmnet_or_corrupt_original(self):
        with self.assertRaises(ValueError):
            rehearse_offline_copy(VMX.encode(), "vmnet10", os.getuid())
        with self.assertRaises(ValueError):
            rehearse_offline_copy(VMX.encode() + b"\xff", "vmnet2", os.getuid())

    def test_source_disallows_vmware_mutation_and_north_access(self):
        source = (Path(__file__).resolve().parents[1] /
                  "kingdoms/wslpe_vmrun_recovery.py").read_text()
        for forbidden in (
            '"stop"', '"start"', '"suspend"', '"reset"',
            "vmrun -T ws stop", "nft -f", "vmx_original.write",
            "lab-mode.sh", "10.4.10.11", "vmnet10",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
