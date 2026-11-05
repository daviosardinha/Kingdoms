"""Offline source regressions for PURPLE-LX01's standard Sliver trainee."""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PURPLE = ROOT / "ad/PURPLE/providers/vmware"
VAGRANT = PURPLE / "Vagrantfile"
PROVISION = PURPLE / "provision-sliver-trainee.sh"


class SliverTraineeSourceTests(unittest.TestCase):
    def test_shell_syntax_and_target_guard(self):
        subprocess.run(["bash", "-n", str(PROVISION)], check=True)
        script = PROVISION.read_text()
        self.assertIn('ACCOUNT="sliver.trainee"', script)
        self.assertIn('EXPECTED_IP="172.28.233.32/24"', script)
        self.assertIn('"ubuntu"', script)
        self.assertIn('"22.04"', script)
        self.assertIn('getent passwd vagrant', script)
        self.assertIn('[[ "$MODE" == "--ensure" || "$MODE" == "--verify" ]]', script)

    def test_idempotent_no_admin_and_real_login_checks(self):
        script = PROVISION.read_text()
        self.assertIn('if ! getent passwd "$ACCOUNT"', script)
        self.assertIn('useradd --badname --create-home --user-group', script)
        self.assertIn('--shell /bin/bash', script)
        self.assertIn('runuser -l "$ACCOUNT"', script)
        self.assertIn('sudo -n -l -U "$ACCOUNT"', script)
        self.assertIn('is not allowed to run sudo on', script)
        self.assertIn('PURPLE_SLIVER_TRAINEE_SUDO=DENIED', script)
        self.assertIn('PURPLE_SLIVER_TRAINEE_LOGIN_SHELL=PASS', script)
        self.assertIn('PURPLE_SLIVER_TRAINEE_HOME_EXEC=PASS', script)
        self.assertIn('PURPLE_SLIVER_TRAINEE_PASSWORD_LOGIN=CONFIGURED', script)
        self.assertIn('HASH_FILE="/home/vagrant/.purple-sliver-trainee.sha512"', script)
        self.assertIn('chpasswd --encrypted', script)
        self.assertIn('PASSWORD_HASH', script)
        self.assertIn('getent shadow "$ACCOUNT"', script)
        self.assertNotIn('REQUIRES_MANUAL_SETUP', script)
        self.assertNotIn('usermod -aG sudo', script)
        self.assertNotIn('NOPASSWD', script)
        self.assertNotIn('chpasswd', script)
        self.assertNotIn('passwd --stdin', script)

    def test_only_lx01_receives_the_new_provisioner(self):
        vm = VAGRANT.read_text()
        self.assertEqual(vm.count("provision-sliver-trainee.sh"), 1)
        start = vm.index(':name => "PURPLE-LX01"')
        end = vm.index(':name => "PURPLE-WAZUH"')
        self.assertIn('provision-sliver-trainee.sh', vm[start:end])
        self.assertNotIn('provision-sliver-trainee.sh', vm[:start])
        self.assertNotIn('provision-sliver-trainee.sh', vm[end:])
        self.assertLess(vm.index('provision-ubuntu-desktop.sh'), vm.index('provision-sliver-trainee.sh'))
        self.assertEqual(vm.count(':sliver_trainee_password_hash_file =>'), 1)
        self.assertIn('purple-lx01-trainee.sha512', vm[start:end])
        provider_template = (ROOT / "template/provider/vmware/Vagrantfile").read_text()
        self.assertIn('if box.has_key?(:sliver_trainee_password_hash_file)', provider_template)
        self.assertIn('target.vm.provision :file', provider_template)
        self.assertIn('File.stat(hash_source).mode & 0077', provider_template)
        self.assertIn('/home/vagrant/.purple-sliver-trainee.sha512', provider_template)
        self.assertLess(provider_template.index('target.vm.provision :file'),
                        provider_template.index('if box.has_key?(:provision_scripts)'))


if __name__ == "__main__":
    unittest.main()
