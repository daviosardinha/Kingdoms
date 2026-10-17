"""WSLPE-only randomized credential overlay regression (never touches Windows)."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import stat
import unittest
import yaml

from kingdoms.wslpe_fixture_credentials import (
    fixture_vars_file, _template, FIXTURES, _valid
)

ROOT=Path(__file__).resolve().parents[1]
ADAPTER=ROOT/"ansible/wslpe-lpe-test.yml"
UNSET=ROOT/"ansible/wslpe-secrets-unset.yml"
FASTTRACK=ROOT/"scripts/wslpe-fast-track-20.py"
CLI=ROOT/"scripts/wslpe-operator-secret.py"
FROZEN=ROOT/"ansible/roles/windows_lpe/defaults/main.yml"

class FixtureSecretTests(unittest.TestCase):
    def test_unique_random_passwords_for_five_fixtures_and_reuse(self):
        with TemporaryDirectory() as tmp:
            store=Path(tmp)/"vault"
            first=fixture_vars_file("d986ad-wslpe-vmware",prepare=True,store=store)
            original=first.read_bytes()
            data=json.loads(original)
            self.assertEqual(set(data),set(FIXTURES)|{
                "wslpe_fixture_private","wslpe_fixture_instance_id"})
            self.assertEqual(len({data[key]["password"] for key in FIXTURES}),5)
            # Private generation must not mutate source-default snapshots.
            base=_template()
            self.assertEqual(base, _template())
            for key in FIXTURES:
                self.assertNotEqual(data[key]["password"],base[key]["password"])
                self.assertEqual(
                    {x:y for x,y in data[key].items() if x!="password"},
                    {x:y for x,y in base[key].items() if x!="password"})
            self.assertEqual(stat.S_IMODE(store.stat().st_mode),0o700)
            self.assertEqual(stat.S_IMODE(first.stat().st_mode),0o600)
            again=fixture_vars_file("d986ad-wslpe-vmware",store=store)
            self.assertEqual(first,again)
            self.assertEqual(first.read_bytes(),original)
            second=fixture_vars_file("a102ff-wslpe-vmware",prepare=True,store=store)
            other=json.loads(second.read_text())
            for key in FIXTURES:
                self.assertNotEqual(data[key]["password"],other[key]["password"])

    def test_missing_unsafe_and_tampered_overlay_fail_closed(self):
        with TemporaryDirectory() as tmp:
            store=Path(tmp)/"vault"
            with self.assertRaises(ValueError):
                fixture_vars_file("d986ad-wslpe-vmware",store=store)
            path=fixture_vars_file("d986ad-wslpe-vmware",prepare=True,store=store)
            document=json.loads(path.read_text())
            document["windows_lpe_unattend_credentials"]["password"]=_template()[
                "windows_lpe_unattend_credentials"]["password"]
            path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                fixture_vars_file("d986ad-wslpe-vmware",store=store)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                fixture_vars_file("d986ad-wslpe-vmware",store=store)

    def test_absent_secrets_only_permit_status_and_no_role_changes(self):
        plays=yaml.safe_load(ADAPTER.read_text(encoding="utf-8"))
        self.assertEqual([p["hosts"] for p in plays],["localhost","wslpe"])
        self.assertEqual(sum("vars_files" in p for p in plays),2)
        self.assertFalse(yaml.safe_load(UNSET.read_text())["wslpe_fixture_private"])
        source=ADAPTER.read_text(encoding="utf-8")
        self.assertIn("KINGDOMS_WSLPE_FIXTURE_VARS_FILE",source)
        self.assertIn("KINGDOMS_WSLPE_INSTANCE_ID",source)
        self.assertIn("wslpe_action != 'status'",source)
        self.assertIn("wslpe_fixture_private | default(false)",source)
        self.assertIn("windows_lpe_unattend_credentials is defined",source)
        self.assertNotIn("10.4.10.31",source)
        runner=FASTTRACK.read_text()
        self.assertIn('fixture_vars_file(inventory.parent.name, prepare=False)',runner)
        self.assertIn('env["KINGDOMS_WSLPE_FIXTURE_VARS_FILE"]',runner)
        self.assertIn('--prepare-fixtures',CLI.read_text())
        self.assertIn("password:",FROZEN.read_text())

if __name__=="__main__":
    unittest.main()
