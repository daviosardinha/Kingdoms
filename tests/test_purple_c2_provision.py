"""Offline behavioral tests for fresh PURPLE-C2 package provisioning.

Runs the real shell provisioner with fake package-manager commands.
Never installs system packages or modifies an actual VM.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "ad/PURPLE/providers/vmware/provision-c2-tools.sh"


class PurpleC2ProvisionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.bin_dir = self.base / "bin"
        self.bin_dir.mkdir()
        self.state = self.base / "installed"
        self.state.mkdir()
        self.apt_log = self.base / "apt.log"
        self.apt_log.touch()
        self.env = os.environ.copy()
        self.env.update({
            "PATH": str(self.bin_dir) + os.pathsep + "/usr/bin:/bin",
            "PURPLE_TEST_STATE": str(self.state),
            "PURPLE_TEST_APT_LOG": str(self.apt_log),
            "PURPLE_TEST_UID": "0",
        })
        self.stub("id", '#!/bin/bash\nprintf "%s\\n" "${PURPLE_TEST_UID:-0}"\n')
        self.stub("dpkg-query", """#!/bin/bash
pkg="${@: -1}"
if [[ -f "$PURPLE_TEST_STATE/$pkg" ]]; then
    printf "install ok installed"
else
    exit 1
fi
""")
        self.stub("apt-get", """#!/bin/bash
printf '%s\\n' "$*" >> "$PURPLE_TEST_APT_LOG"
case "$1" in
    update) exit "${PURPLE_TEST_UPDATE_EXIT:-0}" ;;
    install)
        if [[ "${PURPLE_TEST_INSTALL_EXIT:-0}" != 0 ]]; then exit 1; fi
        for pkg in "$@"; do
            if [[ "$pkg" == git || "$pkg" == tcpdump ]]; then
                touch "$PURPLE_TEST_STATE/$pkg"
            fi
        done
        ;;
    *) exit 2 ;;
esac
""")
        self.stub("tcpdump", "#!/bin/bash\nexit 0\n")
        self.stub("git", "#!/bin/bash\nexit 0\n")

    def stub(self, name, content):
        path = self.bin_dir / name
        path.write_text(content)
        path.chmod(0o755)

    def installed(self, *packages):
        for package in packages:
            (self.state / package).touch()

    def run_provisioner(self):
        return subprocess.run(
            ["/bin/bash", str(PROVISION)],
            env=self.env, text=True, capture_output=True, check=False,
        )

    def apt_commands(self):
        return self.apt_log.read_text().splitlines()

    def assert_ready(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PURPLE_C2_TCPDUMP_READY=PASS", result.stdout)
        self.assertIn("PURPLE_C2_GIT_READY=PASS", result.stdout)

    def test_fresh_guest_installs_both_packages(self):
        result = self.run_provisioner()
        self.assert_ready(result)
        self.assertEqual(
            self.apt_commands(),
            ["update", "install -y --no-install-recommends tcpdump git"],
        )
        self.assertTrue((self.state / "git").exists())
        self.assertTrue((self.state / "tcpdump").exists())

    def test_missing_git_on_existing_tcpdump_guest(self):
        self.installed("tcpdump")
        result = self.run_provisioner()
        self.assert_ready(result)
        self.assertEqual(
            self.apt_commands(),
            ["update", "install -y --no-install-recommends tcpdump git"],
        )
        self.assertTrue((self.state / "git").exists())

    def test_healthy_reprovision_does_not_run_apt(self):
        self.installed("tcpdump", "git")
        self.assert_ready(self.run_provisioner())
        self.assert_ready(self.run_provisioner())
        self.assertEqual(self.apt_commands(), [])

    def test_apt_update_failure_prevents_success(self):
        self.env["PURPLE_TEST_UPDATE_EXIT"] = "42"
        result = self.run_provisioner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.apt_commands(), ["update"])
        self.assertNotIn("PURPLE_C2_GIT_READY=PASS", result.stdout)

    def test_apt_install_failure_prevents_success(self):
        self.env["PURPLE_TEST_INSTALL_EXIT"] = "1"
        result = self.run_provisioner()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.apt_commands(),
            ["update", "install -y --no-install-recommends tcpdump git"],
        )
        self.assertNotIn("PURPLE_C2_GIT_READY=PASS", result.stdout)

    def test_non_root_execution_is_rejected(self):
        self.env["PURPLE_TEST_UID"] = "1000"
        result = self.run_provisioner()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires root", result.stderr)
        self.assertEqual(self.apt_commands(), [])


if __name__ == "__main__":
    unittest.main()
