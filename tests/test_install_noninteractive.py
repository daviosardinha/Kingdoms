"""Regression coverage for explicit non-interactive CLI installs."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from goad_nomad import GoadNomad, _dispatch_task


class InstallNonInteractiveTests(unittest.TestCase):
    def _args(self):
        return SimpleNamespace(
            instance=None,
            run_playbook=None,
            ansible_only=None,
            task='install',
        )

    def test_cli_install_uses_non_interactive_create_path(self):
        goad = Mock()
        goad.do_install.return_value = True

        self.assertEqual(_dispatch_task(goad, self._args()), 0)
        goad.do_install.assert_called_once_with('--non-interactive')

    def test_cli_install_failure_propagates(self):
        goad = Mock()
        goad.do_install.return_value = False

        self.assertEqual(_dispatch_task(goad, self._args()), 1)
        goad.do_install.assert_called_once_with('--non-interactive')

    def test_north_resume_dispatch_uses_existing_instance_and_start_playbook(self):
        args = self._args()
        args.task = 'resume-north'
        args.instance = 'ac9fda-north-vmware'
        args.run_playbook = 'vulnerabilities.yml'
        console = Mock()
        console.do_resume_north.return_value = True
        self.assertEqual(_dispatch_task(console, args), 0)
        console.do_load.assert_called_once_with(args.instance)
        console.do_resume_north.assert_called_once_with('vulnerabilities.yml')
        console.do_install_instance.assert_not_called()
        console.do_install.assert_not_called()

    def test_north_resume_requires_explicit_instance_and_start_playbook(self):
        for instance, playbook, ansible_only in (
            (None, 'vulnerabilities.yml', None),
            ('ac9fda-north-vmware', None, None),
            ('ac9fda-north-vmware', 'vulnerabilities.yml', 'yes'),
        ):
            with self.subTest(instance=instance, playbook=playbook):
                args = self._args()
                args.task = 'resume-north'
                args.instance = instance
                args.run_playbook = playbook
                args.ansible_only = ansible_only
                console = Mock()
                self.assertEqual(_dispatch_task(console, args), 1)
                console.do_resume_north.assert_not_called()
                console.do_install.assert_not_called()

    def _north_resume_console(self):
        console = GoadNomad.__new__(GoadNomad)
        manager = Mock()
        manager.get_current_lab_name.return_value = 'NORTH'
        manager.get_current_provider_name.return_value = 'vmware'
        manager.get_current_instance.return_value = Mock()
        provider = Mock()
        provider._course1_unwired.return_value = False
        manager.get_current_instance_provider.return_value = provider
        provisioner = Mock()
        provisioner.get_playbook_list.return_value = [
            'build.yml', 'vulnerabilities.yml', 'phase01.yml',
            'ws01-lpe-install.yml', 'kingdoms-health-final.yml',
        ]
        provisioner.run_from.return_value = True
        manager.get_current_instance_provisioner.return_value = provisioner
        console.lab_manager = manager
        console.refresh_prompt = Mock()
        console._run_with_install_timer = Mock(side_effect=lambda callback: callback())
        return console, manager, provider, provisioner

    def test_north_resume_reuses_original_ansible_run_from_without_vagrant(self):
        console, manager, provider, provisioner = self._north_resume_console()
        self.assertTrue(console.do_resume_north('vulnerabilities.yml'))
        console._run_with_install_timer.assert_called_once()
        provider._course1_unwired.assert_called_once()
        provisioner.run_from.assert_called_once_with('vulnerabilities.yml')
        manager.get_current_instance.return_value.set_status.assert_called_once()
        console.refresh_prompt.assert_called_once()

    def test_north_resume_fails_closed_on_owner_or_playbook_or_anomaly(self):
        console, manager, provider, provisioner = self._north_resume_console()
        provider._course1_unwired.return_value = True
        self.assertFalse(console.do_resume_north('vulnerabilities.yml'))
        provisioner.run_from.assert_not_called()
        manager.get_current_instance.return_value.set_status.assert_not_called()
        provider._course1_unwired.return_value = False
        self.assertFalse(console.do_resume_north('not-our-playbook.yml'))
        provisioner.run_from.assert_not_called()
        provisioner.run_from.return_value = False
        self.assertFalse(console.do_resume_north('vulnerabilities.yml'))
        manager.get_current_instance.return_value.set_status.assert_not_called()
        manager.get_current_lab_name.return_value = 'GOAD'
        self.assertFalse(console.do_resume_north('vulnerabilities.yml'))
        provisioner.run_from.assert_called_once()

    def test_first_playbook_resume_uses_scoped_pre_ad_gate(self):
        console, manager, provider, provisioner = self._north_resume_console()
        provider.get_runtime_mode.return_value = 'unknown'
        observed = []
        def run(playbook):
            observed.append((playbook, provider._north_pre_ad_resume_authorized))
            return True
        provisioner.run_from.side_effect = run
        with patch('goad_nomad.assert_pre_ad_north_resume',
                   return_value=('exact receipt',)) as proof:
            self.assertTrue(console.do_resume_north('build.yml'))
        proof.assert_called_once()
        self.assertEqual(observed, [('build.yml', True)])
        self.assertIs(provider._north_pre_ad_resume_authorized, False)
        provider.install.assert_not_called()

    def test_first_playbook_resume_rejects_missing_receipt(self):
        console, manager, provider, provisioner = self._north_resume_console()
        provider.get_runtime_mode.return_value = 'unknown'
        with patch('goad_nomad.assert_pre_ad_north_resume',
                   side_effect=Exception('unexpected')) as proof:
            # Fail closed without invoking provider/Ansible. A *typed*
            # PreADResumeError is the expected user-facing case.
            from goad.course1_pre_ad_resume import PreADResumeError
            proof.side_effect = PreADResumeError('receipt not trusted')
            self.assertFalse(console.do_resume_north('build.yml'))
        provisioner.run_from.assert_not_called()
        manager.get_current_instance.return_value.set_status.assert_not_called()

    def test_scoped_pre_ad_grant_cleared_when_ansible_fails(self):
        console, manager, provider, provisioner = self._north_resume_console()
        provider.get_runtime_mode.return_value = 'unknown'
        provisioner.run_from.return_value = False
        with patch('goad_nomad.assert_pre_ad_north_resume', return_value=('ok',)):
            self.assertFalse(console.do_resume_north('build.yml'))
        self.assertIs(provider._north_pre_ad_resume_authorized, False)
        manager.get_current_instance.return_value.set_status.assert_not_called()

    def test_non_interactive_create_skips_confirmation_and_creates_instance(self):
        goad = GoadNomad.__new__(GoadNomad)
        manager = Mock()
        manager.get_current_instance.return_value = None
        manager.create_instance.return_value = True
        manager.current_settings = Mock()
        goad.lab_manager = manager
        goad.do_install_instance = Mock(return_value=True)

        self.assertTrue(goad.do_create('--non-interactive'))
        manager.current_settings.show.assert_called_once_with()
        manager.create_instance.assert_called_once_with()
        goad.do_install_instance.assert_called_once_with()

    def test_non_interactive_create_stops_if_instance_creation_fails(self):
        goad = GoadNomad.__new__(GoadNomad)
        manager = Mock()
        manager.get_current_instance.return_value = None
        manager.create_instance.return_value = False
        manager.current_settings = Mock()
        goad.lab_manager = manager
        goad.do_install_instance = Mock(return_value=True)

        self.assertFalse(goad.do_create('--non-interactive'))
        goad.do_install_instance.assert_not_called()


if __name__ == '__main__':
    unittest.main()
