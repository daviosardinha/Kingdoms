"""NORTH-derived WSLPE-only recovery state machine, all VMware calls mocked."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from kingdoms.wslpe_exact_restore import prepare_plan
from kingdoms.wslpe_vmware_recover import owner_recover, parse_inventory

VMX = (
    'ethernet0.present = "TRUE"\n'
    'ethernet0.connectionType = "nat"\n'
    'ethernet0.generatedAddress = "00:0c:29:01:bb:77"\n'
    'ethernet1.present = "TRUE"\n'
    'ethernet1.connectionType = "custom"\n'
    'ethernet1.vnet = "vmnet2"\n'
    'ethernet1.generatedAddress = "00:0c:29:01:bb:81"\n'
)

def result(text="", code=0):
    return SimpleNamespace(returncode=code, stdout=text)

class ExactRecoveryTests(unittest.TestCase):
    def test_vmrun_list_requires_valid_count(self):
        with TemporaryDirectory() as folder:
            vm = Path(folder) / "windows_10.vmx"
            vm.write_text(VMX)
            self.assertTrue(parse_inventory(f"Total running VMs: 1\n{vm}\n", vm))
            self.assertFalse(parse_inventory("Total running VMs: 0\n", vm))
            alias = str(vm.parent) + "/./" + vm.name
            self.assertRaises(ValueError, parse_inventory,
                              f"Total running VMs: 2\n{vm}\n{alias}\n", vm)
            for bad in ("", "wrong", "Total running VMs: 2\n"+str(vm)+"\n",
                        f"Total running VMs: 2\n{vm}\n{vm}\n"):
                self.assertRaises(ValueError, parse_inventory, bad, vm)

    @unittest.skipIf(os.geteuid() == 0, "requires unprivileged VMware owner")
    def test_live_recovery_is_explicit_and_only_exact_vmx(self):
        with TemporaryDirectory() as folder:
            vm = Path(folder) / "windows_10.vmx"
            vm.write_text(VMX)
            plan = prepare_plan(vm, vm, "vmnet2", os.geteuid())
            vm.write_bytes(plan.candidate)
            seen = []
            status = {"running": True}
            def fake_runner(argv, **kwargs):
                seen.append(argv)
                if argv[3] == "list":
                    return result(f"Total running VMs: {int(status['running'])}\n" +
                                  (str(vm) + "\n" if status["running"] else ""))
                if argv[3] == "stop" and argv[-1] == "soft":
                    status["running"] = False
                    return result()
                if argv[3] == "start" and argv[-1] == "nogui":
                    status["running"] = True
                    return result()
                return result(code=1)
            self.assertRaises(ValueError, owner_recover, plan, vm, "vmrun",
                              runner=fake_runner)
            self.assertEqual(seen, [])
            self.assertEqual(owner_recover(plan, vm, "vmrun", execute=True,
                                           runner=fake_runner, pause=lambda _: None),
                             "RESTORED_ORIGINAL_OFFLINE")
            self.assertEqual(vm.read_bytes(), plan.original)
            actions = [v[3] for v in seen]
            self.assertEqual(actions.count("stop"), 1)
            self.assertEqual(actions.count("start"), 1)
            self.assertTrue(status["running"])

    @unittest.skipIf(os.geteuid() == 0, "requires unprivileged VMware owner")
    def test_changed_metadata_blocks_before_stop(self):
        with TemporaryDirectory() as folder:
            vm = Path(folder) / "windows_10.vmx"
            vm.write_text(VMX)
            plan = prepare_plan(vm, vm, "vmnet2", os.geteuid())
            vm.write_bytes(plan.candidate + b'other = "vmware"\n')
            calls = []
            def runner(argv, **kwargs):
                calls.append(argv)
                return result(f"Total running VMs: 1\n{vm}\n")
            self.assertRaisesRegex(ValueError, "differs", owner_recover,
                                   plan, vm, "vmrun", execute=True, runner=runner)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][3], "list")

    @unittest.skipIf(os.geteuid() == 0, "requires unprivileged VMware owner")
    def test_previously_stopped_vm_never_started_by_recovery(self):
        with TemporaryDirectory() as folder:
            vm = Path(folder) / "windows_10.vmx"
            vm.write_text(VMX)
            plan = prepare_plan(vm, vm, "vmnet2", os.geteuid())
            vm.write_bytes(plan.candidate)
            calls = []
            def runner(argv, **kwargs):
                calls.append(argv)
                return result("Total running VMs: 0\n")
            self.assertEqual(owner_recover(plan, vm, "vmrun", execute=True,
                                           runner=runner, pause=lambda _: None),
                             "RESTORED_ORIGINAL_OFFLINE")
            self.assertEqual(set(x[3] for x in calls), {"list"})

    @unittest.skipIf(os.geteuid() == 0, "requires unprivileged VMware owner")
    def test_wrong_owner_cannot_issue_soft_stop(self):
        from unittest.mock import patch
        with TemporaryDirectory() as folder:
            vm = Path(folder) / "windows_10.vmx"
            vm.write_text(VMX)
            plan = prepare_plan(vm, vm, "vmnet2", os.geteuid())
            vm.write_bytes(plan.candidate)
            commands = []
            def runner(argv, **kwargs):
                commands.append(argv)
                return result()
            with patch("kingdoms.wslpe_vmware_recover.os.geteuid", return_value=0):
                self.assertRaises(ValueError, owner_recover, plan, vm, "vmrun",
                                  execute=True, runner=runner)
            self.assertEqual(commands, [])
            self.assertEqual(vm.read_bytes(), plan.candidate)

if __name__ == "__main__":
    unittest.main()
