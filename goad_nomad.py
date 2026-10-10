"""GOAD_NOMAD console entry point.

This module deliberately subclasses the upstream-style ``goad.py`` console
rather than duplicating the project controller. ``./goad.sh`` remains the
canonical entry point while GOAD_NOMAD can add segmented-network operations
without making future upstream merges unnecessarily invasive.
"""

import argparse
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time

from goad.log import Log
from goad.course_catalog import refuse_course_mutation
from goad.menu import print_menu_entry, print_menu_title
from goad.utils import PROVIDED, READY


_upstream = runpy.run_path(
    str(Path(__file__).with_name('goad.py')),
    run_name='goad_upstream_console',
)

BaseGoad = _upstream['Goad']
print_logo = _upstream['print_logo']


class GoadNomad(BaseGoad):
    """GOAD console plus GOAD_NOMAD segmented-network lifecycle commands."""

    @staticmethod
    def _format_elapsed(seconds):
        total = max(0, int(seconds))
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f'{hours}h {minutes:02d}m {secs:02d}s'
        if minutes:
            return f'{minutes}m {secs:02d}s'
        return f'{secs}s'

    def _start_install_sudo_keepalive(self, stop_event):
        """Prime sudo once and keep the ticket alive for a long Kingdoms install.

        Full clean installations routinely take around two hours. Authentication
        must therefore happen before any lifecycle state changes, not halfway
        through final isolation while the operator may be away. The keepalive is
        deliberately non-interactive after the initial ``sudo -v``; if the ticket
        becomes invalid, the existing provider fail-closed sudo gates remain the
        authority and refuse the next privileged transition instead of prompting.
        """
        if self._nomad_provider() is None:
            return True, None, None

        Log.info(
            'GOAD Kingdoms: refreshing sudo credentials once for the unattended install lifecycle'
        )
        try:
            subprocess.run(
                ['sudo', '-k'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            prime = subprocess.run(['sudo', '-v'], check=False)
        except OSError as exc:
            Log.error(f'GOAD Kingdoms: unable to initialize sudo credentials: {exc}')
            return False, None, None

        if prime.returncode != 0:
            Log.error(
                'GOAD Kingdoms: sudo authentication failed before install state changes; aborting'
            )
            return False, None, None

        lost_event = threading.Event()

        def keepalive():
            while not stop_event.wait(60):
                try:
                    refresh = subprocess.run(
                        ['sudo', '-n', '-v'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False,
                    )
                except OSError as exc:
                    lost_event.set()
                    Log.error(f'GOAD Kingdoms: sudo keepalive failed: {exc}')
                    return

                if refresh.returncode != 0:
                    lost_event.set()
                    detail = refresh.stderr.strip()
                    suffix = f': {detail}' if detail else ''
                    Log.error(
                        'GOAD Kingdoms: sudo keepalive lost its authenticated ticket; '
                        f'future privileged transitions will fail closed{suffix}'
                    )
                    return

        keepalive_thread = threading.Thread(
            target=keepalive,
            name='goad-kingdoms-sudo-keepalive',
            daemon=True,
        )
        keepalive_thread.start()
        Log.success(
            'GOAD Kingdoms: sudo credentials primed; non-interactive keepalive active every 60s'
        )
        return True, lost_event, keepalive_thread

    def _run_with_install_timer(self, operation):
        """Run an install operation with visible timer and sudo heartbeats.

        Vagrant/WinRM can legitimately spend many minutes booting older Windows
        guests. A periodic elapsed-time line keeps that wait observable without
        changing Vagrant's own output or timeout semantics. Segmented Kingdoms
        installs also keep the explicitly primed sudo ticket alive for the whole
        lifecycle so a two-hour unattended build cannot stop for a late password.
        """
        if getattr(self, '_install_timer_active', False):
            return operation()

        self._install_timer_active = True
        self._install_phase = 'starting'
        started = time.monotonic()
        stop_event = threading.Event()

        sudo_ok, sudo_lost_event, sudo_thread = self._start_install_sudo_keepalive(
            stop_event
        )
        if not sudo_ok:
            self._install_phase = 'idle'
            self._install_timer_active = False
            return False

        def heartbeat():
            while not stop_event.wait(60):
                elapsed = self._format_elapsed(time.monotonic() - started)
                phase = getattr(self, '_install_phase', 'unknown')
                Log.info(f'GOAD_NOMAD TIMER: {elapsed} elapsed | phase: {phase}')

        timer_thread = threading.Thread(
            target=heartbeat,
            name='goad-nomad-install-timer',
            daemon=True,
        )
        timer_thread.start()
        Log.info('GOAD_NOMAD TIMER: install timer started (heartbeat every 60s)')

        try:
            result = operation()
            if sudo_lost_event is not None and sudo_lost_event.is_set():
                Log.error(
                    'GOAD Kingdoms: sudo keepalive was lost during the lifecycle; '
                    'refusing to report the install as successful'
                )
                return False
            return result
        finally:
            stop_event.set()
            timer_thread.join(timeout=1)
            if sudo_thread is not None:
                sudo_thread.join(timeout=1)
            elapsed = self._format_elapsed(time.monotonic() - started)
            Log.info(f'GOAD_NOMAD TIMER: install command finished after {elapsed}')
            self._install_phase = 'idle'
            self._install_timer_active = False

    def _configured_provider(self):
        current = self.lab_manager.get_current_instance_provider()
        if current is not None:
            return current

        lab = self.lab_manager.get_lab(self.lab_manager.get_current_lab_name())
        if lab is None:
            return None
        return lab.get_provider(self.lab_manager.get_current_provider_name())

    def _nomad_provider(self, require_instance=False):
        if require_instance:
            provider = self.lab_manager.get_current_instance_provider()
        else:
            provider = self._configured_provider()

        if provider is None:
            return None

        check = getattr(provider, 'is_goad_nomad_segmented', None)
        if callable(check) and check():
            return provider
        return None

    def _course_preview_blocked(self, action):
        lab = self.lab_manager.get_current_lab_name()
        if refuse_course_mutation(lab, action):
            Log.error(
                f'Kingdoms {lab}: {action} refused — course is listed as PREVIEW. '
                'The independent provider/instance is not released yet.'
            )
            return True
        return False

    def do_create(self, arg=''):
        """Create a new instance, with an explicit non-interactive CLI path.

        Interactive console installs retain the upstream confirmation prompt.
        A command-line -t install is already an explicit operator action and
        must not block or silently abort because stdin is not a TTY.
        """
        if self._course_preview_blocked("install/create"):
            return False
        if arg != '--non-interactive':
            return super().do_create(arg)

        if self.lab_manager.get_current_instance() is not None:
            return self.do_install_instance()

        Log.success('Current Settings')
        self.lab_manager.current_settings.show()
        print()
        Log.info(
            'GOAD Kingdoms: explicit CLI install accepted; '
            'creating the lab without an interactive confirmation prompt'
        )
        Log.info('Create instance folder')
        if not self.lab_manager.create_instance():
            Log.error('Instance creation failed')
            return False

        return self.do_install_instance()
    def do_install(self, arg=''):
        """Run a full install and return success only for an installed instance."""
        if self._course_preview_blocked("install"):
            return False
        result = self._run_with_install_timer(lambda: self.do_create(arg))
        if result is False:
            return False

        instance = self.lab_manager.get_current_instance()
        return instance is not None and instance.get_status() == READY

    def do_provide(self, arg=''):
        """Run the provider and return the result from *this* attempt.

        Stock GOAD's interactive install path historically checks the persisted
        instance status after ``do_provide``. On a retry, an instance may still
        carry ``ready for provisioning`` from an earlier successful provider
        run. If the current provider attempt then fails, that stale status can
        incorrectly allow Ansible to start against partially available VMs.

        GOAD_NOMAD treats the current provider return value as authoritative.
        """
        if self._course_preview_blocked("provide"):
            return False
        provider = self.lab_manager.get_current_instance_provider()
        if provider is None:
            Log.error('No provider loaded for the current instance')
            return False

        self._install_phase = 'provider bring-up / VM readiness'
        phase_started = time.monotonic()
        result = provider.install()
        phase_elapsed = self._format_elapsed(time.monotonic() - phase_started)

        if not result:
            Log.error(
                f'GOAD_NOMAD: provider bring-up failed after {phase_elapsed}; '
                'Ansible provisioning will not start'
            )
            return False

        Log.success(f'GOAD_NOMAD TIMER: provider bring-up completed in {phase_elapsed}')
        self.lab_manager.get_current_instance().set_status(PROVIDED)

        # Preserve upstream dynamic-IP behaviour for providers that need it.
        if getattr(provider, 'update_ip_range', False):
            Log.info('Update IP range')
            new_range = provider.get_ip_range()
            if new_range is not None:
                Log.info(f'new range : {new_range}')
                self.lab_manager.get_current_instance().update_ip_range(new_range)
                Log.info('reload instance')
                instance_id = self.lab_manager.get_current_instance_id()
                self.do_load(instance_id)
                self.refresh_prompt()

        return True

    def do_install_instance(self, arg=''):
        """Install/retry an existing instance without trusting stale status."""
        if self._course_preview_blocked("install_instance"):
            return False
        if not getattr(self, '_install_timer_active', False):
            return self._run_with_install_timer(
                lambda: self._do_install_instance(arg)
            )
        return self._do_install_instance(arg)

    def _do_install_instance(self, arg=''):
        if self._course_preview_blocked("install_instance"):
            return False
        Log.info('Launch providing')
        if not self.do_provide():
            Log.error('Providing error stop')
            self.refresh_prompt()
            return False

        Log.info('Prepare jumpbox if needed')
        self.do_prepare_jumpbox()
        Log.info('Launch provisioning')
        provision_result = self.do_provision_lab()
        if provision_result:
            for extension_name in self.lab_manager.current_settings.extensions_name:
                self._install_phase = f'extension provisioning: {extension_name}'
                Log.info(f'Start installation of extension : {extension_name}')
                self.do_install_extension(extension_name)
        self.refresh_prompt()
        return provision_result

    def do_provision_lab(self, arg=''):
        """Provision through the GOAD_NOMAD lifecycle and set READY only on success.

        The Ansible provisioner owns both provisioning-plane preparation and the
        single provider ``finalize_install`` call for a full lab run. Calling the
        upstream controller here would add the legacy ``time.ctime`` duration,
        while calling ``finalize_install`` again would repeat the exercise-mode
        transition. Keep one lifecycle owner and one human-readable timer.
        """
        if self._course_preview_blocked("provision_lab"):
            return False
        if self.lab_manager.get_current_instance_provider() is None:
            Log.error('No provider loaded for the current instance')
            return False

        phase_started = time.monotonic()
        self._install_phase = 'Ansible provisioning + final isolation'
        provision_result = self.lab_manager.get_current_instance_provisioner().run()
        if not provision_result:
            elapsed = self._format_elapsed(time.monotonic() - phase_started)
            Log.error(f'GOAD_NOMAD TIMER: provisioning failed after {elapsed}')
            # The provisioner returns False if management preparation, Ansible,
            # or final exercise isolation fails. Never mark that state READY.
            return False

        self.lab_manager.get_current_instance().set_status(READY)
        elapsed = self._format_elapsed(time.monotonic() - phase_started)
        Log.success(
            f'GOAD_NOMAD TIMER: provisioning + final isolation completed in {elapsed}'
        )
        return True

    def do_provision(self, arg):
        if self._course_preview_blocked("provision"):
            return False
        return super().do_provision(arg)

    def do_provision_lab_from(self, arg):
        if self._course_preview_blocked("provision_lab_from"):
            return False
        return super().do_provision_lab_from(arg)

    def do_create_empty(self, arg=''):
        if self._course_preview_blocked("create_empty"):
            return False
        return super().do_create_empty(arg)

    def do_ws01(self, arg=''):
        """Materialize and provision only the clean M2 WS01 foundation."""
        if self._course_preview_blocked("ws01"):
            return False
        return self._run_with_install_timer(self._do_ws01)

    def _do_ws01(self):
        provider = self._nomad_provider(require_instance=True)
        if provider is None:
            Log.error('Load a GOAD/VMware instance before installing GOAD-WS01')
            return False

        provider_result = False
        provision_result = False
        isolation_result = False
        try:
            self._install_phase = 'GOAD-WS01 VM materialization + management readiness'
            provider_result = provider.install()
            if provider_result:
                self._install_phase = 'GOAD-WS01 clean workstation provisioning'
                provision_result = (
                    self.lab_manager.get_current_instance_provisioner().run('ws01.yml')
                )
        finally:
            self._install_phase = 'GOAD-WS01 final exercise isolation'
            isolation_result = provider.finalize_install()

        if not provider_result:
            if isolation_result:
                Log.error(
                    'GOAD Kingdoms: GOAD-WS01 provider bring-up failed; '
                    'exercise isolation was restored'
                )
            else:
                Log.error(
                    'GOAD Kingdoms: GOAD-WS01 provider bring-up failed and '
                    'exercise isolation restoration also failed'
                )
            return False
        if not provision_result:
            Log.error('GOAD Kingdoms: GOAD-WS01 Ansible provisioning failed')
            return False
        if not isolation_result:
            Log.error('GOAD Kingdoms: GOAD-WS01 provisioned but exercise isolation failed')
            return False

        Log.success(
            'GOAD Kingdoms: GOAD-WS01 clean foundation installed and exercise isolation restored'
        )
        return True

    def do_help(self, arg):
        super().do_help(arg)
        if self._nomad_provider() is not None:
            print_menu_title('GOAD_NOMAD Network')
            print_menu_entry('network', 'show the segmented network profile')
            if self.lab_manager.get_current_instance() is not None:
                print_menu_entry('mode [status|provisioning|exercise]', 'show or change the lab network mode')
                print_menu_entry('validate', 'run the complete Milestone 1 network validation')
                print_menu_entry('ws01', 'install the clean Milestone 2 WS01 foundation')

    def do_network(self, arg=''):
        provider = self._nomad_provider()
        if provider is None:
            Log.error('The current lab/provider does not use the GOAD_NOMAD segmented profile')
            return

        scope = provider.get_network_scope()
        Log.success(f'GOAD_NOMAD Network Scope: {scope}')
        for zone, vmnet, subnet in provider.get_network_details():
            Log.info(f'{zone:<15} {vmnet:<8} {subnet}')

        if self.lab_manager.get_current_instance() is not None:
            Log.info(f'Runtime Mode     : {provider.get_runtime_mode()}')

    def do_mode(self, arg='status'):
        provider = self._nomad_provider(require_instance=True)
        if provider is None:
            Log.error('Load a GOAD/VMware instance before managing GOAD_NOMAD mode')
            return

        mode = (arg or 'status').strip().lower()
        if mode == 'status':
            Log.info(f'GOAD_NOMAD Mode: {provider.get_runtime_mode()}')
            return

        if mode not in ('provisioning', 'exercise'):
            Log.error('Usage: mode [status|provisioning|exercise]')
            return

        if provider.set_runtime_mode(mode):
            Log.success(f'GOAD_NOMAD mode is now {mode}')
        else:
            Log.error(f'Failed to enter GOAD_NOMAD {mode} mode')

    def complete_mode(self, text, line, begidx, endidx):
        options = ['status', 'provisioning', 'exercise']
        if not text:
            return options
        return [option for option in options if option.startswith(text)]

    def do_validate(self, arg=''):
        provider = self._nomad_provider(require_instance=True)
        if provider is None:
            Log.error('Load a GOAD/VMware instance before running GOAD_NOMAD validation')
            return

        if provider.validate_runtime():
            # A full runtime validation proves the instance is provisioned and
            # finishes in exercise mode. Repair stale stock-GOAD metadata from
            # development-era instances only after that proof succeeds.
            self.lab_manager.get_current_instance().set_status(READY)
            Log.success('GOAD_NOMAD runtime validation passed; instance status is installed')
        else:
            Log.error('GOAD_NOMAD runtime validation failed')

    def do_destroy(self, arg=''):
        """Destroy the loaded instance and return the provider result.

        Interactive console use keeps the provider's normal confirmation.
        Non-interactive CLI dispatch uses the provider's explicit forced
        destroy entry point so Vagrant never tries to prompt without a TTY.
        """
        provider = self.lab_manager.get_current_instance_provider()
        if provider is None:
            Log.error('No provider loaded for the current instance')
            return False

        if arg == '--non-interactive':
            destroy_non_interactive = getattr(provider, 'destroy_non_interactive', None)
            if callable(destroy_non_interactive):
                return bool(destroy_non_interactive())

        return bool(provider.destroy())

    def do_status(self, arg=''):
        super().do_status(arg)
        provider = self._nomad_provider(require_instance=True)
        if provider is not None:
            Log.info(f'Network Scope : {provider.get_network_scope()}')
            Log.info(f'Network Mode  : {provider.get_runtime_mode()}')

    def do_set_ip_range(self, arg):
        if self._nomad_provider() is not None:
            Log.warning('GOAD/VMware uses the fixed GOAD_NOMAD segmented profile')
            Log.info('Network scope: 10.4.0.0/16; use "network" to show its four zones')
            return
        super().do_set_ip_range(arg)


def parse_args():
    task_help = 'tasks available: install/check/start/stop/restart/destroy/status/snapshot/reset/validate/ws01'
    parser = argparse.ArgumentParser(
        prog='goad_nomad.py',
        description='GOAD_NOMAD lab management console.',
        epilog='''
Examples:
 - Launch GOAD_NOMAD interactive console: ./goad.sh
 - Install default segmented GOAD on VMware: ./goad.sh -t install -l GOAD -p vmware
 - Validate an installed instance: ./goad.sh -t validate -i <instance_id>
''',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-t', '--task', help=task_help, required=False)
    parser.add_argument('-l', '--lab', help='lab to use (default: GOAD)', default='GOAD', required=False)
    parser.add_argument('-p', '--provider', help='provider to use (default: vmware)', default='vmware', required=False)
    parser.add_argument('-ip', '--ip_range', help='legacy flat-network prefix; ignored by segmented GOAD/VMware', default='', required=False)
    parser.add_argument('-m', '--method', help='deploy method to use (default: local)', default='local', required=False)
    parser.add_argument('-i', '--instance', help='use a specific instance (use default if not selected)', required=False)
    parser.add_argument('-e', '--extensions', help='extensions to use', action='append', required=False)
    parser.add_argument('-a', '--ansible_only', help='run only provisioning (ansible) on instance (-i) (for task install only)', required=False)
    parser.add_argument('-r', '--run_playbook', help='run only one ansible playbook on instance (-i) (for task install only)', required=False)
    parser.add_argument('-d', '--disable_dependencies', help='disable_dependencies', action='append', required=False)
    return parser.parse_args()


def _dispatch_task(goad, args):
    """Preserve the stock goad.py non-interactive task behaviour."""
    if args.instance is not None:
        goad.do_load(args.instance)

    if args.run_playbook is not None or args.ansible_only is not None:
        if args.instance is None:
            Log.error('Instance must be selected (-i) to use --run_playbook (-r) or --ansible_only (-a)')
            return 1

    if args.task == 'install':
        if args.instance is not None:
            if args.run_playbook is not None:
                goad.do_provision(args.run_playbook)
            elif args.ansible_only:
                if not goad.do_provision_lab():
                    return 1
            else:
                if not goad.do_install_instance():
                    return 1
        else:
            if not goad.do_install('--non-interactive'):
                return 1
    elif args.task == 'check':
        goad.do_check()
    elif args.task == 'start':
        if not goad.do_start():
            return 1
    elif args.task == 'stop':
        if not goad.do_stop():
            return 1
    elif args.task == 'restart':
        if not goad.do_stop():
            return 1
        if not goad.do_start():
            return 1
    elif args.task == 'destroy':
        if not goad.do_destroy('--non-interactive'):
            return 1
    elif args.task == 'status':
        goad.do_status()
    elif args.task == 'snapshot':
        if not goad.do_snapshot():
            return 1
    elif args.task == 'reset':
        if not goad.do_reset():
            return 1
    elif args.task == 'validate':
        goad.do_validate()
    elif args.task == 'ws01':
        if not goad.do_ws01():
            return 1
    elif args.task == 'mode':
        goad.do_mode('status')
    elif args.task == 'show':
        pass
    else:
        Log.error(f'Unknown task: {args.task}')
        return 1
    return 0


def main():
    print_logo()
    args = parse_args()
    goad = GoadNomad(args)

    if args is None or args.task is None:
        goad.cmdloop()
        return 0

    return _dispatch_task(goad, args)


if __name__ == '__main__':
    sys.exit(main())