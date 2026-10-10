import os
import re
import shutil
import socket
import subprocess
import time

import winrm

from goad.goadpath import GoadPath
from goad.log import Log
from goad.provider.vagrant.vagrant import VagrantProvider
from goad.utils import *


class VmwareProvider(VagrantProvider):
    provider_name = VMWARE
    default_provisioner = PROVISIONING_LOCAL
    allowed_provisioners = [PROVISIONING_LOCAL, PROVISIONING_RUNNER, PROVISIONING_DOCKER, PROVISIONING_VM]

    # GOAD_NOMAD Windows guests. Keep this explicit so Linux guests such as the
    # Debian router are never forced through the WinRM / VMware Tools path.
    goad_nomad_windows = [
        'GOAD-DC01',
        'GOAD-DC02',
        'GOAD-DC03',
        'GOAD-SRV02',
        'GOAD-SRV03',
        'GOAD-WS01',
    ]

    def check(self):
        checks = [
            super().check(),
            self.command.check_vmware(),
            self.command.check_vmware_utility(),
            self.command.check_vagrant_plugin('vagrant-vmware-desktop', True)
        ]
        return all(checks)

    def _vmx_path(self, machine):
        machine_id = os.path.join(
            str(self.path), '.vagrant', 'machines', machine, 'vmware_desktop', 'id'
        )
        if not os.path.isfile(machine_id):
            return None
        with open(machine_id, 'r', encoding='utf-8') as handle:
            vmx = handle.read().strip()
        return vmx if vmx else None

    def _winrm_forwarded_port(self, machine):
        result = subprocess.run(
            [self.command.vagrant_bin, 'port', machine],
            cwd=self.path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        match = re.search(r'5985\s+\(guest\)\s+=>\s+(\d+)\s+\(host\)', result.stdout)
        return int(match.group(1)) if match else None

    @staticmethod
    def _wait_tcp(port, timeout=180):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=2):
                    return True
            except OSError:
                time.sleep(3)
        return False

    @staticmethod
    def _winrm_session(port):
        return winrm.Session(
            f'http://127.0.0.1:{port}/wsman',
            auth=('vagrant', 'vagrant'),
            transport='ntlm',
            operation_timeout_sec=60,
            read_timeout_sec=90,
        )

    def _wait_winrm_ready(self, port, timeout=180):
        """Wait for a stable WinRM command channel, not merely an open TCP port."""
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                session = self._winrm_session(port)
                result = session.run_ps("Write-Output 'GOAD_WINRM_READY'")
                if result.status_code == 0 and b'GOAD_WINRM_READY' in result.std_out:
                    return True
            except Exception as exc:
                last_error = exc
            time.sleep(5)

        if last_error is not None:
            Log.warning(f'GOAD_NOMAD: WinRM never became stable on port {port}: {last_error}')
        return False

    def _guest_tools_healthy(self, port):
        try:
            session = self._winrm_session(port)
            result = session.run_ps(r'''
$svc = Get-Service -Name VMTools -ErrorAction SilentlyContinue
$file = Test-Path "C:\Program Files\VMware\VMware Tools\vmtoolsd.exe"
if ($svc -and $file) {
    if ($svc.Status -ne 'Running') {
        try {
            Set-Service -Name VMTools -StartupType Automatic -ErrorAction Stop
            Start-Service -Name VMTools -ErrorAction Stop
            $svc = Get-Service -Name VMTools
        } catch {}
    }
    if ($svc.Status -eq 'Running') { Write-Output 'GOAD_VMTOOLS_OK' }
}
''')
            return result.status_code == 0 and b'GOAD_VMTOOLS_OK' in result.std_out
        except Exception:
            return False

    def _wait_guest_ip(self, vmx, timeout=180):
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = subprocess.run(
                ['vmrun', '-T', 'ws', 'getGuestIPAddress', vmx],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            ip = result.stdout.strip()
            if result.returncode == 0 and ip and not ip.lower().startswith('error'):
                Log.success(f'GOAD_NOMAD: VMware guest IP reporting healthy ({ip})')
                return True
            time.sleep(5)
        return False

    def _install_vmware_tools(self, machine, vmx, port):
        Log.warning(f'GOAD_NOMAD: {machine} has no healthy VMware Tools; bootstrapping them')

        # Workstation can mount the Tools ISO successfully but leave
        # `vmrun installTools` waiting indefinitely. Bound the host command and
        # continue to the in-guest setup discovery: the mounted media is the
        # actual prerequisite, not a clean vmrun exit status.
        try:
            mount = subprocess.run(
                ['vmrun', '-T', 'ws', 'installTools', vmx],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )
            if mount.returncode != 0:
                Log.warning(
                    f'GOAD_NOMAD: vmrun installTools returned {mount.returncode} for {machine}; '
                    'checking for mounted Tools media through WinRM'
                )
        except subprocess.TimeoutExpired:
            Log.warning(
                f'GOAD_NOMAD: vmrun installTools timed out for {machine}; '
                'continuing because Workstation may already have mounted the Tools ISO'
            )

        if not self._wait_tcp(port, 120):
            Log.error(f'GOAD_NOMAD: WinRM port {port} did not become reachable for {machine}')
            return False

        # A listening WinRM socket is not enough. Older Windows boxes can reset
        # the first authenticated request while services are still converging.
        if not self._wait_winrm_ready(port, 180):
            Log.error(f'GOAD_NOMAD: WinRM did not become stable for {machine}')
            return False

        try:
            session = self._winrm_session(port)
            install = session.run_ps(r'''
$ErrorActionPreference = 'Stop'
$deadline = (Get-Date).AddSeconds(90)
$setup = $null
while ((Get-Date) -lt $deadline -and -not $setup) {
    $setup = Get-CimInstance Win32_LogicalDisk |
        Where-Object { $_.DriveType -eq 5 } |
        ForEach-Object {
            $candidate = "$($_.DeviceID)\setup.exe"
            if (Test-Path $candidate) { $candidate }
        } |
        Select-Object -First 1
    if (-not $setup) { Start-Sleep -Seconds 2 }
}
if (-not $setup) { throw 'VMware Tools setup.exe was not found on a mounted CD/DVD drive' }

$p = Start-Process -FilePath $setup -ArgumentList '/S','/v"/qn REBOOT=ReallySuppress"' -Wait -PassThru
Write-Output "GOAD_VMTOOLS_INSTALL_EXIT=$($p.ExitCode)"
if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { exit $p.ExitCode }
''')
            if install.status_code != 0:
                Log.error(f'GOAD_NOMAD: VMware Tools installer failed for {machine}')
                return False

            Log.info(f'GOAD_NOMAD: VMware Tools installed on {machine}; rebooting guest')
            session.run_ps("shutdown.exe /r /t 5 /f | Out-Null")
        except Exception as exc:
            # VMware Tools installation/reboot can transiently tear down the
            # WinRM transport itself. The disconnect can happen before the
            # explicit reboot below, leaving a successful MSI installation in
            # a reboot-pending state. First accept a guest that recovered on
            # its own; otherwise, once WinRM is stable, perform exactly one
            # controlled recovery reboot and validate Tools + guest-IP health.
            Log.info(
                f'GOAD_NOMAD: VMware Tools install/reboot interrupted WinRM for {machine}; '
                f'validating guest recovery before classifying it as a failure ({exc})'
            )

            deadline = time.time() + 45
            while time.time() < deadline:
                if self._wait_tcp(port, 15) and self._guest_tools_healthy(port):
                    if self._wait_guest_ip(vmx, 60):
                        Log.success(
                            f'GOAD_NOMAD: VMware Tools recovery completed for {machine} '
                            'despite transient WinRM reset'
                        )
                        return True
                time.sleep(5)

            if not self._wait_tcp(port, 180):
                Log.error(
                    f'GOAD_NOMAD: {machine} WinRM did not return after the '
                    'interrupted VMware Tools installation'
                )
                return False
            if not self._wait_winrm_ready(port, 180):
                Log.error(
                    f'GOAD_NOMAD: {machine} WinRM did not stabilize after the '
                    'interrupted VMware Tools installation'
                )
                return False

            Log.warning(
                f'GOAD_NOMAD: VMware Tools on {machine} require a recovery reboot; '
                'restarting the guest once'
            )
            try:
                recovery_session = self._winrm_session(port)
                recovery_session.run_ps("shutdown.exe /r /t 5 /f | Out-Null")
            except Exception as reboot_exc:
                # A successful shutdown commonly closes WinRM before pywinrm
                # receives a response. The readiness checks below are the
                # authority, not the transport result of the reboot command.
                Log.info(
                    f'GOAD_NOMAD: recovery reboot closed WinRM for {machine}; '
                    f'continuing with readiness validation ({reboot_exc})'
                )

            time.sleep(15)
            if not self._wait_tcp(port, 240):
                Log.error(f'GOAD_NOMAD: {machine} WinRM did not return after recovery reboot')
                return False
            if not self._wait_winrm_ready(port, 180):
                Log.error(f'GOAD_NOMAD: {machine} WinRM did not stabilize after recovery reboot')
                return False

            deadline = time.time() + 240
            while time.time() < deadline:
                if self._guest_tools_healthy(port) and self._wait_guest_ip(vmx, 60):
                    Log.success(
                        f'GOAD_NOMAD: VMware Tools recovery reboot completed for {machine}'
                    )
                    return True
                time.sleep(5)

            Log.error(f'GOAD_NOMAD: VMware Tools recovery did not become healthy for {machine}')
            return False

        # The forwarded socket may stay open briefly while Windows restarts.
        time.sleep(15)
        if not self._wait_tcp(port, 240):
            Log.error(f'GOAD_NOMAD: {machine} WinRM did not return after VMware Tools reboot')
            return False

        if not self._wait_winrm_ready(port, 180):
            Log.error(f'GOAD_NOMAD: {machine} WinRM did not stabilize after VMware Tools reboot')
            return False

        deadline = time.time() + 180
        while time.time() < deadline:
            if self._guest_tools_healthy(port):
                break
            time.sleep(5)
        else:
            Log.error(f'GOAD_NOMAD: VMware Tools did not become healthy inside {machine}')
            return False

        if not self._wait_guest_ip(vmx, 180):
            Log.error(f'GOAD_NOMAD: VMware Tools are running but guest IP reporting failed for {machine}')
            return False

        Log.success(f'GOAD_NOMAD: VMware Tools bootstrap complete for {machine}')
        return True

    def _ensure_vmware_tools(self, machine):
        vmx = self._vmx_path(machine)
        if not vmx:
            Log.error(f'GOAD_NOMAD: cannot locate VMX path for {machine}')
            return False

        port = self._winrm_forwarded_port(machine)
        if not port:
            Log.error(f'GOAD_NOMAD: cannot determine forwarded WinRM port for {machine}')
            return False

        if not self._wait_tcp(port, 120):
            Log.error(f'GOAD_NOMAD: forwarded WinRM port {port} is not reachable for {machine}')
            return False

        if self._guest_tools_healthy(port):
            if not self._wait_guest_ip(vmx, 60):
                Log.warning(f'GOAD_NOMAD: {machine} VMware Tools are healthy but guest IP reporting is delayed')
            return True

        return self._install_vmware_tools(machine, vmx, port)

    def _require_full_goad_instance_binding(self):
        """Prevent legacy lifecycle helpers from mutating a reduced instance.

        The existing six-VM GOAD provider is the only activated implementation.
        A reduced recipe, missing/unknown machines, or a preview marker is
        rejected BEFORE source inventory/Vagrantfile synchronization or VM work.
        """
        if self.lab_name == 'NORTH':
            return self._verify_north_instance_sources()
        if self.lab_name != 'GOAD':
            return True
        from goad.course1_instance_binding import inspect_instance_binding
        from goad.course1_runtime_contract import FULL, ProfileNotReady
        try:
            return inspect_instance_binding(self.path) is FULL
        except (ProfileNotReady, OSError, UnicodeError) as exc:
            Log.error(f'GOAD Kingdoms: blocked non-legacy instance binding: {exc}')
            return False

    def _verify_north_instance_sources(self):
        """Read-only gate for the actual NORTH LabInstance-generated assets."""
        from goad.north_native_instance import inspect_north_instance_assets
        from goad.course1_runtime_contract import ProfileNotReady
        try:
            inspected = inspect_north_instance_assets(self.path)
        except (ProfileNotReady, OSError, UnicodeError, ValueError) as exc:
            Log.error(f'Kingdoms NORTH: instance source verification failed: {exc}')
            return False
        Log.success('Kingdoms NORTH: native instance source verified '
                    '(not runtime authorization)')
        return inspected['status'] == 'NATIVE_INSTANCE_SOURCE_VERIFIED'

    def _sync_goad_nomad_vagrantfile_compatibility(self):
        """Backfill current segmented VMware settings into existing instances.

        Instance Vagrantfiles are rendered when a workspace is first created.
        Updating the repository template therefore does not repair an already
        deployed lab by itself. Keep this compatibility patch intentionally
        small and idempotent so old workspaces gain the same provider settings
        before the next Windows ``vagrant up``.
        """
        if self.lab_name == 'NORTH':
            # NORTH is built from the patched Kingdoms template. Never rewrite
            # it using the reference six-guest WS01 compatibility migration.
            return self._verify_north_instance_sources()

        if not self._require_full_goad_instance_binding():
            return False
        vagrantfile = os.path.join(str(self.path), 'Vagrantfile')
        if not os.path.isfile(vagrantfile):
            Log.error(f'GOAD_NOMAD: instance Vagrantfile not found: {vagrantfile}')
            return False

        with open(vagrantfile, 'r', encoding='utf-8') as handle:
            text = handle.read()

        # Also migrate existing generated workspaces: template edits alone do
        # not disable their Vagrant Cloud metadata checks.
        if 'config.vm.box_check_update = false' not in text:
            config_marker = 'Vagrant.configure("2") do |config|'
            if text.count(config_marker) != 1:
                Log.error('GOAD_NOMAD: cannot locate unique Vagrant configuration for offline settings')
                return False
            text = text.replace(config_marker, config_marker + '\n  config.vm.box_check_update = false', 1)

        required = (
            'v.enable_vmrun_ip_lookup = false',
            'v.vmx["ethernet0.startConnected"] = "TRUE"',
        )
        missing = [setting for setting in required if setting not in text]

        ws01_marker = ':name => "GOAD-WS01"'
        if ws01_marker in text:
            ws01_contract = (
                ':ip => "10.4.10.31"',
                ':box => "mayfly/windows10"',
                ':box_version => "2024.01.06"',
                ':vnet => "vmnet10"',
            )
            if any(token not in text for token in ws01_contract):
                Log.error(
                    'GOAD Kingdoms: an incompatible GOAD-WS01 definition '
                    'already exists in the instance Vagrantfile; refusing to '
                    'overwrite an unknown workstation automatically'
                )
                return False
        else:
            source_vagrantfile = os.path.join(
                GoadPath.get_lab_provider_path('GOAD', 'vmware'),
                'Vagrantfile',
            )
            with open(source_vagrantfile, 'r', encoding='utf-8') as handle:
                source_text = handle.read()

            ws01_match = re.search(
                r'(?ms)^  # GOAD Kingdoms M2 first-class NORTH workstation\.\n'
                r'(.*?)(?=^  # GOAD_NOMAD routing plane\.)',
                source_text,
            )
            router_marker = '  # GOAD_NOMAD routing plane.'
            if ws01_match is None or router_marker not in text:
                Log.error(
                    'GOAD_NOMAD: cannot safely add GOAD-WS01 to the existing '
                    'instance Vagrantfile; expected source markers are missing'
                )
                return False

            ws01_block = (
                '  # GOAD Kingdoms M2 first-class NORTH workstation.\n'
                + ws01_match.group(1)
            )
            text = text.replace(router_marker, ws01_block + router_marker, 1)
            Log.success(
                'GOAD Kingdoms: added the committed GOAD-WS01 definition to '
                'the existing instance Vagrantfile'
            )

        if not missing:
            with open(vagrantfile, 'w', encoding='utf-8') as handle:
                handle.write(text)
            return True

        marker = '        v.vmx["numvcpus"] = box[:cpus]\n'
        if marker not in text:
            Log.error(
                'GOAD_NOMAD: cannot safely update the existing Vagrantfile; '
                'expected VMware provider marker is missing'
            )
            return False

        lines = [
            '',
            '        # GOAD_NOMAD compatibility for existing multi-NIC Windows instances.',
            '        if box[:os] == "windows"',
        ]
        if required[0] in missing:
            lines.append('          v.enable_vmrun_ip_lookup = false')
        if required[1] in missing:
            lines.append('          v.vmx["ethernet0.startConnected"] = "TRUE"')
        lines.append('        end')

        replacement = marker + '\n'.join(lines) + '\n'
        text = text.replace(marker, replacement, 1)

        with open(vagrantfile, 'w', encoding='utf-8') as handle:
            handle.write(text)

        Log.success(
            'GOAD_NOMAD: existing instance Vagrantfile synchronized with '
            'current multi-NIC provisioning settings'
        )
        return True

    def _sync_goad_nomad_inventories(self):
        """Refresh generated GOAD inventories from committed canonical source.

        Instance inventories are generated when the workspace is created. M2
        adds WS01 to an existing M1 instance, so a pulled Git commit must update
        those generated files without asking the operator to edit the test
        checkout or workspace manually.
        """
        if self.lab_name == 'NORTH':
            # Native NORTH inventories must match its own canonical source,
            # never be overwritten by the GOAD reference inventory.
            return self._verify_north_instance_sources()

        if not self._require_full_goad_instance_binding():
            return False
        instance_path = os.path.dirname(str(self.path))
        provider_source = (
            GoadPath.get_lab_provider_path('GOAD', 'vmware')
            + os.path.sep
            + 'inventory'
        )
        provider_destination = os.path.join(instance_path, 'inventory')
        disabled_source = (
            GoadPath.get_lab_data_path('GOAD')
            + os.path.sep
            + 'inventory_disable_vagrant'
        )
        disabled_destination = os.path.join(
            instance_path,
            'inventory_disable_vagrant',
        )

        for source in (provider_source, disabled_source):
            if not os.path.isfile(source):
                Log.error(f'GOAD_NOMAD canonical inventory not found: {source}')
                return False

        shutil.copyfile(provider_source, provider_destination)

        with open(disabled_source, 'r', encoding='utf-8') as handle:
            disabled_text = handle.read()

        # Reuse the already-established NORTH administrator connection rather
        # than publishing another credential literal for WS01. The generated
        # runtime inventory remains deterministic and source-derived.
        srv02_match = re.search(r'(?m)^srv02 ansible_host=.*$', disabled_text)
        if srv02_match is None:
            Log.error(
                'GOAD_NOMAD: cannot derive the WS01 post-Vagrant inventory '
                'from the canonical NORTH server entry'
            )
            return False
        ws01_line = re.sub(
            r'^srv02 ansible_host=\S+ dns_domain=\S+ dict_key=srv02',
            'ws01 ansible_host=10.4.10.31 dns_domain=dc02 dict_key=ws01',
            srv02_match.group(0),
        )
        disabled_text = disabled_text.replace(
            srv02_match.group(0),
            srv02_match.group(0) + '\n' + ws01_line,
            1,
        )
        with open(disabled_destination, 'w', encoding='utf-8') as handle:
            handle.write(disabled_text)

        Log.success(
            'GOAD Kingdoms: generated instance inventories synchronized from '
            'committed source'
        )
        return True

    def install(self):
        """Bring up VMware guests and prepare GOAD_NOMAD local provisioning reachability."""
        if self.lab_name != 'GOAD':
            return super().install()

        if not self._sync_goad_nomad_inventories():
            return False

        if not self._sync_goad_nomad_vagrantfile_compatibility():
            return False

        # Bring up the router independently so a Windows guest failure cannot
        # prevent creation of the routing plane. Linux keeps the normal SSH path.
        Log.info('GOAD_NOMAD: bringing up segmented router')
        if not self.command.run_vagrant(['up', 'GOAD-ROUTER'], self.path):
            Log.error('GOAD_NOMAD: failed to bring up GOAD-ROUTER')
            return False

        # Windows VMware boxes can expose working forwarded WinRM while VMware
        # Tools are absent. In that state vagrant-vmware-desktop cannot discover
        # the guest IP and aborts with the well-known guest-communication error.
        # Handle each Windows guest independently, repair Tools when necessary,
        # and retry the Vagrant bring-up instead of aborting the complete lab.
        for machine in self.goad_nomad_windows:
            Log.info(f'GOAD_NOMAD: bringing up {machine}')
            first_up = self.command.run_vagrant(['up', machine], self.path)

            if not self._ensure_vmware_tools(machine):
                return False

            if not first_up:
                Log.warning(f'GOAD_NOMAD: retrying {machine} after VMware Tools recovery')
                if not self.command.run_vagrant(['up', machine], self.path):
                    Log.error(f'GOAD_NOMAD: {machine} still failed after VMware Tools recovery')
                    return False

        # The host has no vmnet20/vmnet30 adapters, so local Ansible must
        # temporarily reach those protected networks through GOAD-ROUTER after
        # Vagrant has brought the complete instance up.
        route_script = GoadPath.get_script_file('provisioning-routes.sh')
        if not os.path.isfile(route_script):
            Log.error(f'GOAD_NOMAD provisioning route helper not found: {route_script}')
            return False

        Log.info('GOAD_NOMAD: enabling temporary host routes for local Ansible provisioning')
        # Repository script files are not guaranteed to carry an executable bit
        # after clone/archive operations. Invoke the helper through bash instead
        # of executing it directly so the install path is mode-independent.
        route_result = subprocess.run(['sudo', 'bash', route_script, 'enable'], check=False)
        if route_result.returncode != 0:
            Log.error('GOAD_NOMAD: failed to enable temporary provisioning routes')
            return False

        Log.warning('GOAD_NOMAD: provisioning routes are temporary and must be removed before exercise mode')
        return True
