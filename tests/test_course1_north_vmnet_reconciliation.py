"""NORTH vmnet host-address drift after Windows Vagrant attach (offline).

Execute committed provider methods through their AST: the full VMware module
imports runtime-only pywinrm. No VMware VMs, interfaces, or systemd units
are accessed by these tests.
"""
import ast
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"
SERVICE = "kingdoms-north-vmnet-hostaddrs.service"
HELPER = "/tmp/isolated-course1-north-hostaddr-check"


class ParentProvider:
    def _apply_router_policy(self, mode):
        self.inherited_calls.append(("policy", mode))
        return True

    def _enable_provisioning_routes(self):
        self.inherited_calls.append(("routes",))
        return True


class NorthVmnetReconciliationTests(unittest.TestCase):
    @staticmethod
    def provider():
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
        klass = next(
            node for node in tree.body if isinstance(node, ast.ClassDef)
            and node.name == "GoadKingdomsVmwareProvider"
        )
        wanted = {
            "_reconcile_north_host_addresses", "_apply_router_policy",
            "_enable_provisioning_routes", "_rollback_north_pre_guest_bootstrap",
        }
        klass.body = [
            node for node in klass.body
            if isinstance(node, ast.FunctionDef) and node.name in wanted
        ]
        if {node.name for node in klass.body} != wanted:
            raise AssertionError("NORTH host reconciliation methods missing")
        klass.bases = [ast.Name(id="ParentProvider", ctx=ast.Load())]
        klass.keywords = []
        klass.decorator_list = []
        tree.body = [klass]
        namespace = {
            "ParentProvider": ParentProvider,
            "subprocess": subprocess,
            "Log": Mock(),
        }
        exec(compile(ast.fix_missing_locations(tree), str(SOURCE), "exec"), namespace)
        provider = namespace["GoadKingdomsVmwareProvider"]()
        provider.lab_name = "NORTH"
        provider.inherited_calls = []
        provider._north_runtime_allowed = Mock(return_value=True)
        provider._require_cached_sudo = Mock(return_value=True)
        provider._script = Mock(return_value=HELPER)
        return provider

    def test_healthy_host_addresses_are_readonly_no_restart(self):
        provider = self.provider()
        with patch.object(subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            self.assertTrue(provider._reconcile_north_host_addresses("GOAD-WS01"))
        run.assert_called_once_with(["bash", HELPER, "status"], check=False, timeout=25)
        provider._require_cached_sudo.assert_not_called()

    def test_vmware_replaced_host_address_repaired_and_revalidated(self):
        provider = self.provider()
        responses = [
            SimpleNamespace(returncode=1),
            SimpleNamespace(returncode=0),
            SimpleNamespace(returncode=0),
        ]
        with patch.object(subprocess, "run", side_effect=responses) as run:
            self.assertTrue(provider._reconcile_north_host_addresses("GOAD-WS01"))
        self.assertEqual(run.call_args_list, [
            call(["bash", HELPER, "status"], check=False, timeout=25),
            call(["sudo", "-n", "systemctl", "restart", SERVICE],
                 check=False, timeout=50),
            call(["bash", HELPER, "status"], check=False, timeout=25),
        ])
        provider._require_cached_sudo.assert_called_once()

    def test_refuses_to_repair_unbound_instance(self):
        provider = self.provider()
        provider._north_runtime_allowed.return_value = False
        with patch.object(subprocess, "run") as run:
            self.assertFalse(provider._reconcile_north_host_addresses("bad binding"))
        run.assert_not_called()

    def test_unavailable_sudo_blocks_repair_without_mutation(self):
        provider = self.provider()
        provider._require_cached_sudo.return_value = False
        with patch.object(subprocess, "run", return_value=SimpleNamespace(returncode=1)) as run:
            self.assertFalse(provider._reconcile_north_host_addresses("GOAD-WS01"))
        run.assert_called_once_with(["bash", HELPER, "status"], check=False, timeout=25)

    def test_repair_failure_stops_before_final_validation(self):
        provider = self.provider()
        with patch.object(subprocess, "run", side_effect=[
            SimpleNamespace(returncode=1), SimpleNamespace(returncode=1),
        ]) as run:
            self.assertFalse(provider._reconcile_north_host_addresses("GOAD-WS01"))
        self.assertEqual(run.call_count, 2)

    def test_repair_must_retain_expected_addresses(self):
        provider = self.provider()
        with patch.object(subprocess, "run", side_effect=[
            SimpleNamespace(returncode=1), SimpleNamespace(returncode=0),
            SimpleNamespace(returncode=1),
        ]) as run:
            self.assertFalse(provider._reconcile_north_host_addresses("GOAD-WS01"))
        self.assertEqual(run.call_count, 3)

    def test_timeout_rejects_repair_without_unhandled_exception(self):
        provider = self.provider()
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("ip", 25)):
            self.assertFalse(provider._reconcile_north_host_addresses("GOAD-WS01"))

    def test_policy_and_route_transition_require_reconciliation(self):
        provider = self.provider()
        provider._reconcile_north_host_addresses = Mock(return_value=False)
        self.assertFalse(provider._apply_router_policy("provisioning"))
        self.assertFalse(provider._enable_provisioning_routes())
        self.assertEqual(provider.inherited_calls, [])
        provider._reconcile_north_host_addresses.return_value = True
        self.assertTrue(provider._apply_router_policy("exercise"))
        self.assertTrue(provider._enable_provisioning_routes())
        self.assertEqual(provider.inherited_calls, [("policy", "exercise"), ("routes",)])

    def test_failed_install_rollback_repairs_vmnet_before_router_policy(self):
        provider = self.provider()
        # The route is already removed (or removal works) while VMware has
        # recreated a host vmnet. Policy SSH must not run until .254 is back.
        results = [
            SimpleNamespace(returncode=0),  # exact NORTH route disable
            SimpleNamespace(returncode=1),  # .254 status failed
            SimpleNamespace(returncode=0),  # protected NORTH repair service
            SimpleNamespace(returncode=0),  # independent .254 status
        ]
        with patch.object(subprocess, "run", side_effect=results) as run:
            self.assertTrue(provider._rollback_north_pre_guest_bootstrap())
        self.assertEqual(run.call_args_list, [
            call(["sudo", "-n", "bash", HELPER, "disable"],
                 check=False, timeout=30),
            call(["bash", HELPER, "status"], check=False, timeout=25),
            call(["sudo", "-n", "systemctl", "restart", SERVICE],
                 check=False, timeout=50),
            call(["bash", HELPER, "status"], check=False, timeout=25),
        ])
        self.assertEqual(provider.inherited_calls, [("policy", "exercise")])

    def test_failed_install_rollback_never_claims_isolation_after_bad_repair(self):
        provider = self.provider()
        results = [
            SimpleNamespace(returncode=0),  # exact route absent/removed
            SimpleNamespace(returncode=1),  # bad .254
            SimpleNamespace(returncode=1),  # repair refused
        ]
        with patch.object(subprocess, "run", side_effect=results) as run:
            self.assertFalse(provider._rollback_north_pre_guest_bootstrap())
        self.assertEqual(run.call_count, 3)
        self.assertEqual(provider.inherited_calls, [])

    def test_reference_routes_and_policy_remain_unchanged(self):
        provider = self.provider()
        provider.lab_name = "GOAD"
        provider._reconcile_north_host_addresses = Mock(return_value=False)
        self.assertTrue(provider._apply_router_policy("provisioning"))
        self.assertTrue(provider._enable_provisioning_routes())
        provider._reconcile_north_host_addresses.assert_not_called()
        self.assertEqual(provider.inherited_calls, [("policy", "provisioning"), ("routes",)])


if __name__ == "__main__":
    unittest.main()
