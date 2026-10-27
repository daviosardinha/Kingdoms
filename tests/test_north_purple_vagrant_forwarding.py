"""Offline NORTH/PURPLE coexistence: exact Vagrant management-only attestation."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goad import course1_foreign_nat as foreign
from goad.course1_vmnet_config import (
    NetworkPlanError, verify_owned_vmnet_runtime,
)
from tests.test_course1_vmnet_config import Course1VmnetPlanTests


class CoexistenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Course1VmnetPlanTests(
            "test_post_vagrant_accepts_real_vmware_normalization_and_forwards")
        self.fixture.setUp()
        self.baseline, self.owned, self.normal = (
            self.fixture.vmware_post_vagrant_fixture()
        )
        self.ports = {5985: 2200, 5986: 2201, 22: 2202}
        self.rules = foreign._rules(self.ports)
        self.purple = ("\n".join(sorted(self.rules)) + "\n").encode()
        self.observed = self.normal + self.purple

    def test_purple_guest_ports_from_vagrant(self):
        output = ("5985 (guest) => 2200 (host)\n"
                  "5986 (guest) => 2201 (host)\n"
                  "22 (guest) => 2202 (host)\n")
        self.assertEqual(foreign._parse_ports(output), self.ports)
        with self.assertRaises(foreign.ForeignNatError):
            foreign._parse_ports(output.replace("2201", "2200"))
        with self.assertRaises(foreign.ForeignNatError):
            foreign._parse_ports(output.replace("5986", "3389"))

    def test_foreign_rules_are_blocked_without_valid_proof(self):
        with self.assertRaisesRegex(NetworkPlanError, "outside approved"):
            verify_owned_vmnet_runtime(self.owned, self.observed,
                                       self.baseline, self.fixture.layout)
        findings = verify_owned_vmnet_runtime(
            self.owned, self.observed, self.baseline, self.fixture.layout,
            reviewed_foreign_nat=self.rules)
        self.assertEqual(len(findings), 2)

    def test_proof_binds_exact_ports_and_guest_address(self):
        for old, new in (
            (b"172.28.233.31", b"10.4.10.31"),
            (b"2200", b"3200"),
            (b"5985", b"3389"),
            (b"8 tcp", b"10 tcp"),
        ):
            with self.subTest(new=new), self.assertRaises(NetworkPlanError):
                verify_owned_vmnet_runtime(
                    self.owned, self.observed.replace(old, new, 1),
                    self.baseline, self.fixture.layout,
                    reviewed_foreign_nat=self.rules)

    def test_unknown_or_replayed_proof_is_refused(self):
        for bad in (frozenset(), frozenset(list(self.rules)[:2]),
                    frozenset((*self.rules, "add_nat_portfwd 8 tcp 9999 10.4.10.11 22"))):
            with self.subTest(bad=bad), self.assertRaises(NetworkPlanError):
                verify_owned_vmnet_runtime(self.owned, self.observed,
                                           self.baseline, self.fixture.layout,
                                           reviewed_foreign_nat=bad)

    def test_register_and_read_identity_pinned_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            north = root / "north" / "workspace" / "0da0a9-north-vmware" / "provider"
            north.mkdir(parents=True)
            purple = root / "purple" / "workspace" / "ef5c0b-purple-vmware" / "provider"
            purple.mkdir(parents=True)
            (purple / "Vagrantfile").write_text(
                'boxes = [{ :name => "PURPLE-WS01", :ip => "172.28.233.31" }]\n')
            state = purple / ".vagrant" / "machines" / "PURPLE-WS01" / "vmware_desktop" / "abc"
            state.mkdir(parents=True)
            vmx = state / "windows_10.vmx"
            vmx.write_text("fixture")
            pointer = state.parent / "id"
            pointer.write_text(str(vmx))
            owner = root / "north-owner.json"
            owner.write_text(json.dumps({"profile": "NORTH", "provider": str(north)}))
            owner.chmod(0o600)
            networking = root / "networking"
            networking.write_bytes(self.observed)
            receipt = root / "receipt.json"
            output = "5985 (guest) => 2200 (host)\n5986 (guest) => 2201 (host)\n22 (guest) => 2202 (host)\n"
            # Only the host-network provider proof is mocked; no actual VMware/VMX
            # actions occur and no real files outside this fixture are written.
            with patch.object(foreign.os, "geteuid", return_value=0), patch(
                "goad.course1_host_network_apply.inspect_installed_north",
                return_value=("pass",)):
                foreign.register(
                    str(north), str(purple), owner=owner,
                    networking=networking, receipt=receipt,
                    owner_uid=os.getuid(), vagrant_output=output)
            self.assertEqual(
                foreign.approved_foreign_forwardings(
                    str(north), owner.read_bytes(), source=receipt,
                    owner_uid=os.getuid()), self.rules)
            data = json.loads(receipt.read_text())
            self.assertEqual(data["vmx_path"], str(vmx))
            pointer.write_text(str(vmx) + "\n")
            with self.assertRaises(foreign.ForeignNatError):
                foreign.approved_foreign_forwardings(
                    str(north), owner.read_bytes(), source=receipt,
                    owner_uid=os.getuid())

    def test_approved_proof_absent_is_no_exception(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                foreign.approved_foreign_forwardings(
                    "/north/provider", b"owner", source=Path(td)/"no.json",
                    owner_uid=os.getuid()), frozenset())


if __name__ == "__main__":
    unittest.main()
