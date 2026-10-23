"""Mock-only creation provenance tests. Never creates or starts a VMware VM."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from kingdoms import wslpe41_native_stage1_bridge as gate
from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked

COMMIT = "a" * 40
PREFIX = "172.28.232"
OLD = "/unrelated/north/guest.vmx"


class Manager:
    def get_current_instance(self):
        return None


class GuardedNativeCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.peer = self.root / "other-workspace"
        self.peer.mkdir()
        self.manager = Manager()
        self.plan = SimpleNamespace(prefix=PREFIX, running_vm_count=1)
        self.identity = FreshGuestIdentity(
            instance_id="new123-wslpe-vmware", workspace=str(self.workspace),
            vmx=str(self.workspace / "new123-wslpe-vmware" / "provider" / "win10.vmx"),
            subnet=PREFIX + ".0/24", source_commit=COMMIT,
        )

    def _create(self, *_args, **_kwargs):
        (self.workspace / self.identity.instance_id).mkdir(parents=True, exist_ok=True)
        return self.identity

    @staticmethod
    def _vmware(*paths):
        return "Total running VMs: " + str(len(paths)) + "\n" + "".join(p + "\n" for p in paths)

    def _contexts(self, outputs=None, *, prefix=PREFIX):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(
            gate.GoadPath, "get_workspace_path", return_value=str(self.workspace)))
        stack.enter_context(patch.object(
            gate.GoadPath, "get_project_path", return_value=str(self.root)))
        plan = stack.enter_context(patch.object(
            gate, "host_plan",
            return_value=SimpleNamespace(prefix=prefix, running_vm_count=1)))
        inventory = iter(outputs or [
            self._vmware(OLD), self._vmware(OLD),
            self._vmware(OLD, self.identity.vmx),
        ])
        def probe(*args):
            if args[0] == "git":
                return COMMIT + "\n" if "rev-parse" in args else ""
            return next(inventory)
        probes = stack.enter_context(patch.object(
            gate, "read_only_command", side_effect=probe))
        bootstrap = stack.enter_context(patch.object(
            gate, "create_native_guest_identity", side_effect=self._create))
        stack.enter_context(patch.object(
            gate, "verify_native_vmnet", return_value="vmnet3"))
        return stack, plan, probes, bootstrap

    def _go(self, **kwargs):
        return gate.create_guarded_native_guest(
            self.manager, COMMIT, workspaces=(self.workspace, self.peer),
            approved_prefix=PREFIX, confirmed=True, **kwargs,
        )

    def test_first_native_guest_created_once_with_exact_host_evidence(self):
        stack, host, vmware, bootstrap = self._contexts()
        with stack:
            evidence = self._go()
        self.assertEqual(evidence.identity, self.identity)
        self.assertEqual(evidence.newly_running_vmx, self.identity.vmx)
        self.assertEqual(evidence.exercise_vmnet, "vmnet3")
        self.assertEqual(evidence.previously_running, (OLD,))
        self.assertEqual(evidence.previous_instance_ids, ())
        self.assertIn("NOT guest freshness", evidence.source)
        host.assert_called_once_with(workspaces=(self.workspace, self.peer))
        bootstrap.assert_called_once_with(
            self.manager, PREFIX, COMMIT, confirmed=True)
        self.assertEqual(vmware.call_count, 5)

    def test_unconfirmed_creation_does_not_touch_host_or_vm(self):
        stack, host, vmware, bootstrap = self._contexts()
        with stack, self.assertRaises(InstallBlocked):
            gate.create_guarded_native_guest(
                self.manager, COMMIT, workspaces=(self.workspace, self.peer),
                approved_prefix=PREFIX, confirmed=False,
            )
        host.assert_not_called()
        vmware.assert_not_called()
        bootstrap.assert_not_called()

    def test_stale_candidate_prevents_creation(self):
        stack, _, _, bootstrap = self._contexts(prefix="172.28.233")
        with stack, self.assertRaisesRegex(InstallBlocked, "stale"):
            self._go()
        bootstrap.assert_not_called()

    def test_co_tenant_started_during_preflight_prevents_creation(self):
        stack, _, _, bootstrap = self._contexts(outputs=[
            self._vmware(OLD), self._vmware(OLD, "/another/guest.vmx"),
        ])
        with stack, self.assertRaisesRegex(InstallBlocked, "during the host preflight"):
            self._go()
        bootstrap.assert_not_called()

    def test_unexpected_vm_during_creation_blocks_completion(self):
        stack, _, _, bootstrap = self._contexts(outputs=[
            self._vmware(OLD), self._vmware(OLD),
            self._vmware(OLD, self.identity.vmx, "/another/new.vmx"),
        ])
        with stack, self.assertRaisesRegex(InstallBlocked, "provenance"):
            self._go()
        bootstrap.assert_called_once()

    def test_invalid_post_boot_vmnet_mapping_rejects_creation_provenance(self):
        stack, _, _, bootstrap = self._contexts()
        with stack, patch.object(
            gate, "verify_native_vmnet",
            side_effect=InstallBlocked("guest attached to NORTH vmnet"),
        ):
            with self.assertRaisesRegex(InstallBlocked, "NORTH vmnet"):
                self._go()
        bootstrap.assert_called_once()

    def test_prior_instance_is_not_reused(self):
        (self.workspace / self.identity.instance_id).mkdir(parents=True)
        stack, _, _, bootstrap = self._contexts()
        with stack, self.assertRaisesRegex(InstallBlocked, "provenance"):
            self._go()
        bootstrap.assert_called_once()

    def test_bad_workspaces_and_symlink_fail_before_mutation(self):
        stack, host, vmware, bootstrap = self._contexts()
        with stack:
            with self.assertRaisesRegex(InstallBlocked, "inventory required"):
                gate.create_guarded_native_guest(
                    self.manager, COMMIT, workspaces=(self.peer, self.workspace),
                    approved_prefix=PREFIX, confirmed=True)
            self.workspace.symlink_to(self.peer, target_is_directory=True)
            with self.assertRaisesRegex(InstallBlocked, "another checkout"):
                self._go()
        host.assert_not_called()
        vmware.assert_not_called()
        bootstrap.assert_not_called()

    def test_dirty_or_wrong_source_revision_prevents_vm_creation(self):
        stack, host, vmware, bootstrap = self._contexts()
        with stack, patch.object(gate, "read_only_command",
                                 side_effect=[COMMIT + "\n", " M tracked.py"]):
            with self.assertRaisesRegex(InstallBlocked, "not clean"):
                self._go()
        host.assert_not_called()
        bootstrap.assert_not_called()
        stack, host, vmware, bootstrap = self._contexts()
        with stack, patch.object(gate, "read_only_command",
                                 side_effect=["b" * 40 + "\n", ""]):
            with self.assertRaisesRegex(InstallBlocked, "revision differs"):
                self._go()
        host.assert_not_called()
        bootstrap.assert_not_called()

    def test_identity_from_another_native_workspace_is_rejected(self):
        stack, _, _, bootstrap = self._contexts()
        foreign = FreshGuestIdentity(
            instance_id=self.identity.instance_id, workspace=str(self.peer),
            vmx=self.identity.vmx, subnet=self.identity.subnet, source_commit=COMMIT,
        )
        def create_foreign(*_args, **_kwargs):
            (self.workspace / self.identity.instance_id).mkdir(parents=True)
            return foreign
        with stack, patch.object(gate, "create_native_guest_identity", side_effect=create_foreign):
            with self.assertRaisesRegex(InstallBlocked, "does not belong"):
                self._go()

    def test_non_absolute_and_duplicate_vmware_inventory_block_before_mutation(self):
        stack, _, _, bootstrap = self._contexts(outputs=[
            self._vmware("relative.vmx"), self._vmware(OLD),
        ])
        with stack, self.assertRaisesRegex(InstallBlocked, "relative VMX"):
            self._go()
        bootstrap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
