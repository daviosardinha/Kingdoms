"""Read-only simulated host ownership checks. Never start/stop VMware."""
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest import mock

from kingdoms import wslpe_management_vmnet_host_gate as gate

VMWARE = (
    "VERSION=1,0\n"
    "answer VNET_3_DHCP no\n"
    "answer VNET_3_NAT no\n"
    "answer VNET_3_HOSTONLY_SUBNET 172.28.232.0\n"
    "answer VNET_3_HOSTONLY_NETMASK 255.255.255.0\n"
)


class HostVmnetGateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        self.fresh = base / "fresh"
        self.old = base / "old"
        self.fresh.mkdir()
        self.old.mkdir()
        self.new_vmx = self.fresh / "WSLPE.vmx"
        self.old_vmx = self.old / "MASTER.vmx"
        self.new_vmx.write_text('ethernet1.vnet = "vmnet3"\n')
        self.old_vmx.write_text('ethernet1.vnet = "vmnet2"\n')
        self.roots = (self.fresh, self.old)

    def output(self, *paths):
        return f"Total running VMs: {len(paths)}\n" + "".join(f"{p}\n" for p in paths)

    def test_two_running_vmware_guests_are_reconciled(self):
        result = gate.parse_running_vmware(
            self.output(self.new_vmx, self.old_vmx), self.roots, 2)
        self.assertEqual(result.vmrun_count, 2)
        self.assertEqual(result.process_count, 2)
        self.assertEqual(set(result.vmx_paths),
                         {str(self.new_vmx), str(self.old_vmx)})

    def test_discrepant_guest_counts_rejected(self):
        with self.assertRaisesRegex(gate.HostVmnetGateBlocked, "differs"):
            gate.parse_running_vmware(self.output(self.new_vmx), self.roots, 2)

    def test_vmware_started_outside_supplied_workspaces_blocks(self):
        foreign = self.fresh.parent / "foreign.vmx"
        foreign.write_text('ethernet1.vnet = "vmnet12"\n')
        with self.assertRaisesRegex(gate.HostVmnetGateBlocked, "outside supplied"):
            gate.parse_running_vmware(self.output(foreign), self.roots, 1)

    def test_zero_guests_exact_counts(self):
        self.assertEqual(gate.parse_vmware_processes(1, ""), 0)
        self.assertEqual(gate.parse_vmware_processes(1, "0\n"), 0)
        result = gate.parse_running_vmware("Total running VMs: 0\n", self.roots, 0)
        self.assertEqual(result.vmx_paths, ())
        self.assertEqual(result.vmrun_count, 0)

    def test_unknown_or_malformed_process_counts_fail_closed(self):
        for code, output in ((0, "0\n"), (0, "abc"), (1, "2"), (2, ""),
                             (0, "-1"), (0, "999")):
            with self.subTest(code=code, output=output):
                with self.assertRaises(gate.HostVmnetGateBlocked):
                    gate.parse_vmware_processes(code, output)

    def test_vmrun_header_mismatch_or_duplicate_rejected(self):
        for output, count in (
            ("Total running VMs: 3\n" + str(self.new_vmx) + "\n", 1),
            (self.output(self.new_vmx, self.new_vmx), 2),
            ("Total running VMs: 1\nrelative.vmx\n", 1),
        ):
            with self.subTest(output=output):
                with self.assertRaises(gate.HostVmnetGateBlocked):
                    gate.parse_running_vmware(output, self.roots, count)

    def test_symlinked_registration_fails_closed(self):
        symlink = self.old / "alias.vmx"
        symlink.symlink_to(self.new_vmx)
        with self.assertRaisesRegex(gate.HostVmnetGateBlocked, "linked"):
            gate.parse_running_vmware(self.output(symlink), self.roots, 1)

    def test_rejects_missing_or_duplicate_workspace(self):
        with self.assertRaisesRegex(gate.HostVmnetGateBlocked, "Duplicate"):
            gate.parse_running_vmware("Total running VMs: 0\n",
                                      (self.fresh, self.fresh), 0)
        with self.assertRaisesRegex(gate.HostVmnetGateBlocked, "missing"):
            gate.parse_running_vmware("Total running VMs: 0\n",
                                      (self.fresh.parent / "absent",), 0)

    def test_vmnet4_is_scoped_candidate_only(self):
        gate.scoped_candidate_free(VMWARE, self.roots, "vmnet4")
        with self.assertRaisesRegex(gate.HostVmnetGateBlocked, "reserved"):
            gate.scoped_candidate_free(VMWARE, self.roots, "vmnet10")
        with self.assertRaisesRegex(gate.HostVmnetGateBlocked, "exists"):
            gate.scoped_candidate_free(VMWARE, self.roots, "vmnet3")
        self.new_vmx.write_text('ethernet2.vnet = "vmnet4"\n')
        with self.assertRaisesRegex(gate.HostVmnetGateBlocked, "referenced"):
            gate.scoped_candidate_free(VMWARE, self.roots, "vmnet4")

    def test_probe_uses_only_vmrun_and_pgrep(self):
        calls = []
        def vmrun(*args):
            calls.append(args)
            return self.output(self.new_vmx)
        with (mock.patch.object(gate, "read_only_command", side_effect=vmrun),
              mock.patch.object(gate.subprocess, "run",
                                return_value=CompletedProcess([], 0, "1\n", "")) as ps):
            result = gate.probe_running_vmware(self.roots)
        self.assertEqual(result.vmrun_count, 1)
        self.assertEqual(calls, [("vmrun", "-T", "ws", "list")])
        self.assertEqual(ps.call_args.args[0], ["pgrep", "-c", "-x", "vmware-vmx"])


if __name__ == "__main__":
    unittest.main()
