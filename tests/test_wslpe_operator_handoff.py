"""WSLPE operator credential and isolated stage source tests (no guest access)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import stat
import unittest
from unittest.mock import patch
import yaml

from kingdoms.wslpe_operator_credentials import operator_secret, exact_instance_id

ROOT=Path(__file__).resolve().parents[1]
PLAY=ROOT/"ansible/wslpe-operator-foundation.yml"
CLI=ROOT/"scripts/wslpe-operator-secret.py"

class OperatorHandoffTests(unittest.TestCase):
    def test_generate_once_per_instance_not_in_git_or_terminal(self):
        with TemporaryDirectory() as tmp:
            base=Path(tmp)/"store"
            a=operator_secret("d986ad-wslpe-vmware",prepare=True,store=base)
            b=operator_secret("a102ff-wslpe-vmware",prepare=True,store=base)
            self.assertGreaterEqual(len(a),24)
            self.assertNotEqual(a,b)
            self.assertEqual(operator_secret("d986ad-wslpe-vmware",store=base),a)
            self.assertEqual(stat.S_IMODE(base.stat().st_mode),0o700)
            file=base/"d986ad-wslpe-vmware/credential"
            self.assertEqual(stat.S_IMODE(file.stat().st_mode),0o600)
            self.assertEqual(file.read_text(),a+"\n")

    def test_missing_and_suspicious_paths_fail_closed(self):
        with TemporaryDirectory() as tmp:
            base=Path(tmp)/"store"
            with self.assertRaises(ValueError):
                operator_secret("d986ad-wslpe-vmware",store=base)
            for bad in ("../../NORTH","GOAD","d986ad-wslpe-vmware/../other",
                        "D986AD-wslpe-vmware"):
                with self.assertRaises(ValueError):
                    exact_instance_id(bad)
            operator_secret("d986ad-wslpe-vmware",prepare=True,store=base)
            file=base/"d986ad-wslpe-vmware/credential"
            file.chmod(0o644)
            with self.assertRaises(ValueError):
                operator_secret("d986ad-wslpe-vmware",store=base)
            file.chmod(0o600)
            linked=base/"d986ad-wslpe-vmware/linked"
            linked.symlink_to(file)
            self.assertTrue(linked.is_symlink())
            base.chmod(0o755)
            with self.assertRaises(ValueError):
                operator_secret("d986ad-wslpe-vmware",store=base)

    def test_wslpe_operator_playbook_is_explicitly_guarded(self):
        plays=yaml.safe_load(PLAY.read_text(encoding="utf-8"))
        self.assertEqual([x["hosts"] for x in plays],["localhost","wslpe"])
        checks=" ".join(plays[0]["tasks"][0]["ansible.builtin.assert"]["that"])
        for requirement in ("groups.get('wslpe'","groups.get('dc'",
                            "groups.get('domain'","wslpe_operator_handoff_approved",
                            "KINGDOMS_WSLPE_OPERATOR_PASSWORD"):
            self.assertIn(requirement,checks)
        source=PLAY.read_text(encoding="utf-8")
        for expected in ("WSLPE-WS01", "PartOfDomain","lpe.trainee",
                         "kingdom.operator", "update_password: on_create",
                         "no_log: true","SID 'S-1-5-32-544'"):
            self.assertIn(expected,source)
        for forbidden in ("Disable-LocalUser","Set-LocalUser","NORTH\\",
                          "10.4.10.31","Restart-Service","vmrun",
                          "vagrant up","ansible/roles/windows_lpe"):
            self.assertNotIn(forbidden,source)

    def test_local_credential_cli_has_no_windows_mutation(self):
        source=CLI.read_text(encoding="utf-8")
        self.assertIn('args.prepare',source)
        self.assertIn('exact_native_id()',source)
        self.assertIn('operator_secret(ident,prepare=True)',source)
        for forbidden in ("ansible-playbook","winrm.Session","vmrun stop",
                          "disable_vagrant","NORTH-WS01","print(secret)"):
            self.assertNotIn(forbidden,source)

if __name__=="__main__":
    unittest.main()
