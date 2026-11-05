"""PURPLE fixed trainee password and Wazuh one-time admin credential regression."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PURPLE = ROOT / "ad/PURPLE"
GUEST = PURPLE / "providers/vmware/provision-sliver-trainee.sh"
WAZUH = PURPLE / "providers/vmware/provision-wazuh-all-in-one.sh"


class PurpleCredentialFixturesTests(unittest.TestCase):
    def test_known_trainee_crypt_hash_matches_documented_lab_password(self):
        source = GUEST.read_text()
        m = re.search(r"^FIXED_PASSWORD_HASH='([^']+)'$", source, flags=re.M)
        self.assertIsNotNone(m)
        expected = subprocess.check_output(
            ["openssl", "passwd", "-6", "-salt", "PurpleLab2026", "sliver123"],
            text=True,
        ).strip()
        self.assertEqual(m.group(1), expected)
        self.assertNotIn("sliver123", source)
        self.assertIn("chpasswd --encrypted", source)
        self.assertIn("PURPLE_SLIVER_TRAINEE_SUDO=DENIED", source)

    def test_wazuh_admin_parser_handles_official_password_file_format(self):
        source = WAZUH.read_text()
        start_mark = "| python3 -c '\n"
        end_mark = "\n')\" || fail"
        self.assertEqual(source.count(start_mark), 1)
        start = source.index(start_mark) + len(start_mark)
        end = source.index(end_mark, start)
        admin_parser = source[start:end]

        fixture = (
            "# Admin user for the web user interface and Wazuh indexer\n"
            "  indexer_username: 'admin'\n"
            "  indexer_password: 'EasyTest*42:part'\n"
            "# Wazuh dashboard internal user\n"
            "  indexer_username: 'kibanaserver'\n"
            "  indexer_password: 'other-pass'\n"
        )
        def parse(data):
            return subprocess.run(
                ["python3", "-c", admin_parser],
                input=data, text=True, capture_output=True,
                check=False,
            )
        result = parse(fixture)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "EasyTest*42:part")
        self.assertEqual(parse("indexer_username: 'admin'\nindexer_password: ''\n").returncode, 1)
        self.assertEqual(parse(fixture + "\nindexer_username: 'admin'\nindexer_password: 'second'\n").returncode, 1)

    def test_password_not_reprinted_when_wazuh_already_active(self):
        source = WAZUH.read_text()
        early = source.index('if [[ "$all_running" == true ]]')
        early_end = source.index('if [[ "$any_installed" == true ]]', early)
        self.assertIn('exit 0', source[early:early_end])
        self.assertNotIn("INITIAL PASSWORD - SAVE SECURELY", source[early:early_end])
        ready = source.index('if [[ "$ready" == true ]]')
        shown = source.index("INITIAL PASSWORD - SAVE SECURELY")
        self.assertLess(ready, shown)

    def test_documentation_explains_wazuh_exception(self):
        doc = (PURPLE / "DEPLOYMENT.md").read_text()
        self.assertIn("sliver123", doc)
        self.assertIn("generated", doc.lower())
        self.assertIn("INITIAL PASSWORD - SAVE SECURELY", doc)
        self.assertNotIn("purple-trainee-password.py", doc)


if __name__ == "__main__":
    unittest.main()
