"""One simulated vmnet4 runtime suite: no VMware actions or host writes."""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest import mock
import subprocess

from kingdoms import wslpe_management_vmnet_runtime as rt
from kingdoms.wslpe_management_vmnet_transaction import NetworkTransactionBlocked


SOURCE = (
    "VERSION=1,0\n"
    "answer VNET_3_DHCP no\n"
    "answer VNET_3_NAT no\n"
    "answer VNET_3_HOSTONLY_SUBNET 172.28.232.0\n"
    "answer VNET_3_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_10_HOSTONLY_SUBNET 10.4.10.0\n"
    "answer VNET_10_HOSTONLY_NETMASK 255.255.255.0\n"
)
ADDR = [{"ifname": "vmnet3", "addr_info": [
    {"family": "inet", "local": "172.28.232.254", "prefixlen": 24}]}]
ROUTES = [{"dst": "172.28.232.0/24", "dev": "vmnet3"}]


class Vmnet4RuntimeTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base = Path(t.name)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        (self.workspace / "WSLPE.vmx").write_text(
            'ethernet1.connectionType = "custom"\nethernet1.vnet = "vmnet3"\n'
        )
        self.networking = self.base / "networking"
        self.networking.write_text(SOURCE)
        self.state = self.base / "priv"
        self.state.mkdir()
        self.commands = []
        self.isolated = []
        self.service = SimpleNamespace(
            action=lambda operation: self.commands.append(operation))
        self.adapter = SimpleNamespace(
            verify_host_adapter=lambda vmnet, subnet, text:
            self.commands.append(("verify", vmnet, subnet, text))
        )
        self.reconciler = SimpleNamespace(
            reconcile=lambda vmnet, subnet, text:
            self.commands.append(("reconcile", vmnet, subnet, text))
        )
        self.owner_vmrun = lambda owner: "Total running VMs: 0\n"
        self.process_run = lambda *_a, **_kw: subprocess.CompletedProcess(
            [], 1, "", ""
        )
        self.routes = iter((json.dumps(ADDR), json.dumps(ROUTES)))
        self.route_run = lambda *_a, **_kw: next(self.routes)

    def runtime(self, **kwargs):
        return rt.Vmnet4MaintenanceRuntime(
            owner=kwargs.pop("owner", "stark"),
            roots=kwargs.pop("roots", (self.workspace,)),
            isolation_acceptance=kwargs.pop(
                "isolation_acceptance", lambda vmnet, subnet:
                self.isolated.append((vmnet, subnet))),
            networking=kwargs.pop("networking", self.networking),
            state_dir=kwargs.pop("state_dir", self.state),
            vmrun=kwargs.pop("vmrun", self.owner_vmrun),
            process_run=kwargs.pop("process_run", self.process_run),
            service=kwargs.pop("service", self.service),
            adapter=kwargs.pop("adapter", self.adapter),
            reconciler=kwargs.pop("reconciler", self.reconciler),
            route_run=kwargs.pop("route_run", self.route_run),
            **kwargs
        )

    def test_zero_running_counts_use_both_independent_sources(self):
        with (mock.patch.object(rt.os, "geteuid", return_value=0),
              mock.patch.object(rt, "_trusted_binary")):
            count = rt.running_zero(owner="stark", vmrun=self.owner_vmrun,
                                    process_run=self.process_run)
        self.assertEqual(count, 0)

    def test_any_running_guest_blocks_even_if_vmrun_owner_is_empty(self):
        def process(*_a, **_kw):
            return subprocess.CompletedProcess([], 0, "2\n", "")
        with (mock.patch.object(rt.os, "geteuid", return_value=0),
              mock.patch.object(rt, "_trusted_binary")):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "vmware-vmx=2"):
                rt.running_zero(owner="stark", vmrun=self.owner_vmrun,
                                process_run=process)

    def test_running_owner_vmrun_blocks_even_with_zero_processes(self):
        with (mock.patch.object(rt.os, "geteuid", return_value=0),
              mock.patch.object(rt, "_trusted_binary")):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "owner-vmrun=1"):
                rt.running_zero(owner="stark",
                                vmrun=lambda *_: "Total running VMs: 1\n/ignored.vmx\n",
                                process_run=self.process_run)

    def test_running_source_mismatch_blocks_fail_closed(self):
        with (mock.patch.object(rt.os, "geteuid", return_value=0),
              mock.patch.object(rt, "_trusted_binary")):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "Cannot establish"):
                rt.running_zero(owner="stark",
                                vmrun=lambda *_: "unparseable",
                                process_run=self.process_run)

    def test_owner_vmrun_must_drop_privileges(self):
        account = SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_name="stark",
                                  pw_dir=str(self.base))
        captured = []
        def fake_run(command, **kwargs):
            captured.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0,
                                              "Total running VMs: 0\n", "")
        with (mock.patch.object(rt.os, "geteuid", return_value=0),
              mock.patch.object(rt.pwd, "getpwnam", return_value=account),
              mock.patch.object(rt, "_trusted_binary"),
              mock.patch.object(rt.subprocess, "run", side_effect=fake_run)):
            out = rt.owner_vmrun_list("stark")
        self.assertIn("Total running VMs: 0", out)
        self.assertEqual(captured[0][1]["env"]["HOME"], str(self.base))
        self.assertTrue(callable(captured[0][1]["preexec_fn"]))
        self.assertEqual(captured[0][0][1:], ["-T", "ws", "list"])

    def test_owner_vmrun_rejects_root_or_unknown_uid(self):
        with (mock.patch.object(rt.os, "geteuid", return_value=0),
              mock.patch.object(rt.pwd, "getpwnam", return_value=SimpleNamespace(
                  pw_uid=0, pw_gid=0, pw_dir="/root", pw_name="root"))):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "non-root"):
                rt.owner_vmrun_list("root")

    def test_live_collision_probe_avoids_inventing_vmnet4(self):
        replies = iter((json.dumps(ADDR), json.dumps(ROUTES)))
        with mock.patch.object(rt, "_trusted_binary"):
            rt.verify_candidate_collisions(
                SOURCE, vmnet="vmnet4", subnet=rt.SUBNET,
                roots=(self.workspace,),
                run=lambda *_a, **_kw: next(replies)
            )
        self.assertFalse((self.state / "journal.json").exists())

    def test_overlapping_host_routes_rejected_before_mutation(self):
        bad = ROUTES + [{"dst": "172.28.233.0/24", "dev": "veth-other"}]
        replies = iter((json.dumps(ADDR), json.dumps(bad)))
        with mock.patch.object(rt, "_trusted_binary"):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "overlaps"):
                rt.verify_candidate_collisions(
                    SOURCE, vmnet="vmnet4", subnet=rt.SUBNET,
                    roots=(self.workspace,),
                    run=lambda *_a, **_kw: next(replies))

    def test_assemble_never_stops_vmware(self):
        runtime = self.runtime()
        with (mock.patch.object(rt.os, "geteuid", return_value=0),
              mock.patch.object(rt, "assert_private_state_dir"),
              mock.patch.object(runtime, "_zero", return_value=0)):
            obj = runtime.assemble()
        self.assertEqual(obj.networking, self.networking)
        self.assertEqual(obj.lock, self.state / "exclusive.lock")
        self.assertEqual(obj.journal, self.state / "journal.json")
        self.assertEqual(self.commands, [])

    def test_assemble_blocks_without_root_or_private_dir(self):
        runtime = self.runtime()
        with mock.patch.object(rt.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "Root-only"):
                runtime.assemble()
        with mock.patch.object(rt.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "root-only"):
                runtime.assemble()

    def test_assembly_requires_independent_isolation_capability(self):
        with self.assertRaisesRegex(NetworkTransactionBlocked, "Independent"):
            self.runtime(isolation_acceptance=None)

    def test_post_creation_host_and_isolation_proofs_are_both_required(self):
        runtime = self.runtime()
        with (mock.patch.object(rt, "_read_regular", return_value=(SOURCE.encode(), None)),
              mock.patch.object(runtime, "_zero", return_value=0)):
            runtime._verify(rt.VMNET, rt.SUBNET)
        self.assertEqual(self.isolated, [("vmnet4", rt.SUBNET)])
        self.assertEqual([command[0] for command in self.commands], ["reconcile", "verify"])
        self.assertEqual(self.commands[0][:3], ("reconcile", "vmnet4", rt.SUBNET))

    def test_failing_isolation_blocks_acceptance_even_after_adapter_passes(self):
        def deny(*_a):
            raise NetworkTransactionBlocked("NORTH forwarding still allowed")
        runtime = self.runtime(isolation_acceptance=deny)
        with (mock.patch.object(rt, "_read_regular", return_value=(SOURCE.encode(), None)),
              mock.patch.object(runtime, "_zero", return_value=0)):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "NORTH forwarding"):
                runtime._verify(rt.VMNET, rt.SUBNET)

    def test_live_guest_on_host_blocks_address_reconciliation(self):
        runtime = self.runtime()
        with (mock.patch.object(rt, "_read_regular", return_value=(SOURCE.encode(), None)),
              mock.patch.object(runtime, "_zero",
                                side_effect=NetworkTransactionBlocked("guest started"))):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "guest started"):
                runtime._verify(rt.VMNET, rt.SUBNET)
        self.assertEqual(self.commands, [])

    def test_reconciler_failure_never_reaches_adapter_or_isolation(self):
        refusing = SimpleNamespace(
            reconcile=lambda *_args: (_ for _ in ()).throw(
                NetworkTransactionBlocked("foreign vmnet4 address"))
        )
        runtime = self.runtime(reconciler=refusing)
        with (mock.patch.object(rt, "_read_regular", return_value=(SOURCE.encode(), None)),
              mock.patch.object(runtime, "_zero", return_value=0)):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "foreign vmnet4"):
                runtime._verify(rt.VMNET, rt.SUBNET)
        self.assertEqual(self.commands, [])
        self.assertEqual(self.isolated, [])

    def test_preflight_requires_original_owner_library_no_root_inference(self):
        library = self.base / ".vmware"
        library.mkdir()
        (library / "inventory.vmls").write_text(
            f'vmlist0.config = "{self.workspace / "WSLPE.vmx"}"\n'
        )
        account = SimpleNamespace(pw_dir=str(self.base))
        runtime = self.runtime()
        with (mock.patch.object(runtime, "_zero", return_value=0),
              mock.patch.object(rt.pwd, "getpwnam", return_value=account),
              mock.patch.object(rt, "_trusted_binary"),
              mock.patch.object(rt, "_read_regular",
                                return_value=(SOURCE.encode(), SimpleNamespace(st_uid=0)))):
            runtime._preflight(rt.VMNET, rt.SUBNET)
        self.assertEqual(self.commands, [])

    def test_preflight_rejects_unregistered_external_vm_before_restart(self):
        foreign = self.base / "foreign.vmx"
        foreign.write_text('ethernet0.vnet = "vmnet5"\n')
        library = self.base / ".vmware"
        library.mkdir()
        (library / "inventory.vmls").write_text(
            f'vmlist0.config = "{foreign}"\n'
        )
        runtime = self.runtime()
        with (mock.patch.object(runtime, "_zero", return_value=0),
              mock.patch.object(rt.pwd, "getpwnam",
                                return_value=SimpleNamespace(pw_dir=str(self.base))),
              mock.patch.object(rt, "_trusted_binary"),
              mock.patch.object(rt, "_read_regular",
                                return_value=(SOURCE.encode(), SimpleNamespace(st_uid=0)))):
            with self.assertRaisesRegex(NetworkTransactionBlocked, "coverage"):
                runtime._preflight(rt.VMNET, rt.SUBNET)


if __name__ == "__main__":
    unittest.main()
