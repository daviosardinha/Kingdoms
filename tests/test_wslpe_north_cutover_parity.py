"""NORTH WS01 -> standalone WSLPE exact NAT transition source parity.

Only mocked VMware metadata and pure text rendering; never stops VMs,
applies nftables, contacts Windows, or executes NORTH lifecycle scripts.
"""
import hashlib
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest
from kingdoms.wslpe_nat_cutover_contract import (
    render_nat_offline, manifest, guarded_original_restore,
)
from kingdoms.wslpe_nat_readiness import vmx_snapshot
from kingdoms.wslpe_winrm_guard import firewall_batch
from kingdoms.wslpe_isolation_policy import render_host_filter

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/wslpe-p1c-north-cutover-preview.py"
SPEC = importlib.util.spec_from_file_location("wslpe_north_cutover_preview", CLI)
assert SPEC and SPEC.loader
PREVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIEW)

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

class NorthWs01CutoverParityTests(unittest.TestCase):
    def test_north_proven_sequence_available_readonly(self):
        # NORTH is source of truth for VMX/NAT stop/edit/start sequencing.
        PREVIEW.north_source_contract()

    def test_only_one_nat_property_is_added_and_restorable(self):
        candidate = render_nat_offline(VMX, "vmnet2")
        self.assertIn('ethernet0.startConnected = "FALSE"', candidate)
        self.assertEqual(candidate.replace(
            'ethernet0.startConnected = "FALSE"\n', ""), VMX)
        proof = manifest(VMX, candidate, "vmnet2")
        self.assertEqual(proof.before_sha256, hashlib.sha256(VMX.encode()).hexdigest())
        self.assertEqual(guarded_original_restore(candidate, VMX, proof, "vmnet2"), VMX)
        self.assertEqual(vmx_snapshot(VMX, "vmnet2")["exercise_vmnet"], "vmnet2")

    def test_existing_explicit_nat_flag_preserves_every_other_byte(self):
        source = VMX.replace(
            'ethernet0.connectionType = "nat"\n',
            'ethernet0.connectionType = "nat"\n'
            'ethernet0.startConnected = "TRUE"\n',
        )
        candidate = render_nat_offline(source, "vmnet2")
        self.assertEqual(
            candidate, source.replace('ethernet0.startConnected = "TRUE"',
                                      'ethernet0.startConnected = "FALSE"')
        )

    def test_vmx_without_final_newline_never_joins_two_properties(self):
        source = VMX.rstrip("\n")
        candidate = render_nat_offline(source, "vmnet2")
        self.assertIn('ethernet0.startConnected = "FALSE"\n'
                      'ethernet0.generatedAddress', candidate)
        self.assertEqual(guarded_original_restore(
            candidate, source, manifest(source, candidate, "vmnet2"), "vmnet2"
        ), source)

    def test_duplicate_nat_property_or_foreign_adapter_is_rejected(self):
        invalid = (
            VMX + 'ethernet0.startConnected = "TRUE"\n'
                  'ethernet0.startConnected = "FALSE"\n',
            VMX + 'ethernet2.present = "TRUE"\n',
            VMX.replace('ethernet1.vnet = "vmnet2"',
                        'ethernet1.vnet = "vmnet10"'),
            VMX.replace('ethernet0.connectionType = "nat"',
                        'ethernet0.connectionType = "bridged"'),
        )
        for source in invalid:
            with self.subTest(source=source[-80:]), self.assertRaises(ValueError):
                render_nat_offline(source, "vmnet2")

    def test_modified_candidate_or_original_blocks_restore(self):
        candidate = render_nat_offline(VMX, "vmnet2")
        proof = manifest(VMX, candidate, "vmnet2")
        with self.assertRaises(ValueError):
            guarded_original_restore(candidate + 'name = "foreign"\n',
                                     VMX, proof, "vmnet2")
        with self.assertRaises(ValueError):
            guarded_original_restore(candidate, VMX + 'foreign = "1"\n',
                                     proof, "vmnet2")

    def test_existing_scoped_firewall_renderers_reused_unchanged(self):
        guard = firewall_batch(2210)
        exercise = render_host_filter("vmnet2", "172.28.231.0/24",
                                       "172.28.231.1", "172.28.231.31")
        self.assertIn("kingdoms_wslpe_winrm", guard)
        self.assertIn("kingdoms_wslpe_exercise", exercise)
        self.assertNotIn("vmnet10", guard + exercise)
        self.assertNotIn("flush ruleset", guard + exercise)
        self.assertNotIn("masquerade", guard + exercise)

    def test_preview_has_no_north_or_vmware_lifecycle_calls(self):
        source = CLI.read_text(encoding="utf-8")
        for token in ("NORTH_REFERENCE.read_text", "north_source_contract()",
                      "stage.locate_registered_vm(", "stage.forwarded_winrm_port(",
                      "guarded_original_restore(", "render_host_filter(",
                      "render_nat_offline(", "running_exact(vmx)"):
            self.assertIn(token, source)
        for forbidden in (
            '["vmrun", "-T", "ws", "stop"', '["vmrun", "-T", "ws", "start"',
            '["nft", "-f"', '["vagrant", "up"', "vmx.write_text(",
            "vmx.write_bytes(", "ansible.windows.win_reboot:",
            "Restart-Computer", "Set-NetAdapter",
        ):
            self.assertNotIn(forbidden, source)

    def test_local_standalone_foundation_reuses_north_safe_roles(self):
        base = (ROOT / "ansible/wslpe-foundation.yml").read_text()
        lpe = (ROOT / "ansible/wslpe-lpe-test.yml").read_text()
        parity = (ROOT / "tests/test_wslpe_ws01_parity.py").read_text()
        for token in ("name: settings/hostname", "name: settings/eval_rearm"):
            self.assertIn(token, base)
        self.assertIn("role: windows_lpe", lpe)
        self.assertIn("win_domain_membership", parity)
        self.assertIn("PartOfDomain", base)

if __name__ == "__main__":
    unittest.main()
