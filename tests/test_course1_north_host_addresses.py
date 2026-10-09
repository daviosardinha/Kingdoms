"""NORTH post-allocation host-fit and isolated address persistence regressions."""
import copy
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from goad.course1_vmnet_phase import inspect_network_phase
from goad.course1_runtime_contract import ProfileNotReady
from tests.test_course1_host_fit import host_snapshot
from tests.test_course1_network_plan import proposal

ROOT = Path(__file__).resolve().parents[1]


def allocated_snapshot(north="10.41.10.1/24", management="10.41.99.1/24"):
    p = proposal()
    s = host_snapshot()
    for zone in ("NORTH", "SEVENKINGDOMS", "MANAGEMENT"):
        vmnet = p["zones"][zone]["vmnet"]
        s["observed_vmnets"].append(vmnet)
        s["vmware_configured_subnet_hints"].append({
            "vmnet": vmnet,
            "subnet_address": p["zones"][zone]["subnet"].split("/")[0],
        })
    for name, ip in (("vmnet11", north), ("vmnet13", management)):
        s["host_interfaces"].append({
            "interface": name, "ipv4": [ip], "state": "UNKNOWN"
        })
        net = "10.41.10.0/24" if name == "vmnet11" else "10.41.99.0/24"
        s["ipv4_routes"].append({"destination": net, "interface": name})
    return s


class NorthAllocatedHostTests(unittest.TestCase):
    def test_unallocated_still_runs_original_collision_gate(self):
        result = inspect_network_phase(proposal(), host_snapshot())
        self.assertEqual(result["network_phase"], "UNALLOCATED")
        self.assertFalse(result["deployment_authorized"])

    def test_three_networks_pending_host_addresses(self):
        result = inspect_network_phase(proposal(), allocated_snapshot())
        self.assertEqual(result["network_phase"], "ALLOCATED")
        self.assertEqual(result["status"], "NORTH_HOST_ADDRESSES_PENDING")
        self.assertEqual(result["host_addresses"]["NORTH"], "10.41.10.1/24")
        self.assertFalse(result["host_addresses_ready"])
        self.assertTrue(result["reference_host_addresses_preserved"])
        self.assertFalse(result["deployment_authorized"])

    def test_corrected_addresses_are_ready_but_not_deployed(self):
        snap = allocated_snapshot("10.41.10.254/24", "10.41.99.254/24")
        result = inspect_network_phase(proposal(), snap)
        self.assertEqual(result["status"], "NORTH_HOST_ADDRESSES_READY")
        self.assertTrue(result["host_addresses_ready"])
        self.assertFalse(result["guest_lifecycle_authorized"])
        self.assertFalse(result["deployment_authorized"])

    def test_partial_allocation_is_refused(self):
        s = allocated_snapshot()
        s["observed_vmnets"].remove("vmnet12")
        with self.assertRaises(ProfileNotReady):
            inspect_network_phase(proposal(), s)

    def test_wrong_allocated_subnet_is_refused(self):
        s = allocated_snapshot()
        s["vmware_configured_subnet_hints"][-1]["subnet_address"] = "10.42.99.0"
        with self.assertRaises(ProfileNotReady):
            inspect_network_phase(proposal(), s)

    def test_parent_host_address_cannot_regress(self):
        s = allocated_snapshot()
        s["host_interfaces"][0]["ipv4"] = ["10.4.10.1/24"]
        with self.assertRaises(ProfileNotReady):
            inspect_network_phase(proposal(), s)

    def test_protected_parent_has_no_new_host_interface(self):
        s = allocated_snapshot()
        s["host_interfaces"].append({
            "interface": "vmnet12", "ipv4": [], "state": "UNKNOWN"
        })
        with self.assertRaises(ProfileNotReady):
            inspect_network_phase(proposal(), s)

    def test_unexpected_north_ip_is_refused(self):
        s = allocated_snapshot()
        for entry in s["host_interfaces"]:
            if entry["interface"] == "vmnet11":
                entry["ipv4"] = ["10.41.10.17/24"]
        with self.assertRaises(ProfileNotReady):
            inspect_network_phase(proposal(), s)

    def test_foreign_route_collision_is_refused(self):
        s = allocated_snapshot()
        s["ipv4_routes"].append({
            "destination": "10.41.20.0/24", "interface": "tun0"
        })
        with self.assertRaises(ProfileNotReady):
            inspect_network_phase(proposal(), s)

    def test_registered_vm_collision_remains_refused(self):
        s = allocated_snapshot()
        s["registered_inventory"]["registered_vms"][0]["adapters"][0][
            "vnet"] = "vmnet11"
        with self.assertRaises(ProfileNotReady):
            inspect_network_phase(proposal(), s)


FAKE_IP = r"""#!/usr/bin/env bash
case "$*" in
  "link show vmnet12") [[ "$LEAK" == "1" ]] && exit 0 || exit 1 ;;
  "link show vmnet"*) exit 0 ;;
  "-4 -o addr show dev "*)
    name="$6"
    case "$name" in
      vmnet10) addr="10.4.10.254/24" ;;
      vmnet99) addr="10.4.99.254/24" ;;
      vmnet11) addr="$VMNET11" ;;
      vmnet13) addr="$VMNET13" ;;
      *) exit 2 ;;
    esac
    echo "7: $name inet $addr scope global $name"
    exit 0 ;;
esac
exit 3
"""


class NorthHostAddressHelperTests(unittest.TestCase):
    def test_helper_shell_and_installer_shell_syntax(self):
        for rel in (
            "scripts/course1/kingdoms-north-vmnet-hostaddrs",
            "scripts/course1/manage-north-hostaddrs.sh",
        ):
            with self.subTest(file=rel):
                run = subprocess.run(
                    ["bash", "-n", str(ROOT / rel)],
                    capture_output=True, text=True,
                )
                self.assertEqual(run.returncode, 0, run.stderr)

    def run_fake(self, addr="10.41.10.254/24", leak=False):
        with tempfile.TemporaryDirectory(prefix="kingdoms-north-ip-test-") as dir:
            ip = Path(dir) / "ip"
            ip.write_text(FAKE_IP, encoding="utf-8")
            ip.chmod(0o700)
            env = {**os.environ, "PATH": dir + ":" + os.environ["PATH"],
                   "VMNET11": addr, "VMNET13": "10.41.99.254/24",
                   "LEAK": "1" if leak else "0"}
            return subprocess.run(
                ["bash", str(ROOT / "scripts/course1/kingdoms-north-vmnet-hostaddrs"),
                 "status"], capture_output=True, text=True, env=env
            )

    def test_readonly_status_passes_only_intended_host_addrs(self):
        r = self.run_fake()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("vmnet11 10.41.10.254/24", r.stdout)
        self.assertIn("vmnet13 10.41.99.254/24", r.stdout)

    def test_readonly_status_refuses_vmware_auto_gateway(self):
        r = self.run_fake(addr="10.41.10.1/24")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("expected 10.41.10.254/24", r.stderr)

    def test_readonly_status_refuses_vmnet12_host_link(self):
        r = self.run_fake(leak=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("vmnet12 acquired a host adapter", r.stderr)

    def test_persistence_owns_only_north_vmnets(self):
        helper = (ROOT / "scripts/course1/kingdoms-north-vmnet-hostaddrs").read_text()
        for token in ("repair_one vmnet11 10.41.10.254/24 10.41.10.1/24",
                      "repair_one vmnet13 10.41.99.254/24 10.41.99.1/24",
                      "check_reference", "check_segments"):
            self.assertIn(token, helper)
        for bad in ("ip -4 addr flush dev vmnet10", "ip -4 addr flush dev vmnet99",
                    "vmware-networks --stop", "vagrant up"):
            self.assertNotIn(bad, helper)
        timer = (ROOT / "ops/systemd/kingdoms-north-vmnet-hostaddrs.timer").read_text()
        service = (ROOT / "ops/systemd/kingdoms-north-vmnet-hostaddrs.service").read_text()
        self.assertIn("OnUnitInactiveSec=15s", timer)
        self.assertIn("ExecStart=/usr/local/sbin/kingdoms-north-vmnet-hostaddrs repair",
                      service)
        self.assertNotIn("goad-nomad-vmnet-hostaddrs", service + timer)

    def test_installer_blocks_missing_confirmation(self):
        run = subprocess.run(
            ["bash", str(ROOT / "scripts/course1/manage-north-hostaddrs.sh"),
             "install"], capture_output=True, text=True,
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("--confirm-host-addresses", run.stderr)


if __name__ == "__main__":
    unittest.main()
