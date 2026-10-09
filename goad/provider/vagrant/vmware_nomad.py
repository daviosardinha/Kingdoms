import os
import socket
import subprocess
import time

import winrm

from goad.goadpath import GoadPath
from goad.kingdoms_vmware_profile import binding_for
from goad.log import Log
from goad.provider.vagrant.vmware import VmwareProvider


class GoadNomadVmwareProvider(VmwareProvider):
    """VMware provider with the GOAD_NOMAD segmented lifecycle.

    The normal GOAD lab on VMware is segmented by default in this fork. Other
    labs using the VMware provider retain the upstream Vagrant behaviour.
    """

    network_scope = '10.4.0.0/16 (segmented)'
    network_zones = (
        ('NORTH', 'vmnet10', '10.4.10.0/24'),
        ('SEVENKINGDOMS', 'vmnet20', '10.4.20.0/24'),
        ('ESSOS', 'vmnet30', '10.4.30.0/24'),
        ('MANAGEMENT', 'vmnet99', '10.4.99.0/24'),
    )

    management_hosts = {
        'GOAD-DC01': '10.4.20.10',
        'GOAD-DC02': '10.4.10.11',
        'GOAD-DC03': '10.4.30.12',
        'GOAD-SRV02': '10.4.10.22',
        'GOAD-SRV03': '10.4.30.23',
        'GOAD-WS01': '10.4.10.31',
    }

    def __init__(self, lab_name):
        super().__init__(lab_name)
        # Data-only instance binding: the patched Kingdoms provider is shared.
        # GOAD receives byte-for-byte equivalent 6-guest/4-zone values.
        # NORTH can be selected as a separate profile, but is NOT installable
        # until its router/exercise lifecycle is proved independently.
        binding = binding_for(lab_name)
        self.kingdoms_vmware_binding = binding
        if binding is not None:
            self.goad_nomad_windows = list(binding.roster.windows)
            self.management_hosts = dict(binding.roster.management_hosts)
            self.network_zones = binding.zones
            self.network_scope = (
                "10.4.0.0/16 (segmented)" if lab_name == "GOAD"
                else "10.41.0.0/16 (segmented)"
            )

    def is_goad_nomad_segmented(self):
        return self.lab_name == 'GOAD'

    @staticmethod
    def _project_root_from_script(script):
        return os.path.dirname(os.path.dirname(script))

    def _script(self, name):
        script = GoadPath.get_script_file(name)
        if not os.path.isfile(script):
            Log.error(f'GOAD_NOMAD helper not found: {script}')
            return None
        return script

    def _provider_env(self):
        env = os.environ.copy()
        env['GOAD_PROVIDER_DIR'] = str(self.path)
        return env

    def _run_vagrant_bounded(self, args, timeout):
        command = [self.command.vagrant_bin] + args
        Log.info(f'GOAD_NOMAD: running bounded command: {" ".join(command)}')
        try:
            result = subprocess.run(
                command,
                cwd=self.path,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            Log.warning(
                f'GOAD_NOMAD: {" ".join(command)} exceeded {timeout}s; '
                'continuing with automatic shutdown fallback'
            )
            return False
        return result.returncode == 0

    def _running_instance_vms(self):
        """Return this instance's running Vagrant machine names via vmrun."""
        try:
            result = subprocess.run(
                ['vmrun', '-T', 'ws', 'list'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            Log.error(f'GOAD_NOMAD: cannot query VMware running state: {exc}')
            return None

        if result.returncode != 0:
            Log.error(
                'GOAD_NOMAD: vmrun list failed: '
                + (result.stderr.strip() or result.stdout.strip())
            )
            return None

        running_paths = {
            os.path.realpath(line.strip())
            for line in result.stdout.splitlines()[1:]
            if line.strip()
        }

        names = self.goad_nomad_windows + ['GOAD-ROUTER']
        running = []
        for machine in names:
            vmx = self._vmx_path(machine)
            if vmx and os.path.realpath(vmx) in running_paths:
                running.append(machine)
        return running

    def _all_windows_materialized(self):
        """Return True only when all six Windows VMX files already exist."""
        return all(self._vmx_path(machine) for machine in self.goad_nomad_windows)

    def _router_policy_path(self, mode):
        return os.path.join(
            GoadPath.get_lab_provider_path('GOAD', 'vmware'),
            'router',
            'nftables',
            f'{mode}.nft',
        )

    def _apply_router_policy(self, mode):
        """Apply one router policy without requiring the Windows VMs to exist.

        ``lab-mode.sh provisioning`` deliberately validates all six Windows VMX
        files before changing state. That is correct for normal mode switching,
        but a genuinely fresh installation needs the router forwarding plane
        before the Windows VMs have even been created. This small bootstrap path
        therefore applies only the router policy; the full mode controller takes
        ownership again once all Windows guests exist.
        """
        policy = self._router_policy_path(mode)
        if not os.path.isfile(policy):
            Log.error(f'GOAD_NOMAD router policy not found: {policy}')
            return False

        with open(policy, 'r', encoding='utf-8') as handle:
            policy_text = handle.read()

        remote = (
            'set -e; '
            'cat > /tmp/goad-nomad-mode.nft; '
            'sudo nft -c -f /tmp/goad-nomad-mode.nft; '
            'sudo install -m 0644 /tmp/goad-nomad-mode.nft /etc/nftables.conf; '
            'sudo systemctl restart nftables'
        )

        ssh = self._script('router-ssh.sh')
        if ssh is None:
            return False
        try:
            result = subprocess.run(
                ['bash', ssh, remote],
                cwd=self.path,
                env=self._provider_env(),
                input=policy_text,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            Log.error(f'GOAD_NOMAD: router policy update failed: {exc}')
            return False
        if result.returncode != 0:
            Log.error(f'GOAD_NOMAD: failed to apply router {mode} policy')
            return False

        Log.success(f'GOAD_NOMAD: router {mode} policy active')
        return True

    def _enable_provisioning_routes(self):
        route_script = self._script('provisioning-routes.sh')
        if route_script is None:
            return False

        result = subprocess.run(
            ['sudo', 'bash', route_script, 'enable'],
            check=False,
        )
        if result.returncode != 0:
            Log.error('GOAD_NOMAD: failed to enable temporary provisioning routes')
            return False

        Log.success('GOAD_NOMAD: protected-zone provisioning routes enabled')
        return True

    def _bootstrap_provisioning_plane(self):
        """Make routing available before Vagrant chooses a protected-zone IP.

        vagrant-vmware-desktop may select the exercise NIC address (for example
        10.4.30.12) as its WinRM endpoint. The host intentionally has no vmnet20
        or vmnet30 adapter, so routes and permissive router policy must already
        exist before any Windows ``vagrant up`` operation begins.
        """
        Log.info('GOAD_NOMAD: bootstrapping router before Windows guests')
        if not self.command.run_vagrant(['up', 'GOAD-ROUTER'], self.path):
            Log.error('GOAD_NOMAD: failed to bring up GOAD-ROUTER')
            return False

        # On an existing complete deployment use the authoritative mode
        # controller. It also reconnects persistent NAT adapters if the lab was
        # previously in exercise mode.
        if self._all_windows_materialized():
            Log.info('GOAD_NOMAD: complete VM set detected; entering provisioning mode before guest bring-up')
            return self.set_runtime_mode('provisioning')

        # On the first ever install the Windows VMX files do not exist yet, so
        # only bootstrap the router + host routes. Full mode state is persisted
        # after VmwareProvider.install() has created all six guests.
        if not self._apply_router_policy('provisioning'):
            return False
        if not self._enable_provisioning_routes():
            return False

        return True

    @staticmethod
    def _lab_winrm_session(host):
        return winrm.Session(
            f'https://{host}:5986/wsman',
            auth=('vagrant', 'vagrant'),
            transport='ntlm',
            server_cert_validation='ignore',
            operation_timeout_sec=30,
            read_timeout_sec=45,
        )

    def _wait_lab_winrm_ready(self, machine, host, timeout=300):
        """Prove the exact management endpoint Ansible will use is functional."""
        deadline = time.time() + timeout
        last_error = None

        while time.time() < deadline:
            try:
                with socket.create_connection((host, 5986), timeout=3):
                    pass

                result = self._lab_winrm_session(host).run_ps(
                    "Write-Output 'GOAD_NOMAD_ANSIBLE_READY'"
                )
                if (
                    result.status_code == 0
                    and b'GOAD_NOMAD_ANSIBLE_READY' in result.std_out
                ):
                    Log.success(
                        f'GOAD_NOMAD: {machine} Ansible WinRM ready at {host}:5986'
                    )
                    return True
            except Exception as exc:
                last_error = exc

            time.sleep(5)

        detail = f': {last_error}' if last_error is not None else ''
        Log.error(
            f'GOAD_NOMAD: {machine} Ansible WinRM never became ready at '
            f'{host}:5986 within {timeout}s{detail}'
        )
        return False

    def _validate_management_plane(self):
        """Fail closed unless all six inventory endpoints are ready."""
        Log.info('GOAD_NOMAD: validating all six Ansible management endpoints')
        for machine, host in self.management_hosts.items():
            if not self._wait_lab_winrm_ready(machine, host):
                return False

        Log.success('GOAD_NOMAD: all Windows Ansible management endpoints are healthy')
        return True

    def prepare_install(self):
        """Ensure the four GOAD_NOMAD VMware networks exist before Vagrant."""
        if not self.is_goad_nomad_segmented():
            return True

        check_script = self._script('check-vmware-networks.sh')
        setup_script = self._script('setup-vmware-networks.sh')
        if check_script is None or setup_script is None:
            return False

        Log.info('GOAD_NOMAD: checking segmented VMware networks')
        check = subprocess.run(['bash', check_script], check=False)
        if check.returncode == 0:
            Log.success('GOAD_NOMAD: segmented VMware networks already ready')
            return True

        Log.info('GOAD_NOMAD: preparing vmnet10/vmnet20/vmnet30/vmnet99')
        setup = subprocess.run(['sudo', 'bash', setup_script], check=False)
        if setup.returncode != 0:
            Log.error('GOAD_NOMAD: VMware network setup failed')
            return False

        check = subprocess.run(['bash', check_script], check=False)
        if check.returncode != 0:
            Log.error('GOAD_NOMAD: VMware network validation failed after setup')
            return False

        Log.success('GOAD_NOMAD: segmented VMware networks prepared')
        return True

    def get_network_scope(self):
        if self.is_goad_nomad_segmented():
            return self.network_scope
        return None

    def get_network_details(self):
        if not self.is_goad_nomad_segmented():
            return []
        return list(self.network_zones)

    def get_runtime_mode(self):
        if not self.is_goad_nomad_segmented() or self.path is None:
            return '-'
        state_file = os.path.join(str(self.path), '.goad-nomad-mode')
        if not os.path.isfile(state_file):
            return 'unknown'
        with open(state_file, 'r', encoding='utf-8') as handle:
            value = handle.read().strip()
        return value if value else 'unknown'

    def set_runtime_mode(self, mode):
        if not self.is_goad_nomad_segmented():
            Log.error('Runtime modes are only available for GOAD_NOMAD GOAD/VMware instances')
            return False

        if mode not in ('provisioning', 'exercise'):
            Log.error('GOAD_NOMAD mode must be provisioning or exercise')
            return False

        mode_script = self._script('lab-mode.sh')
        if mode_script is None:
            return False

        Log.info(f'GOAD_NOMAD: switching to {mode} mode')
        result = subprocess.run(
            ['bash', mode_script, mode],
            env=self._provider_env(),
            check=False,
        )
        return result.returncode == 0

    def prepare_provisioning(self):
        """Make the Vagrant/Ansible management plane available."""
        if not self.is_goad_nomad_segmented():
            return True
        if self.get_runtime_mode() == 'provisioning':
            return self._validate_management_plane()
        if not self.set_runtime_mode('provisioning'):
            return False
        return self._validate_management_plane()

    def finalize_install(self):
        """A successful full GOAD provisioning run must end in exercise mode."""
        if not self.is_goad_nomad_segmented():
            return True
        Log.info('GOAD_NOMAD: provisioning complete; enforcing final exercise isolation')
        return self.set_runtime_mode('exercise')

    def validate_runtime(self):
        if not self.is_goad_nomad_segmented():
            Log.error('GOAD_NOMAD runtime validation is only available for GOAD/VMware')
            return False

        validator = self._script('validate-network-segmentation.sh')
        if validator is None:
            return False

        root = self._project_root_from_script(validator)
        Log.info('GOAD_NOMAD: launching clean network-segmentation runtime validation')
        result = subprocess.run(
            ['bash', validator],
            cwd=root,
            env=self._provider_env(),
            check=False,
        )
        return result.returncode == 0

    def status(self):
        result = super().status()
        if self.is_goad_nomad_segmented():
            Log.info(f'GOAD_NOMAD Network : {self.network_scope}')
            Log.info(f'GOAD_NOMAD Mode    : {self.get_runtime_mode()}')
        return result

    def stop(self):
        """Stop the segmented lab without leaving the operator stuck in Vagrant.

        Upstream GOAD gives graceful halt a 600-second window. Windows/WinRM can
        stall in Vagrant's GracefulHalt path, so GOAD_NOMAD adds an outer bound:
        try the normal graceful Vagrant halt first, then automatically force only
        the guests that remain running and verify the final VMware power state.
        """
        if not self.is_goad_nomad_segmented():
            return super().stop()

        running = self._running_instance_vms()
        if running is None:
            return False
        if not running:
            Log.success('GOAD_NOMAD: all instance VMs are already stopped')
            return True

        Log.info(
            'GOAD_NOMAD: stopping lab gracefully with a bounded controller timeout '
            f'({", ".join(running)})'
        )
        self._run_vagrant_bounded(['halt'], timeout=180)

        remaining = self._running_instance_vms()
        if remaining is None:
            return False

        if remaining:
            Log.warning(
                'GOAD_NOMAD: graceful shutdown did not finish for: '
                + ', '.join(remaining)
                + '; automatically forcing only those remaining guests'
            )
            for machine in remaining:
                self._run_vagrant_bounded(['halt', machine, '-f'], timeout=45)

        remaining = self._running_instance_vms()
        if remaining is None:
            return False
        if remaining:
            Log.error('GOAD_NOMAD: shutdown incomplete; still running: ' + ', '.join(remaining))
            return False

        Log.success('GOAD_NOMAD: all instance VMs stopped and VMware state verified')
        return True

    def install(self):
        if not self.is_goad_nomad_segmented():
            return super().install()

        if not self.prepare_install():
            return False

        # The provisioning network plane must exist before any Windows Vagrant
        # bring-up. vagrant-vmware-desktop may select a 10.4.x exercise address
        # for WinRM, and protected zones are intentionally unreachable from the
        # host until these temporary routes + router policy are active.
        if not self._bootstrap_provisioning_plane():
            return False

        # Reuse the hardened VMware guest bring-up and Tools recovery. The base
        # provider will harmlessly re-check the already-running router and
        # re-enable the same idempotent provisioning routes at the end.
        if not super().install():
            return False

        # Do not let the console launch Ansible merely because Vagrant returned.
        # Prove the exact six HTTPS/WinRM inventory endpoints first.
        if not self._validate_management_plane():
            Log.error('GOAD_NOMAD: provider bring-up incomplete; refusing Ansible provisioning')
            return False

        # Persist the authoritative mode and make sure NAT adapters remain
        # connected for the provisioning phase.
        if not self.set_runtime_mode('provisioning'):
            return False

        return self._validate_management_plane()
