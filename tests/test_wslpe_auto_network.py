"""WSlPE fresh-install network selection tests, no hypervisor or host writes."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import json
import os
import tempfile
import unittest
from unittest import mock

from kingdoms import wslpe_auto_network as auto
from kingdoms import wslpe_stage1 as boot
from goad_nomad import _dispatch_task


HOST = (
    "VERSION=1,0\n"
    "answer VNET_1_HOSTONLY_SUBNET 172.16.195.0\n"
    "answer VNET_1_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_8_HOSTONLY_SUBNET 192.168.213.0\n"
    "answer VNET_8_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_8_NAT yes\n"
    "answer VNET_10_HOSTONLY_SUBNET 10.4.10.0\n"
    "answer VNET_10_HOSTONLY_NETMASK 255.255.255.0\n"
)


class WslpeAutoNetworkTests(unittest.TestCase):
    def test_clean_vmware_chooses_existing_candidate_without_changes(self):
        proposal = auto.choose_prefix(HOST, [], [])
        self.assertEqual(proposal["prefix"], "172.28.231")
        self.assertEqual(proposal["cidr"], "172.28.231.0/24")
        self.assertEqual(proposal["guest_ip"], "172.28.231.31")
        self.assertEqual(proposal["mode"], "READ_ONLY_FRESH_PILOT")
        self.assertEqual(proposal["scanned_candidates"], 1)

    def test_existing_wslpe_network_causes_skip(self):
        source = HOST + (
            "answer VNET_2_HOSTONLY_SUBNET 172.28.231.0\n"
            "answer VNET_2_HOSTONLY_NETMASK 255.255.255.0\n"
        )
        p = auto.choose_prefix(source, [], [])
        self.assertEqual(p["prefix"], "172.28.232")
        self.assertEqual(p["guest_ip"], "172.28.232.31")
        self.assertEqual(p["scanned_candidates"], 2)

    def test_all_tables_host_route_and_subnet_overlap_skip(self):
        addresses = [{"ifname": "vpn0", "addr_info": [
            {"family": "inet", "local": "172.28.231.75", "prefixlen": 24}
        ]}]
        routes = [{"dst": "172.28.232.0/23", "dev": "tun0", "table": 100}]
        p = auto.choose_prefix(HOST, addresses, routes)
        self.assertEqual(p["prefix"], "172.28.234")

    def test_no_free_prefix_fails_closed(self):
        with self.assertRaisesRegex(auto.NetworkSelectionError, "No collision-free"):
            auto.choose_prefix(
                HOST, [],
                [{"dst": "172.28.231.0/24"}, {"dst": "172.28.232.0/24"}],
                candidates=("172.28.231", "172.28.232"),
            )

    def test_reject_duplicate_and_incomplete_vmnet_metadata(self):
        with self.assertRaisesRegex(auto.NetworkSelectionError, "Unsafe VMware"):
            auto.choose_prefix(HOST + "answer VNET_1_HOSTONLY_SUBNET 172.16.196.0\n", [], [])
        with self.assertRaisesRegex(auto.NetworkSelectionError, "Unsafe VMware"):
            auto.choose_prefix(HOST + "answer VNET_3_NAT\n", [], [])

    def test_partial_vmnet_subnet_metadata_refuses_allocation(self):
        for extra in (
            "answer VNET_4_HOSTONLY_SUBNET 172.29.210.0",
            "answer VNET_4_HOSTONLY_NETMASK 255.255.255.0",
        ):
            with self.subTest(extra=extra), self.assertRaisesRegex(
                auto.NetworkSelectionError, "incomplete subnet metadata"
            ):
                auto.choose_prefix(HOST + extra + chr(10), [], [])

    def test_live_proposal_and_unchanged_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "networking"
            config.write_text(HOST, encoding="utf-8")
            checker = auto._checker()
            with (
                mock.patch.object(auto, "NETWORKING", config),
                mock.patch.object(auto, "require_no_running_guests") as idle,
                mock.patch.object(auto, "_checker", return_value=checker),
                mock.patch.object(checker, "run_ip", return_value=[]),
            ):
                plan = auto.choose_live()
                self.assertEqual(plan["prefix"], "172.28.231")
                self.assertEqual(idle.call_count, 2)
                auto.assert_plan_still_valid(plan)
                config.write_text(HOST + "# Operator metadata changed\n", encoding="utf-8")
                with self.assertRaisesRegex(auto.NetworkSelectionError, "changed after"):
                    auto.assert_plan_still_valid(plan)

    def test_read_only_planning_does_not_require_powering_off_north(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "networking"
            config.write_text(HOST, encoding="utf-8")
            checker = auto._checker()
            with (
                mock.patch.object(auto, "NETWORKING", config),
                mock.patch.object(auto, "require_no_running_guests") as idle,
                mock.patch.object(auto, "_checker", return_value=checker),
                mock.patch.object(checker, "run_ip", return_value=[]),
            ):
                result = auto.choose_live(fresh_boot=False)
                self.assertEqual(result["guest_ip"], "172.28.231.31")
                idle.assert_not_called()

    def test_running_vmware_guests_fail_before_ip_inspection(self):
        busy = SimpleNamespace(returncode=0, stdout="Total running VMs: 5\n", stderr="")
        with mock.patch.object(auto.subprocess, "run", return_value=busy) as process:
            with self.assertRaisesRegex(auto.NetworkSelectionError, "requires no running"):
                auto.require_no_running_guests()
        process.assert_called_once()
        self.assertEqual(process.call_args.args[0], ["vmrun", "-T", "ws", "list"])

    def test_vmware_process_blocks_even_if_vmrun_reports_empty(self):
        idle = SimpleNamespace(returncode=0, stdout="Total running VMs: 0\n", stderr="")
        vmx = SimpleNamespace(returncode=0, stdout="1234\n", stderr="")
        with mock.patch.object(auto.subprocess, "run", side_effect=[idle, vmx]):
            with self.assertRaisesRegex(auto.NetworkSelectionError, "guest process"):
                auto.require_no_running_guests()

    def test_vmware_idle_both_checks_pass(self):
        idle = SimpleNamespace(returncode=0, stdout="Total running VMs: 0\n", stderr="")
        none = SimpleNamespace(returncode=1, stdout="", stderr="")
        with mock.patch.object(auto.subprocess, "run", side_effect=[idle, none]):
            auto.require_no_running_guests()

    def test_symlinked_networking_path_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            original = path / "original"
            original.write_text(HOST)
            link = path / "networking"
            link.symlink_to(original)
            with mock.patch.object(auto, "NETWORKING", link):
                with self.assertRaisesRegex(auto.NetworkSelectionError, "unsafe"):
                    auto._network_config()

    def test_stage1_plan_revalidated_after_preboot_before_workspace_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            manager = SimpleNamespace(
                current_settings=SimpleNamespace(provisioner_name="local", extensions_name=[]),
                get_current_lab_name=lambda: "WSLPE",
                get_current_provider_name=lambda: "vmware",
                get_current_instance=lambda: None,
            )
            plan = {"prefix": "172.28.231", "mode": "READ_ONLY_FRESH_PILOT"}
            with (
                mock.patch.object(boot.GoadPath, "get_project_path", return_value=str(root)),
                mock.patch.object(boot.GoadPath, "get_workspace_path", return_value=str(workspace)),
                mock.patch.object(boot, "preboot_acceptance", return_value=True) as acceptance,
                mock.patch.object(auto, "assert_plan_still_valid",
                                  side_effect=auto.NetworkSelectionError("race")) as recheck,
            ):
                self.assertFalse(boot.bootstrap_native_wslpe(
                    manager, "172.28.231", confirmed=True, fresh_network_plan=plan,
                ))
            acceptance.assert_called_once()
            recheck.assert_called_once_with(plan)
            self.assertFalse(workspace.exists())

    def pilot_args(self, task="wslpe-fresh-pilot", confirm=False):
        return SimpleNamespace(
            lab="WSLPE", provider="vmware", method="local",
            instance=None, extensions=None, course=None,
            run_playbook=None, ansible_only=None, task=task,
            confirm_wslpe_fresh_pilot=confirm,
        )

    def test_legacy_wslpe_install_remains_locked(self):
        operator = mock.Mock()
        self.assertEqual(_dispatch_task(operator, self.pilot_args(task="install")), 1)
        operator.do_install.assert_not_called()

    def test_pilot_rejects_missing_confirmation_before_any_proposal(self):
        operator = mock.Mock()
        with mock.patch("goad_nomad.choose_live") as chooser:
            self.assertEqual(_dispatch_task(operator, self.pilot_args()), 1)
        chooser.assert_not_called()
        operator.lab_manager.create_instance.assert_not_called()

    def test_read_only_task_selects_network_without_boot(self):
        operator = mock.Mock()
        operator.lab_manager.get_current_instance.return_value = None
        proposal = auto.choose_prefix(HOST, [], [])
        with (
            mock.patch("goad_nomad.choose_live", return_value=proposal) as chooser,
            mock.patch("goad_nomad.bootstrap_native_wslpe") as bootstrap,
        ):
            self.assertEqual(_dispatch_task(operator, self.pilot_args(task="wslpe-network-plan")), 0)
        chooser.assert_called_once_with(fresh_boot=False)
        bootstrap.assert_not_called()
        operator.lab_manager.create_instance.assert_not_called()

    def test_other_checkout_offline_master_does_not_block_new_pilot(self):
        operator = mock.Mock()
        operator.lab_manager.get_current_instance.return_value = None
        operator.lab_manager.lab_instances.instances = {}
        operator._set_course_selection.return_value = True
        source = HOST + chr(10).join((
            "answer VNET_2_HOSTONLY_SUBNET 172.28.231.0",
            "answer VNET_2_HOSTONLY_NETMASK 255.255.255.0",
            "",
        ))
        proposal = auto.choose_prefix(source, [], [])
        self.assertEqual(proposal["prefix"], "172.28.232")
        with (
            mock.patch("goad_nomad.choose_live", return_value=proposal) as selector,
            mock.patch("goad_nomad.bootstrap_native_wslpe", return_value=True) as bootstrap,
        ):
            self.assertEqual(_dispatch_task(operator, self.pilot_args(confirm=True)), 0)
        selector.assert_called_once_with(fresh_boot=True)
        bootstrap.assert_called_once()

    def test_same_checkout_registered_master_blocks_new_pilot(self):
        operator = mock.Mock()
        operator.lab_manager.get_current_instance.return_value = None
        operator.lab_manager.lab_instances.instances = {
            "existing": SimpleNamespace(lab_name="WSLPE")
        }
        with mock.patch("goad_nomad.choose_live") as selector:
            self.assertEqual(_dispatch_task(operator, self.pilot_args(confirm=True)), 1)
        selector.assert_not_called()

    def test_explicit_pilot_dispatch_uses_only_native_stage1_boot(self):
        operator = mock.Mock()
        operator.lab_manager.get_current_instance.return_value = None
        operator.lab_manager.lab_instances.instances = {}
        operator._set_course_selection.return_value = True
        proposal = auto.choose_prefix(HOST, [], [])
        with (
            mock.patch("goad_nomad.choose_live", return_value=proposal),
            mock.patch("goad_nomad.bootstrap_native_wslpe", return_value=True) as bootstrap,
        ):
            self.assertEqual(_dispatch_task(operator, self.pilot_args(confirm=True)), 0)
        bootstrap.assert_called_once_with(
            operator.lab_manager, proposal["prefix"], confirmed=True,
            fresh_network_plan=proposal,
        )
        operator.do_install.assert_not_called()

    def test_pilot_denies_existing_instance_and_wrong_lab(self):
        operator = mock.Mock()
        operator.lab_manager.get_current_instance.return_value = object()
        args = self.pilot_args(confirm=True)
        with mock.patch("goad_nomad.choose_live") as chooser:
            self.assertEqual(_dispatch_task(operator, args), 1)
        chooser.assert_not_called()
        operator.lab_manager.get_current_instance.return_value = None
        args.lab = "GOAD"
        with mock.patch("goad_nomad.choose_live") as chooser:
            self.assertEqual(_dispatch_task(operator, args), 1)
        chooser.assert_not_called()

    def test_north_range_remains_reserved_and_wslpe_guest_is_generated(self):
        self.assertNotIn("10.4.", auto.choose_prefix(HOST, [], [])["guest_ip"])
        with self.assertRaises(auto.NetworkSelectionError):
            auto.choose_prefix(HOST, [], [], candidates=("10.4.10",))
        source = (Path(__file__).resolve().parents[1] /
                  "ad/WSLPE/providers/vmware/Vagrantfile").read_text()
        self.assertIn(':ip => "{{ip_range}}.31"', source)
        self.assertNotIn("vmnet10", source)


if __name__ == "__main__":
    unittest.main()
