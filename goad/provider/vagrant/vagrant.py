import subprocess
import threading
import time

from goad.log import Log
from goad.provider.provider import Provider


class VagrantProvider(Provider):

    def __init__(self, lab_name):
        super().__init__(lab_name)
        self.jumpbox_setup_script = 'setup_local_jumpbox.sh'

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

    def check(self):
        checks = [
            self.command.check_vagrant(),
            self.command.check_disk(),
            self.command.check_ram(),
            self.command.check_ansible(),
            self.command.check_vagrant_plugin('vagrant-reload')
        ]
        return all(checks)

    def install(self):
        return self.command.run_vagrant(['up'], self.path)

    def destroy(self):
        return self.command.run_vagrant(['destroy'], self.path)

    def destroy_non_interactive(self):
        """Destroy Vagrant resources without requiring an interactive TTY."""
        return self.command.run_vagrant(['destroy', '-f'], self.path)

    def start(self, vm_name=None):
        # GOAD_NOMAD's segmented VMware provider needs more than a bare
        # ``vagrant up``. Protected-zone routing may need to be opened
        # temporarily, older Windows guests may require VMware Tools recovery,
        # and all six Ansible/WinRM endpoints must be proven healthy before the
        # lifecycle command can report success. Reuse that provider's hardened
        # install/bring-up path, then restore the mode that was recorded before
        # start. All other Vagrant providers retain the upstream behaviour.
        segmented = getattr(self, 'is_goad_nomad_segmented', None)
        if callable(segmented) and segmented():
            get_mode = getattr(self, 'get_runtime_mode', None)
            set_mode = getattr(self, 'set_runtime_mode', None)
            prepare_install = getattr(self, 'prepare_install', None)
            original_mode = get_mode() if callable(get_mode) else 'unknown'
            started = time.monotonic()

            # A segmented start can take longer than the host's normal sudo
            # timestamp lifetime. Prime sudo before touching any VM and refresh
            # it non-interactively until the lifecycle has restored the original
            # network mode. This prevents a six-minute bring-up from failing only
            # when temporary provisioning routes are finally required.
            Log.info(
                'GOAD Kingdoms: authenticating sudo before segmented start state changes'
            )
            try:
                prime = subprocess.run(['sudo', '-v'], check=False)
            except OSError as exc:
                Log.error(f'GOAD Kingdoms: unable to initialize sudo for start: {exc}')
                return False
            if prime.returncode != 0:
                Log.error(
                    'GOAD Kingdoms: sudo authentication failed before start; '
                    'no VM state changes were attempted'
                )
                return False

            sudo_stop = threading.Event()
            sudo_lost = threading.Event()

            def sudo_keepalive():
                while not sudo_stop.wait(60):
                    try:
                        refresh = subprocess.run(
                            ['sudo', '-n', '-v'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            text=True,
                            check=False,
                        )
                    except OSError as exc:
                        sudo_lost.set()
                        Log.error(f'GOAD Kingdoms: start sudo keepalive failed: {exc}')
                        return

                    if refresh.returncode != 0:
                        sudo_lost.set()
                        detail = refresh.stderr.strip()
                        suffix = f': {detail}' if detail else ''
                        Log.error(
                            'GOAD Kingdoms: start sudo keepalive lost its authenticated '
                            f'ticket; privileged transitions will fail closed{suffix}'
                        )
                        return

            sudo_thread = threading.Thread(
                target=sudo_keepalive,
                name='goad-kingdoms-start-sudo-keepalive',
                daemon=True,
            )
            sudo_thread.start()
            Log.success(
                'GOAD Kingdoms: start sudo credentials primed; '
                'non-interactive keepalive active every 60s'
            )

            try:
                # Run the collision/network/sudo preflight before powering on a
                # single guest. GoadKingdomsVmwareProvider.prepare_install()
                # fails closed if another segmented instance conflicts or if
                # required VMware networks are not ready.
                if callable(prepare_install) and not prepare_install():
                    elapsed = self._format_elapsed(time.monotonic() - started)
                    Log.error(
                        f'GOAD_NOMAD: start preflight failed after {elapsed}; '
                        'no guest bring-up will be attempted'
                    )
                    return False

                Log.info(
                    f'GOAD_NOMAD: hardened start using segmented lifecycle '
                    f'(recorded mode: {original_mode})'
                )

                # Installed Kingdoms guests must not re-enter Vagrant's NAT
                # provisioning transport just to power on. Other segmented
                # providers retain their existing install/bring-up behavior.
                start_existing = getattr(self, '_start_existing_instance', None)
                restored = True
                ready = False
                try:
                    if callable(start_existing):
                        ready = start_existing(vm_name) if vm_name is not None else start_existing()
                    else:
                        ready = self.install()
                finally:
                    # Close temporary management routing even when startup or
                    # readiness fails, or the operator interrupts the wait.
                    if original_mode == 'exercise':
                        # NORTH's dependency-ordered cold start can fail before
                        # powering on WS01. Restore router/routes/NAT isolation
                        # without pretending an offline member passed WinRM.
                        # The limited option is only for a failed NORTH start
                        # whose recorded mode was already exercise.
                        if self.lab_name == 'NORTH' and not ready:
                            restored = callable(set_mode) and set_mode(
                                'exercise', allow_stopped_members=True
                            )
                        else:
                            restored = callable(set_mode) and set_mode('exercise')
                        if not restored:
                            Log.error('GOAD_NOMAD: exercise isolation restoration failed; inspect router policy and host routes')

                if not ready:
                    elapsed = self._format_elapsed(time.monotonic() - started)
                    Log.error(
                        f'GOAD_NOMAD: start failed after {elapsed}; '
                        'lab readiness was not proven'
                    )
                    return False

                if not restored:
                    return False

                if sudo_lost.is_set():
                    elapsed = self._format_elapsed(time.monotonic() - started)
                    Log.error(
                        f'GOAD Kingdoms: sudo keepalive was lost during start after '
                        f'{elapsed}; refusing to report start as successful'
                    )
                    return False

                current_mode = get_mode() if callable(get_mode) else original_mode
                elapsed = self._format_elapsed(time.monotonic() - started)
                Log.success(
                    f'GOAD_NOMAD: segmented lab started and readiness verified '
                    f'in {elapsed} (mode: {current_mode})'
                )
                return True
            finally:
                sudo_stop.set()
                sudo_thread.join(timeout=1)

        return self.command.run_vagrant(['up'], self.path)

    def stop(self):
        return self.command.run_vagrant(['halt'], self.path)

    def status(self):
        return self.command.run_vagrant(['status'], self.path)

    def snapshot(self):
        return self.command.run_vagrant(['snapshot', 'push'], self.path)

    def reset(self):
        return self.command.run_vagrant(['snapshot', 'pop', '--no-delete'], self.path)

    def destroy_vm(self, vm_name):
        return self.command.run_vagrant(['destroy', vm_name], self.path)

    def start_vm(self, vm_name):
        return self.command.run_vagrant(['up', vm_name], self.path)

    def stop_vm(self, vm_name):
        return self.command.run_vagrant(['halt', vm_name], self.path)

    def remove_extension(self, extension_name):
        # TODO one day if possible
        pass

    def get_jumpbox_ip(self, ip_range=''):
        return ip_range + '.3'
