import ipaddress
import os
import re
import signal
import subprocess
import time

import psutil

from goad.course1_snapshot_restore import (
    NorthSnapshotRestoreError, restore_north_offline_snapshots,
)
from goad.goadpath import GoadPath
from goad.log import Log
from goad.provider.vagrant.vmware_nomad import GoadNomadVmwareProvider


class GoadKingdomsVmwareProvider(GoadNomadVmwareProvider):
    """GOAD Kingdoms VMware provider policy layered over the M1 lifecycle.

    ``GoadNomadVmwareProvider`` remains the compatibility implementation that
    owns the already-validated segmented lifecycle. New GOAD Kingdoms safety
    policy is added here so M2 changes do not casually rewrite the M1 core.
    """

    def _course1_unwired(self):
        """Fail closed unless THIS NORTH instance owns verified host networking.

        Use the original Kingdoms lifecycle only after the committed VMware
        owner, backup, three vmnets and .254 persistence prove ready. No
        generic Vagrant fallback and no host writes in this attestation.
        """
        if self.lab_name != 'NORTH':
            return False
        path = getattr(self, 'path', None)
        if path is None:
            Log.error('Course 1: no instance provider path; refusing NORTH lifecycle')
            return True
        checker = self._script('setup-vmware-networks.sh')
        if checker is None:
            return True
        try:
            result = subprocess.run(
                ['sudo', '-n', 'bash', checker, '--north', 'verify',
                 '--provider-dir', os.path.realpath(str(path))],
                check=False, capture_output=True, text=True, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            Log.error(f'Course 1: host-network ownership check unavailable: {exc}')
            return True
        if result.returncode != 0:
            Log.error('Course 1: NORTH VMware owner or live host state is not ready')
            if result.stderr.strip():
                Log.error(result.stderr.strip())
            return True
        return False

    def start(self, vm_name=None):
        if self._course1_unwired():
            return False
        return super().start(vm_name=vm_name)

    def _require_cached_sudo(self):
        """Require an already-authenticated sudo timestamp without prompting.

        GOAD Kingdoms lifecycle commands must never stop deep inside a provider
        transition waiting for an unexpected password prompt. Long install/ws01
        lifecycles prime sudo once at the console boundary and refresh it with a
        non-interactive keepalive. Direct provider/mode operations still require
        an existing sudo cache. Every privileged transition re-checks the cache
        non-interactively and fails before changing runtime state if credentials
        are unavailable or expired.
        """
        result = subprocess.run(
            ['sudo', '-n', '-v'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip()
            if detail:
                Log.error(f'GOAD Kingdoms: sudo cache unavailable: {detail}')
            Log.error(
                'GOAD Kingdoms: administrative credentials are not cached; '
                'run `sudo -v` in this terminal, then repeat the command'
            )
            return False

        return True

    def _check_segmented_instance_conflicts(self):
        if not self.is_goad_nomad_segmented():
            return True

        if self.path is None:
            Log.error('GOAD Kingdoms: provider path is unavailable for collision preflight')
            return False

        guard = self._script('check-vmware-instance-conflicts.sh')
        if guard is None:
            return False

        Log.info('GOAD Kingdoms: checking for conflicting running segmented VMware instances')
        conflict_args = ['bash', guard]
        if self.lab_name == 'NORTH':
            conflict_args.append('--north')
        conflict_args.append(os.path.realpath(str(self.path)))
        result = subprocess.run(conflict_args, check=False)
        if result.returncode != 0:
            Log.error(
                'GOAD Kingdoms: VMware bring-up blocked because another running '
                'guest owns one or more deterministic segmented MAC identities'
            )
            return False

        Log.success('GOAD Kingdoms: segmented VMware instance collision preflight passed')
        return True

    @staticmethod
    def _vagrant_cleanup_members(pgid):
        """Snapshot live group members, with fresh executable/PID identities.

        A started vmware-vmx can inherit Vagrant's process group. Group
        membership therefore establishes scope, never permission to signal it.
        Inspection failures propagate so cleanup cannot guess at a target.
        """
        members = {}
        for pid in psutil.pids():
            try:
                if os.getpgid(pid) != pgid:
                    continue
                proc = psutil.Process(pid)
                if proc.status() == psutil.STATUS_ZOMBIE:
                    continue
                name = os.path.basename(proc.exe())
                if not name:
                    raise RuntimeError(f'cannot identify executable for PID {pid}')
                members[pid] = (proc.create_time(), proc.ppid(), name)
            except (psutil.NoSuchProcess, ProcessLookupError):
                continue
        return members

    @staticmethod
    def _vagrant_cleanup_targets(members, leader, preserved):
        """Protect VM monitors and their descendants; allow known controllers."""
        protected = {
            pid for pid, (created, _, name) in members.items()
            if name.startswith('vmware-vmx') or name == 'mksSandbox'
            or (pid, created) in preserved
        }
        while True:
            children = {pid for pid, (_, parent, _) in members.items()
                        if parent in protected}
            if children.issubset(protected):
                break
            protected.update(children)
        preserved.update((pid, members[pid][0]) for pid in protected)

        targets, unknown = {}, []
        for pid, (created, _, name) in members.items():
            if pid in protected:
                continue
            if (pid == leader or name in ('vagrant', 'vmrun', 'sh', 'bash', 'dash')
                    or re.fullmatch(r'ruby(?:\d+(?:\.\d+)*)?', name)):
                targets[pid] = (created, name)
            else:
                unknown.append(f'{name} (PID {pid})')
        return targets, unknown

    @staticmethod
    def _signal_vagrant_controller(pid, identity, pgid, sig):
        """Recheck PID age, executable and scope immediately before signaling."""
        try:
            proc = psutil.Process(pid)
            current = (proc.create_time(), os.path.basename(proc.exe()))
            if current != identity or os.getpgid(pid) != pgid:
                raise RuntimeError(f'process identity or group changed for PID {pid}')
            # psutil also checks PID reuse when sending the signal.
            proc.send_signal(sig)
        except (psutil.NoSuchProcess, ProcessLookupError):
            pass

    def _reap_vagrant_controller(self, process, command):
        """Reap controller/helpers by PID while leaving VMware guests running.

        Unknown/unreadable group members make cleanup incomplete. Never send a
        group-wide signal: a guest monitor can outlive the Vagrant controller
        in that very same group. Remember protected identities across scans,
        including VM descendants that become reparented during cleanup.
        """
        Log.warning(
            'GOAD Kingdoms: cleaning up timed-out Vagrant controller by PID '
            f'(preserving VMware guests): {" ".join(command)}'
        )
        preserved = set()
        for sig in (signal.SIGTERM, signal.SIGKILL):
            deadline = time.monotonic() + 5
            signaled = set()
            while True:
                try:
                    process.poll()
                    members = self._vagrant_cleanup_members(process.pid)
                    previously_preserved = set(preserved)
                    targets, unknown = self._vagrant_cleanup_targets(
                        members, process.pid, preserved,
                    )
                    newly_preserved = preserved - previously_preserved
                    if newly_preserved:
                        Log.info(
                            'GOAD Kingdoms: excluding VMware guest processes from cleanup: '
                            + ', '.join(f'{members[pid][2]} (PID {pid})'
                                        for pid, _ in sorted(newly_preserved))
                        )
                    if unknown:
                        raise RuntimeError('unrecognized group members: ' + ', '.join(unknown))
                    if not targets:
                        if process.poll() is None:
                            raise RuntimeError('Vagrant leader is still running outside verified cleanup targets')
                        Log.success(
                            'GOAD Kingdoms: timed-out Vagrant controller fully reaped; '
                            'VMware guest processes preserved'
                        )
                        return True
                    for pid, identity in targets.items():
                        key = (pid, identity)
                        if key not in signaled:
                            self._signal_vagrant_controller(pid, identity, process.pid, sig)
                            signaled.add(key)
                except (psutil.Error, OSError, RuntimeError) as exc:
                    Log.error(f'GOAD Kingdoms: Vagrant cleanup incomplete; {exc}')
                    return False
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.2)
        Log.error(
            'GOAD Kingdoms: timed-out Vagrant controller is still alive; '
            'refusing to race a second lifecycle action'
        )
        return False

    def _run_vagrant_bounded(self, args, timeout):
        """Run Vagrant in a dedicated group; selectively reap it on timeout."""
        if not getattr(self, '_last_bounded_vagrant_reaped', True):
            Log.error('GOAD Kingdoms: previous Vagrant cleanup is incomplete; refusing another action')
            return False
        command = [self.command.vagrant_bin] + args
        Log.info(f'GOAD_NOMAD: running bounded command: {" ".join(command)}')
        self._last_bounded_vagrant_reaped = True

        try:
            process = subprocess.Popen(
                command,
                cwd=self.path,
                start_new_session=True,
            )
        except OSError as exc:
            Log.error(f'GOAD Kingdoms: failed to start {" ".join(command)}: {exc}')
            return False

        try:
            return process.wait(timeout=timeout) == 0
        except subprocess.TimeoutExpired:
            Log.warning(
                f'GOAD_NOMAD: {" ".join(command)} exceeded {timeout}s; '
                'cleaning up its controller while preserving VMware guests'
            )
            self._last_bounded_vagrant_reaped = self._reap_vagrant_controller(
                process,
                command,
            )
            return False

    def _wait_machine_stopped(self, machine, timeout=120):
        """Wait until VMware no longer reports ``machine`` as running."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            running = self._running_instance_vms()
            if running is None:
                return False
            if machine not in running:
                return True
            time.sleep(3)
        return False

    def _stop_machine_via_vmware(self, machine):
        """Request local guest shutdown, retaining the bounded hard fallback."""
        vmx = self._vmx_path(machine)
        if not vmx:
            Log.error(f'GOAD Kingdoms: cannot locate VMX for shutdown fallback: {machine}')
            return False

        Log.info(f'GOAD Kingdoms: requesting local VMware Tools soft shutdown for {machine}')
        try:
            soft = subprocess.run(
                ['vmrun', '-T', 'ws', 'stop', vmx, 'soft'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=45,
            )
        except subprocess.TimeoutExpired:
            # vmrun can block waiting for VMware Tools even after Windows has
            # accepted the shutdown request. Do not turn a slow graceful stop
            # into an immediate hard power cut: observe VMware power state for
            # one bounded guest-shutdown grace window first.
            Log.warning(
                f'GOAD Kingdoms: VMware soft-stop host command timed out for {machine}; '
                'the guest may still be shutting down, allowing up to 120s before hard fallback'
            )
        except OSError as exc:
            Log.warning(f'GOAD Kingdoms: VMware soft stop failed for {machine}: {exc}')
        else:
            detail = soft.stderr.strip() or soft.stdout.strip()
            if detail:
                Log.warning(f'GOAD Kingdoms: VMware soft stop for {machine}: {detail}')

        # Even a timed-out vmrun may already have delivered the shutdown
        # request. Give Windows enough time to finish service/domain shutdown
        # before using the last-resort hard power-off.
        if self._wait_machine_stopped(machine, 120):
            Log.success(f'GOAD Kingdoms: {machine} completed VMware soft shutdown')
            return True
        running = self._running_instance_vms()
        if running is None:
            Log.error('GOAD Kingdoms: cannot verify VMware state; refusing hard shutdown')
            return False
        if machine not in running:
            return True

        Log.warning(
            f'GOAD Kingdoms: {machine} did not stop softly; '
            'using VMware hard stop as the final fallback'
        )
        try:
            hard = subprocess.run(
                ['vmrun', '-T', 'ws', 'stop', vmx, 'hard'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            Log.error(f'GOAD Kingdoms: VMware hard stop failed for {machine}: {exc}')
            return False

        if self._wait_machine_stopped(machine, 30):
            Log.success(f'GOAD Kingdoms: {machine} stopped by VMware hard fallback')
            return True

        detail = hard.stderr.strip() or hard.stdout.strip()
        if detail:
            Log.error(f'GOAD Kingdoms: VMware hard stop for {machine}: {detail}')
        Log.error(f'GOAD Kingdoms: {machine} is still running after VMware hard fallback')
        return False

    def _stop_failed_windows_guest_cleanly(self, machine):
        """Stop a recoverable Windows guest without hard-powering it off first.

        Older StefanScherer Windows Server 2016 boxes can reach the desktop while
        VMware Tools/WSMan becomes unhealthy after an unconditional ``halt -f``.
        At this point ``_ensure_vmware_tools`` has already proved WinRM/Tools
        readiness, so prefer an in-guest Windows shutdown. If the transport tears
        down before returning, VMware power state remains authoritative. A VMware
        Tools soft stop is the second graceful path; forced Vagrant halt is only
        the final bounded fallback.
        """
        port = self._winrm_forwarded_port(machine)
        if port and self._wait_winrm_ready(port, 30):
            Log.info(f'GOAD Kingdoms: requesting graceful in-guest shutdown for {machine}')
            try:
                self._winrm_session(port).run_ps(
                    "shutdown.exe /s /t 0 /f | Out-Null"
                )
            except Exception as exc:
                # A successful shutdown normally destroys WinRM before pywinrm
                # receives a response. Power state below decides success.
                Log.warning(
                    f'GOAD Kingdoms: {machine} shutdown command interrupted WinRM: {exc}'
                )

            if self._wait_machine_stopped(machine, 120):
                Log.success(f'GOAD Kingdoms: {machine} completed graceful Windows shutdown')
                return True

        vmx = self._vmx_path(machine)
        if vmx:
            Log.warning(
                f'GOAD Kingdoms: {machine} did not stop through WinRM; '
                'trying VMware Tools soft shutdown'
            )
            try:
                soft = subprocess.run(
                    ['vmrun', '-T', 'ws', 'stop', vmx, 'soft'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                    timeout=45,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                Log.warning(f'GOAD Kingdoms: VMware soft stop failed for {machine}: {exc}')
            else:
                if soft.returncode == 0 and self._wait_machine_stopped(machine, 120):
                    Log.success(f'GOAD Kingdoms: {machine} completed VMware soft shutdown')
                    return True
                detail = soft.stderr.strip() or soft.stdout.strip()
                if detail:
                    Log.warning(f'GOAD Kingdoms: VMware soft stop for {machine}: {detail}')

        Log.warning(
            f'GOAD Kingdoms: graceful shutdown paths did not stop {machine}; '
            'using bounded forced halt as final fallback'
        )
        if not self._run_vagrant_bounded(['halt', machine, '-f'], timeout=45):
            Log.error(f'GOAD Kingdoms: forced halt failed for {machine}')
            return False
        if not self._wait_machine_stopped(machine, 60):
            Log.error(f'GOAD Kingdoms: {machine} is still running after forced halt')
            return False
        return True

    def _north_existing_canonical_ready(self, machine):
        """Recognize an already-running, exactly owned NORTH guest on retry.

        After direct first-boot recovery, the original Windows VM can satisfy
        the complete canonical readiness contract even though Vagrant's guest
        adapter action failed. In that state, repeating Vagrant up is circular
        and can spend another ten minutes before doing any useful work.

        This is deliberately read-only: the direct proof checks the registered
        running VMX, both in-guest NIC MACs, NAT WinRM identity, fixed lab IP,
        persistent internal route, HTTPS listener and VMware Tools. Never skip
        Vagrant just because a VMX exists, a DHCP lease exists, or a TCP port is
        open. None means the regular Vagrant path remains responsible.
        """
        if self.lab_name != 'NORTH' or not self._vmx_path(machine):
            return None

        from goad.course1_direct_winrm import (
            NorthGuestRecoveryBlocked, NorthGuestIdentityMismatch,
            prove_canonical_guest,
        )
        try:
            address = prove_canonical_guest(self.path, machine, timeout=30)
        except NorthGuestIdentityMismatch as exc:
            # An authenticated foreign guest is not a safe recovery candidate.
            Log.error(
                f'NORTH: {machine} existing direct WinRM guest identity differs '
                f'from its registered VMX; refusing Vagrant resume: {exc}'
            )
            return False
        except NorthGuestRecoveryBlocked as exc:
            Log.info(
                f'NORTH: {machine} does not yet pass existing-guest canonical '
                f'readiness; retaining normal Vagrant bring-up: {exc}'
            )
            return None

        if not hasattr(self, '_north_first_boot_nat_addresses'):
            self._north_first_boot_nat_addresses = {}
        self._north_first_boot_nat_addresses[machine] = address
        Log.success(
            f'NORTH: {machine} already recovered and canonical at NAT {address}; '
            'skipping redundant Vagrant up/guest adapter operation'
        )
        return True


    def _north_existing_ws01_orphan_before_vagrant(self, machine):
        """Return True for strictly recovered WS01, False for blocked, None for fresh.

        On an interrupted NORTH resume, a known signed WS01 Tools orphan is
        inaccessible to the normal post-rearm gate because Vagrant runs first.
        Do not run Vagrant's generic guest bootstrap against that partial MSI.
        This is not a new-guest path, not a licensing/rearm action, and not a
        shortcut around canonical identity verification.
        """
        if (self.lab_name != 'NORTH' or machine != 'GOAD-WS01'
                or not self._vmx_path(machine)):
            return None

        from goad.course1_tools_transition import (
            inspect_owned_guest_tools, NorthToolsTransitionBlocked,
        )
        from goad.course1_direct_winrm import (
            NorthGuestRecoveryBlocked, owned_guest,
        )

        # Previous runs treated a missing/stale forwarded WinRM port as
        # permission to fall through to Vagrant's generic Tools bootstrap.
        # That silently bypassed the signed orphan recovery and repeated the
        # same VMware Tools failure. Only a VM that is NOT yet running may
        # retain the normal first-boot Vagrant path.
        try:
            owned_guest(self.path, machine)
        except NorthGuestRecoveryBlocked as exc:
            if str(exc) == 'Original guest is not uniquely running':
                Log.info(
                    'NORTH: WS01 is registered but not running; '
                    'normal Vagrant first boot remains authoritative'
                )
                return None
            Log.error(f'NORTH: WS01 pre-Vagrant owned VMX proof blocked: {exc}')
            return False

        Log.info('NORTH: original running WS01 requires authenticated '
                 'Tools inventory before any Vagrant fallback')
        try:
            port = self._winrm_forwarded_port(machine)
            if not port:
                Log.error(
                    'NORTH: original running WS01 has no forwarded WinRM port; '
                    'refusing generic Vagrant VMware Tools bootstrap'
                )
                return False
            if not self._wait_winrm_ready(port, 60):
                Log.error(
                    f'NORTH: original running WS01 WinRM port {port} did not '
                    'become authenticated within 60s; refusing Vagrant fallback'
                )
                return False
            _vmx, state = inspect_owned_guest_tools(
                self.path, machine, self._winrm_session(port)
            )
        except (NorthToolsTransitionBlocked, NorthGuestRecoveryBlocked,
                OSError, ValueError) as exc:
            Log.error(
                f'NORTH: original WS01 VMware Tools identity at pre-Vagrant '
                f'resume could not be proven: {exc}'
            )
            return False

        Log.info(f'NORTH_WS01_PRE_VAGRANT_TOOLS_STATE={state}')
        # Existing RUNNING WS01 is not a first boot. The previous helper
        # explicitly fell through to Vagrant for a fully missing Tools
        # inventory. On the fifth-install resume that caused another generic
        # vmrun installTools attempt outside the one-shot recovery journal.
        #
        # A healthy Tools inventory does not imply canonical readiness:
        # the caller has already failed complete IP/route/HTTPS/Tools proof.
        # Do not use Vagrant to compensate for that incomplete contract.
        if state == 'healthy':
            Log.error(
                'NORTH: running WS01 has healthy Tools but failed canonical '
                'guest readiness; refusing unreviewed Vagrant fallback'
            )
            return False
        if state not in ('partial', 'missing'):
            Log.error(
                f'NORTH: running WS01 returned unexpected Tools state {state!r}; '
                'refusing Vagrant fallback'
            )
            return False

        if state == 'partial':
            Log.warning(
                'NORTH: running WS01 has partial VMware Tools before Vagrant; '
                'requiring exact signed post-rearm orphan proof'
            )
        else:
            Log.warning(
                'NORTH: running WS01 has completely absent VMware Tools '
                'before Vagrant; using existing single-attempt recovery gate'
            )
        # This owns both the signed-partial path and the already-approved
        # all-missing recovery. Both share the exact original VMX/MAC/IP,
        # atomic WS01 repair marker and authenticated post-install proof.
        if not self._north_tools_transition_gate(
                machine, 'pre-vagrant-ws01-resume'):
            Log.error('NORTH: WS01 pre-Vagrant Tools repair refused or failed; '
                      'no generic Vagrant bootstrap fallback')
            return False
        # The Tools repair can reboot the guest. Full original VMX + both MACs,
        # canonical IP, internal route and WinRM HTTPS must be proved again
        # before skipping any Vagrant action.
        if self._north_existing_canonical_ready(machine) is not True:
            Log.error(
                'NORTH: repaired WS01 did not pass original canonical identity; '
                'refusing Vagrant fallback or another VMware Tools repair'
            )
            return False
        Log.success(
            'NORTH_WS01_PRE_VAGRANT_TOOLS_RECOVERED=PASS'
        )
        return True

    def _north_direct_first_boot_recovery(self, machine):
        """Bounded NORTH-only direct WinRM fallback; no Vagrant guest operations.

        Return None if the live exact guest cannot be authenticated and allow
        existing Vagrant recovery rules. Return False for a proven guest whose
        source-owned provisioning failed: never silently repeat state changes.
        """
        from goad.course1_direct_winrm import (
            NorthGuestRecoveryBlocked, NorthGuestIdentityMismatch,
            prove_guest, recover_north_first_boot,
        )
        try:
            forwarded_port = self._winrm_forwarded_port(machine)
        except Exception:
            forwarded_port = None
        try:
            _session, nat_ip, _guest = prove_guest(
                self.path, machine, timeout=90,
                forwarded_port=forwarded_port,
            )
        except NorthGuestIdentityMismatch as exc:
            Log.error(
                f'NORTH: {machine} forwarded WinRM identity does not match the '
                f'exact owned VMware guest; refusing recovery: {exc}'
            )
            return False
        except NorthGuestRecoveryBlocked as exc:
            Log.warning(
                f'NORTH: direct guest proof unavailable for {machine}: {exc}'
            )
            return None
        try:
            if recover_north_first_boot(
                    self.path, machine, address_hint=nat_ip):
                if not hasattr(self, '_north_first_boot_nat_addresses'):
                    self._north_first_boot_nat_addresses = {}
                self._north_first_boot_nat_addresses[machine] = nat_ip
                Log.success(
                    f'NORTH: {machine} exact-VMX direct WinRM provisioning and '
                    'canonical IP/HTTPS readiness verified'
                )
                return True
        except NorthGuestRecoveryBlocked as exc:
            Log.error(f'NORTH: {machine} direct recovery failed after guest identity proof: {exc}')
        return False

    def _north_tools_transition_gate(self, machine, phase):
        """Prove or repair one exact NORTH Windows guest at a reboot boundary.

        The inherited VMTools bootstrap may return False ONLY because VMware
        host-side guest IP telemetry failed. Its exit code is not authoritative;
        exact post-reboot guest identity + Tools + WinRM + canonical IP is.
        A fully absent Tools package gets ONE guarded install. Partial Tools
        registration is a hard stop, never an automatic overwrite.
        """
        if (self.lab_name != 'NORTH' or
                machine not in ('GOAD-DC01', 'GOAD-DC02', 'GOAD-SRV02', 'GOAD-WS01') or
                phase not in ('post-ws01-eval', 'pre-exercise-isolation',
                              'pre-vagrant-ws01-resume') or
                (phase in ('post-ws01-eval', 'pre-vagrant-ws01-resume')
                 and machine != 'GOAD-WS01')):
            Log.error('NORTH: unexpected VMware Tools transition scope')
            return False

        from goad.course1_tools_transition import (
            NorthToolsTransitionBlocked, inspect_owned_guest_tools,
            prove_idle_signed_original_ws01_orphan,
        )
        from goad.course1_direct_winrm import NorthGuestRecoveryBlocked
        from goad.course1_install_diagnostics import emit

        def record(signature, outcome, attempts=0):
            emit(self.path, machine=machine, phase=phase,
                 signature=signature, result=outcome, attempts=attempts)

        try:
            # Never install against a forged forwarded endpoint or a foreign VM.
            port = self._winrm_forwarded_port(machine)
            if not port or not self._wait_winrm_ready(port, 60):
                Log.error(f'NORTH: {machine} WinRM unavailable at {phase}')
                return False
            vmx, state = inspect_owned_guest_tools(
                self.path, machine, self._winrm_session(port)
            )
        except (NorthToolsTransitionBlocked, NorthGuestRecoveryBlocked,
                OSError, ValueError) as exc:
            record('VMTOOLS_IDENTITY_OR_TRANSPORT_BLOCKED', 'blocked')
            Log.error(f'NORTH: {machine} original guest/Tools preflight blocked at {phase}: {exc}')
            return False

        if state == 'healthy':
            if self._authenticated_guest_install_ready(machine, timeout=20):
                record('VMTOOLS_HEALTHY', 'pass')
                Log.success(f'NORTH: {machine} VMware Tools healthy at {phase}')
                return True
            record('VMTOOLS_READINESS_INCOMPLETE', 'blocked')
            Log.error(f'NORTH: {machine} Tools exist but canonical guest readiness incomplete at {phase}')
            return False

        if state == 'partial':
            record('VMTOOLS_PARTIAL', 'observed')
            # Post-rearm Windows services may still be converging. Only
            # OBSERVE the exact original guest three more times. No Tools
            # reinstall or service mutation while registration is ambiguous.
            if phase == 'post-ws01-eval':
                for check in range(3):
                    time.sleep(5)
                    try:
                        new_vmx, new_state = inspect_owned_guest_tools(
                            self.path, machine, self._winrm_session(port)
                        )
                    except (NorthToolsTransitionBlocked, NorthGuestRecoveryBlocked,
                            OSError, ValueError) as exc:
                        record('VMTOOLS_IDENTITY_OR_TRANSPORT_BLOCKED', 'blocked')
                        Log.error(f'NORTH: {machine} post-evaluation Tools observation failed: {exc}')
                        return False
                    if new_vmx != vmx:
                        record('VMTOOLS_IDENTITY_OR_TRANSPORT_BLOCKED', 'blocked')
                        Log.error('NORTH: refusing changed guest identity during Tools convergence')
                        return False
                    state = new_state
                    if state != 'partial':
                        break
                if state == 'healthy':
                    if self._authenticated_guest_install_ready(machine, timeout=20):
                        record('VMTOOLS_HEALTHY', 'pass')
                        Log.success(f'NORTH: {machine} Tools converged without installer replay')
                        return True
                    record('VMTOOLS_READINESS_INCOMPLETE', 'blocked')
                    return False

            if state == 'partial':
                # One narrowly approved recoverable exception: the exact WS01
                # signed 13.1.0 binary left by the known post-rearm MSI
                # interruption, with no current MSI transaction or VMTools
                # registration, on an unchanged original MAC-bound guest.
                # All other partial installations remain hard-blocked.
                if machine == 'GOAD-WS01' and phase in (
                        'post-ws01-eval', 'pre-vagrant-ws01-resume'):
                    try:
                        approved = prove_idle_signed_original_ws01_orphan(
                            self.path, machine, vmx, self._winrm_session(port)
                        )
                    except (NorthToolsTransitionBlocked, NorthGuestRecoveryBlocked,
                            OSError, ValueError) as exc:
                        record('VMTOOLS_IDENTITY_OR_TRANSPORT_BLOCKED', 'blocked')
                        Log.error(f'NORTH: WS01 signed orphan proof unavailable: {exc}')
                        return False
                    if approved:
                        state = 'known_idle_orphan'
                    else:
                        record('VMTOOLS_PARTIAL_PERSISTENT', 'blocked')
                        Log.error('NORTH: WS01 VMware Tools partially registered but '
                                  'not the reviewed signed idle orphan fingerprint')
                        return False
                else:
                    record('VMTOOLS_PARTIAL_PERSISTENT', 'blocked')
                    Log.error(f'NORTH: {machine} VMware Tools remain partially installed '
                              f'at {phase}; diagnostic journal saved. No reinstall attempted')
                    return False

        if state not in ('missing', 'known_idle_orphan'):
            record('VMTOOLS_PARTIAL_PERSISTENT', 'blocked')
            Log.error('NORTH: unsupported VMware Tools transition state')
            return False

        if state == 'known_idle_orphan':
            record('VMTOOLS_WS01_SIGNED_IDLE_ORPHAN', 'observed')
        else:
            record('VMTOOLS_MISSING', 'observed')
        instance = os.path.dirname(os.path.realpath(self.path))
        # The same guest repair must never be repeated because the resume
        # encountered it before Vagrant and later after license maintenance.
        # Share WS01's original post-evaluation one-shot marker across phases.
        marker_phase = ('post-ws01-eval' if machine == 'GOAD-WS01'
                        and phase in ('post-ws01-eval', 'pre-vagrant-ws01-resume')
                        else phase)
        marker = os.path.join(
            instance, f'.north-vmtools-{machine}-{marker_phase}.attempted'
        )
        # Protect against accidental replay after a failed Tools installation
        # that may already have changed Windows installer or reboot state.
        try:
            fd = os.open(
                marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                getattr(os, 'O_NOFOLLOW', 0), 0o600,
            )
        except OSError as exc:
            record('VMTOOLS_REPAIR_FAILED', 'blocked')
            Log.error(f'NORTH: {machine} Tools repair previously attempted or marker '
                      f'unavailable at {phase}: {exc}')
            return False
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(f'vm={machine}\nphase={phase}\nvmx={vmx}\n')
        record('VMTOOLS_REPAIR_ATTEMPTED', 'observed', attempts=1)

        Log.warning(f'NORTH: {machine} VMware Tools '
                    f'{"signed idle orphan" if state == "known_idle_orphan" else "absent"} '
                    f'at {phase}; invoking the original Tools installer once')
        try:
            result = self._install_vmware_tools(machine, vmx, port)
            if not result:
                Log.warning(
                    f'NORTH: {machine} installer returned failure; checking '
                    'authenticated guest state because VMware IP telemetry is advisory'
                )
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                if self._authenticated_guest_install_ready(machine, timeout=12):
                    # Reaffirm both MACs and VMware Tools after any install reboot.
                    final_vmx, final_state = inspect_owned_guest_tools(
                        self.path, machine, self._winrm_session(port)
                    )
                    if final_vmx == vmx and final_state == 'healthy':
                        record('VMTOOLS_REPAIR_VERIFIED', 'pass', attempts=1)
                        Log.success(f'NORTH: {machine} exact guest VMware Tools '
                                    f'recovered after {phase}')
                        return True
                time.sleep(5)
        except (NorthToolsTransitionBlocked, NorthGuestRecoveryBlocked,
                OSError, ValueError) as exc:
            Log.error(f'NORTH: {machine} VMware Tools recovery failed at {phase}: {exc}')
        record('VMTOOLS_REPAIR_FAILED', 'failed', attempts=1)
        Log.error(f'NORTH: {machine} VMware Tools not verified after repair at {phase}; '
                  'repair marker retained; do not replay automatically')
        return False

    def finalize_install(self):
        """Keep NORTH pre-isolation guest-control health strict and recoverable."""
        if self.lab_name != 'NORTH':
            return super().finalize_install()
        if self._course1_unwired():
            return False
        mode = self.get_runtime_mode()
        if mode != 'provisioning':
            # A genuine first install deliberately skips the AD-aware mode
            # controller before build.yml creates Active Directory. At this
            # point the full Ansible run has succeeded, so the *same* controller
            # can establish and validate the recorded provisioning state before
            # entering exercise mode. Never synthesize the marker ourselves.
            if mode != 'unknown' or not self._fresh_install_bootstrap_pending():
                Log.error('NORTH: refusing final isolation without recorded provisioning mode')
                return False
            Log.info(
                'NORTH: completed fresh Ansible provisioning; establishing '
                'recorded provisioning mode through the AD-aware controller'
            )
            if not self.set_runtime_mode('provisioning'):
                Log.error(
                    'NORTH: post-AD provisioning mode transition failed; '
                    'exercise isolation not started'
                )
                return False
            if self.get_runtime_mode() != 'provisioning':
                Log.error(
                    'NORTH: mode controller did not persist provisioning state; '
                    'exercise isolation not started'
                )
                return False
        # Ensure a missing Tools service cannot make the first soft shutdown
        # fail after the complete and expensive 21-play Ansible provisioning.
        for machine in ('GOAD-SRV02', 'GOAD-WS01', 'GOAD-DC02', 'GOAD-DC01'):
            if not self._north_tools_transition_gate(machine, 'pre-exercise-isolation'):
                Log.error(f'NORTH: {machine} failed pre-isolation guest-control gate; '
                          'AD was not replayed and isolation not started')
                return False
        return super().finalize_install()

    def _authenticated_guest_install_ready(self, machine, timeout=60):
        """Prove guest health independently of VMware host-side IP telemetry.

        Workstation/VIX can temporarily report that VMware Tools are not running
        even while the authenticated Windows guest has a running VMTools service,
        vmtoolsd.exe, working WinRM, and its canonical KINGDOMS address.

        Host getGuestIPAddress reporting is useful telemetry, but is not the
        authoritative installation-health signal.
        """
        expected = getattr(self, 'management_hosts', {}).get(machine)
        if not expected:
            return False

        try:
            port = self._winrm_forwarded_port(machine)
        except Exception:
            if self.lab_name != 'NORTH':
                return False
            port = None

        if self.lab_name == 'NORTH' and (
                not port or not self._wait_winrm_ready(port, min(timeout, 10))):
            # The generated Vagrant port registry can survive an incomplete
            # VMware NAT forward transaction. The existing exact VMX, direct
            # guest identity and strict final lab IP/HTTPS gate are authoritative.
            from goad.course1_direct_winrm import (
                NorthGuestRecoveryBlocked, prove_canonical_guest,
            )
            try:
                prove_canonical_guest(
                    self.path, machine, timeout=min(timeout, 90),
                    address_hint=getattr(
                        self, '_north_first_boot_nat_addresses', {}
                    ).get(machine),
                )
            except NorthGuestRecoveryBlocked:
                return False
            return True

        if not port:
            return False

        if self.lab_name != 'NORTH' and not self._wait_winrm_ready(port, timeout):
            return False

        try:
            session = self._winrm_session(port)
            result = session.run_ps(rf"""
$ErrorActionPreference = 'Stop'

$svc = Get-Service -Name VMTools -ErrorAction Stop
$file = Test-Path 'C:\Program Files\VMware\VMware Tools\vmtoolsd.exe'
$proc = Get-Process -Name vmtoolsd -ErrorAction SilentlyContinue
$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
    Where-Object {{ $_.IPAddress -eq '{expected}' }} |
    Select-Object -First 1

if (
    $svc.Status -eq 'Running' -and
    $file -and
    $proc -and
    $ip
) {{
    Write-Output 'GOAD_KINGDOMS_GUEST_READY'
}}
# Emit evidence without relaxing the original all-conditions-ready gate.
Write-Output "GOAD_KINGDOMS_GUEST_DIAG|tools_service=$($svc.Status)|tools_file=$([bool]$file)|tools_process=$([bool]$proc)|canonical_ip=$([bool]$ip)"
""")
        except Exception as exc:
            Log.warning(
                f'GOAD Kingdoms: authenticated guest readiness check failed for '
                f'{machine}: {type(exc).__name__}'
            )
            return False

        ready = (
            result.status_code == 0
            and b'GOAD_KINGDOMS_GUEST_READY' in result.std_out
        )
        if self.lab_name == 'NORTH' and not ready:
            # Authenticated forwarded WinRM can return before Windows restores
            # its VMware Tools process or static exercise NIC after a reboot.
            # Expose exactly which existing readiness gate is absent.
            output = result.std_out.decode('utf-8', errors='replace')
            details = next((
                line for line in output.splitlines()
                if line.startswith('GOAD_KINGDOMS_GUEST_DIAG|')
            ), 'guest-readiness-details-unavailable')
            Log.warning(
                f'NORTH: {machine} WinRM responded but authenticated readiness '
                f'has not converged: {details}; status={result.status_code}'
            )
        return ready

    def _north_post_rearm_guest_ready(self, machine, timeout=180):
        """Re-prove NORTH WS01 after evaluation reboot using bounded polling.

        The Ansible role proves Windows evaluation grace and WinRM return, not
        necessarily the VMware Tools service/process + canonical exercise IP.
        This read-only gate preserves _authenticated_guest_install_ready's
        conditions and its exact-VMX direct fallback when forwarded NAT WinRM
        is missing. It never re-runs licensing, changes NICs or starts VMs.
        """
        if self.lab_name != 'NORTH' or machine != 'GOAD-WS01':
            Log.error('NORTH WS01 post-rearm readiness called outside its scope')
            return False
        deadline = time.monotonic() + timeout
        checks = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            checks += 1
            if self._authenticated_guest_install_ready(
                    machine, timeout=max(1, min(10, int(remaining)))):
                Log.success(
                    f'NORTH: {machine} post-rearm authenticated VMware Tools/'
                    f'WinRM/canonical IP ready after {checks} check(s)'
                )
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if checks == 1 or checks % 3 == 0:
                Log.info(
                    f'NORTH: {machine} post-rearm guest readiness not yet '
                    f'converged; checks={checks}; retry_window_s={int(remaining)}'
                )
            time.sleep(min(5, remaining))
        Log.error(
            f'NORTH: {machine} post-rearm guest health not proven after '
            f'{checks} checks; no AD provisioning attempted'
        )
        return False

    def _authenticated_guest_recovery_ready(self, machine, timeout=60):
        """Prove enough pre-provision guest health for one recovery cycle.

        A failed first Vagrant bring-up can stop before fix_ip.ps1 assigns the
        canonical KINGDOMS address. Requiring that address before permitting the
        recovery vagrant up --provision creates a circular dependency: the
        provisioner that assigns the address is never allowed to run.

        For this narrow failed-first-up path, require only authenticated
        forwarded WinRM plus a running VMware Tools service/process. The
        recovery cycle must still finish by passing the normal
        _ensure_vmware_tools gate, which requires the canonical KINGDOMS
        address before installation may continue.
        """
        try:
            port = self._winrm_forwarded_port(machine)
        except Exception:
            return False

        if not port or not self._wait_winrm_ready(port, timeout):
            return False

        try:
            result = self._winrm_session(port).run_ps(r"""
$ErrorActionPreference = 'Stop'
$svc = Get-Service -Name VMTools -ErrorAction Stop
$file = Test-Path 'C:\Program Files\VMware\VMware Tools\vmtoolsd.exe'
$proc = Get-Process -Name vmtoolsd -ErrorAction SilentlyContinue

if (
    $svc.Status -eq 'Running' -and
    $file -and
    $proc
) {
    Write-Output 'GOAD_KINGDOMS_RECOVERY_READY'
}
""")
        except Exception as exc:
            Log.warning(
                f'GOAD Kingdoms: pre-provision recovery readiness failed for '
                f'{machine}: {type(exc).__name__}'
            )
            return False

        return (
            result.status_code == 0
            and b'GOAD_KINGDOMS_RECOVERY_READY' in result.std_out
        )

    def _ensure_vmware_tools(self, machine):
        """Use authenticated guest state as authority for KINGDOMS readiness.

        VMware/VIX guest-IP reporting remains advisory. If authenticated WinRM,
        VMware Tools and the expected KINGDOMS IP are healthy, stale host-side
        telemetry must not trigger unnecessary Tools reinstall/reboot recovery.
        """
        if self.lab_name not in ('GOAD', 'NORTH') or machine not in self.goad_nomad_windows:
            return super()._ensure_vmware_tools(machine)

        previous = getattr(self, '_tools_reporting_context', None)
        self._tools_reporting_context = {
            'machine': machine,
            'restart_attempted': False,
        }

        try:
            # Prefer authenticated evidence from the actual Windows guest.
            if self._authenticated_guest_install_ready(machine):
                vmx = self._vmx_path(machine)
                if vmx and not self._poll_guest_ip_bounded(vmx, 10):
                    Log.warning(
                        f'GOAD Kingdoms: {machine} authenticated guest state is '
                        'healthy at its expected KINGDOMS address, but VMware '
                        'guest-IP reporting remains unavailable; treating host '
                        'telemetry as advisory'
                    )
                return True

            # Guest state is not yet proven. The inherited helper may install or
            # repair VMware Tools, but its success is not sufficient for
            # Kingdoms: it can succeed while the lab-facing NIC is still APIPA
            # or before fix_ip.ps1 has assigned the canonical address.
            super()._ensure_vmware_tools(machine)

            # Always re-prove the strict Kingdoms state after any inherited
            # repair. NAT WinRM and healthy Tools are recovery signals only.
            if self._authenticated_guest_install_ready(machine):
                vmx = self._vmx_path(machine)
                if vmx and not self._poll_guest_ip_bounded(vmx, 10):
                    Log.warning(
                        f'GOAD Kingdoms: {machine} recovered authenticated guest '
                        'health while VMware guest-IP reporting stayed unavailable; '
                        'continuing to canonical management-plane validation'
                    )
                return True

            return False
        finally:
            self._tools_reporting_context = previous

    def _poll_guest_ip_bounded(self, vmx, timeout):
        """Bound each local query as well as the overall polling window."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                result = subprocess.run(
                    ['vmrun', '-T', 'ws', 'getGuestIPAddress', vmx],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, check=False, timeout=min(10, remaining),
                )
                if result.returncode == 0:
                    try:
                        address = ipaddress.IPv4Address(result.stdout.strip())
                    except ipaddress.AddressValueError:
                        pass
                    else:
                        if not (address.is_link_local or address.is_loopback
                                or address.is_unspecified or address.is_multicast):
                            Log.success(f'GOAD_NOMAD: VMware guest IP reporting healthy ({address})')
                            return True
            except subprocess.TimeoutExpired:
                pass
            except OSError:
                return False
            time.sleep(max(0, min(5, deadline - time.monotonic())))
        return False

    def _restart_tools_reporting(self, machine, vmx):
        """Restart the existing guest service over authenticated forwarded WinRM.

        This repairs the observed host/guest reporting disagreement, without
        assigning a lab IP, provisioning Windows, or accepting a failed up.
        """
        try:
            ports = subprocess.run(
                [self.command.vagrant_bin, 'port', machine], cwd=self.path,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, check=False, timeout=15,
            )
            match = re.search(r'5985\s+\(guest\)\s+=>\s+(\d+)\s+\(host\)', ports.stdout)
            if ports.returncode != 0 or match is None:
                return False
            port = int(match.group(1))
            if not 0 < port < 65536:
                return False
            Log.warning(
                f'GOAD Kingdoms: {machine} guest IP reporting stalled; '
                'trying one VMTools service restart through authenticated WinRM'
            )
            result = self._winrm_session(port).run_ps(r'''
$ErrorActionPreference = 'Stop'
$svc = Get-Service -Name VMTools -ErrorAction Stop
if (-not (Test-Path 'C:\Program Files\VMware\VMware Tools\vmtoolsd.exe')) {
    throw 'VMware Tools executable is missing'
}
if ($svc.Status -ne 'Stopped') {
    $svc.Stop()
    $svc.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(20))
}
$svc.Start()
$svc.WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
Write-Output 'GOAD_VMTOOLS_RESTARTED'
''')
            if result.status_code != 0 or b'GOAD_VMTOOLS_RESTARTED' not in result.std_out:
                return False
            # The guest command must succeed AND the host must observe an IP.
            # Direct inventory WinRM remains a separate gate before Ansible.
            if self._poll_guest_ip_bounded(vmx, 60) and self._guest_tools_healthy(port):
                Log.success(f'GOAD Kingdoms: {machine} VMTools reporting recovered after service restart')
                return True
        except Exception as exc:
            Log.warning(f'GOAD Kingdoms: VMTools reporting repair failed for {machine}: {type(exc).__name__}')
        return False

    def _wait_guest_ip(self, vmx, timeout=180):
        context = getattr(self, '_tools_reporting_context', None)
        if context is None:
            return super()._wait_guest_ip(vmx, timeout)
        if self._poll_guest_ip_bounded(vmx, timeout):
            return True
        if context['restart_attempted']:
            return False
        # Set before invoking WinRM: errors must not allow repeated restarts.
        context['restart_attempted'] = True
        return self._restart_tools_reporting(context['machine'], vmx)

    def _recover_failed_windows_vagrant_up(self, machine):
        """Recover a failed fresh Windows ``vagrant up`` deterministically.

        A failed first bring-up does not necessarily mean VMware Tools are
        absent. Fresh StefanScherer guests can already have healthy Tools and a
        working forwarded WinRM endpoint while Vagrant's VMware guest channel
        still fails during adapter/provisioner setup.

        Recovery therefore preserves the now-proven guest state: shut Windows
        down gracefully first, verify VMware reports it stopped, then execute one
        bounded ``vagrant up --provision`` cycle. Finally re-prove VMware Tools
        and authenticated WinRM readiness before allowing installation to move to
        the next machine.
        """
        Log.warning(
            f'GOAD Kingdoms: {machine} first Vagrant bring-up failed despite '
            'recoverable guest readiness; starting a clean recovery provision cycle'
        )

        if not self._stop_failed_windows_guest_cleanly(machine):
            Log.error(
                f'GOAD Kingdoms: could not stop {machine} safely after failed Vagrant bring-up'
            )
            return False

        if not self._run_vagrant_bounded(['up', machine, '--provision'], timeout=600):
            Log.error(
                f'GOAD Kingdoms: {machine} failed the bounded Vagrant --provision recovery cycle'
            )
            return False

        if not self._ensure_vmware_tools(machine):
            Log.error(
                f'GOAD Kingdoms: {machine} completed Vagrant recovery but VMware Tools/WinRM '
                'did not return healthy'
            )
            return False

        Log.success(
            f'GOAD Kingdoms: {machine} completed a clean failed-bring-up recovery provision cycle'
        )
        return True

    def start_vm(self, vm_name):
        """Start one installed guest, plus its router dependency when needed."""
        if self._course1_unwired():
            return False
        if self.lab_name not in ('GOAD', 'NORTH'):
            return super().start_vm(vm_name)
        if vm_name not in self.goad_nomad_windows + ['GOAD-ROUTER']:
            Log.error(f'GOAD Kingdoms: unknown instance machine: {vm_name}')
            return False
        # Share preflight, sudo keepalive and finally-based mode restoration.
        return self.start(vm_name=vm_name)

    def stop_vm(self, vm_name):
        """Stop one instance guest locally; preserve routing for live Windows."""
        if self._course1_unwired():
            return False
        if self.lab_name not in ('GOAD', 'NORTH'):
            return super().stop_vm(vm_name)
        if vm_name not in self.goad_nomad_windows + ['GOAD-ROUTER']:
            Log.error(f'GOAD Kingdoms: unknown instance machine: {vm_name}')
            return False
        if not getattr(self, '_last_bounded_vagrant_reaped', True):
            Log.error('GOAD Kingdoms: an earlier Vagrant controller was not reaped; refusing concurrent VM changes')
            return False
        running = self._running_instance_vms()
        if running is None:
            return False
        if vm_name not in running:
            Log.success(f'GOAD Kingdoms: {vm_name} is already stopped')
            return True
        if vm_name == 'GOAD-ROUTER' and any(name in running for name in self.goad_nomad_windows):
            Log.error('GOAD Kingdoms: Windows guests are still running; use stop for the whole range or stop them before the router')
            return False
        return self._stop_machine_via_vmware(vm_name)

    # Preserve AD/DNS availability as other guests shut down, and make DC01
    # available before WS01 boots. Never inherit NORTH's segmented router policy.
    _purple_stop_order = (
        'PURPLE-WS01', 'PURPLE-LX01', 'PURPLE-DC01', 'PURPLE-WAZUH'
    )
    _purple_start_order = (
        'PURPLE-DC01', 'PURPLE-WAZUH', 'PURPLE-LX01', 'PURPLE-WS01'
    )

    def _purple_controller_busy(self):
        """Reject concurrent Vagrant work touching this exact PURPLE provider."""
        root = os.path.realpath(str(self.path))
        try:
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    argv = proc.info.get('cmdline') or []
                    if not any('vagrant' in str(a).lower() for a in argv):
                        continue
                    if os.path.realpath(proc.cwd()) != root:
                        continue
                    Log.error(
                        f'PURPLE: Vagrant controller PID {proc.pid} still owns this '
                        'provider; finish/reap it before changing VM power'
                    )
                    return True
                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    continue
                except (psutil.AccessDenied, OSError):
                    Log.error('PURPLE: unable to inspect a possible Vagrant controller')
                    return True
        except (psutil.Error, OSError) as exc:
            Log.error(f'PURPLE: Vagrant process inventory cannot be verified: {exc}')
            return True
        return False

    def _purple_power_action_ready(self):
        if self.lab_name != 'PURPLE' or not self.path:
            Log.error('PURPLE: no loaded instance for a power operation')
            return False
        if not getattr(self, '_last_bounded_vagrant_reaped', True):
            Log.error('PURPLE: prior bounded Vagrant controller was not reaped')
            return False
        return not self._purple_controller_busy()

    def _purple_registered_vmx(self):
        """Fail closed unless all four identities resolve inside THIS workspace."""
        if self.lab_name != 'PURPLE' or self.path is None:
            Log.error('PURPLE: no loaded PURPLE provider')
            return None
        registered = {}
        for machine in self._purple_stop_order:
            vmx = self._vmx_path(machine)
            if not vmx or not os.path.isfile(vmx):
                Log.error(f'PURPLE: registered VMware VMX is missing for {machine}')
                return None
            canonical = os.path.realpath(vmx)
            expected_root = os.path.realpath(os.path.join(
                str(self.path), '.vagrant', 'machines', machine,
                'vmware_desktop',
            ))
            if (os.path.islink(vmx) or
                    os.path.commonpath((expected_root, canonical)) != expected_root):
                Log.error(f'PURPLE: VMX for {machine} points outside its own Vagrant registration')
                return None
            if canonical in registered.values():
                Log.error('PURPLE: duplicate VMware VMX identity; refusing VM power changes')
                return None
            registered[machine] = canonical
        return registered

    def _purple_running_vms(self):
        """Inspect only registered PURPLE VMX identities, never all VMware guests."""
        registered = self._purple_registered_vmx()
        if registered is None:
            return None
        try:
            result = subprocess.run(
                ['vmrun', '-T', 'ws', 'list'], capture_output=True,
                text=True, check=False, timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            Log.error(f'PURPLE: unable to inspect VMware power state: {exc}')
            return None
        if result.returncode != 0 or not result.stdout.startswith('Total running VMs:'):
            Log.error('PURPLE: VMware running-guest inventory is unavailable or malformed')
            return None
        active = {
            os.path.realpath(line.strip())
            for line in result.stdout.splitlines()[1:] if line.strip()
        }
        return [name for name in self._purple_stop_order if registered[name] in active]

    def _purple_wait_for_power(self, machine, running, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self._purple_running_vms()
            if current is None:
                return False
            if (machine in current) == running:
                return True
            time.sleep(3)
        return False

    def _purple_soft_stop(self, machine):
        if machine not in self._purple_stop_order:
            Log.error(f'PURPLE: unknown machine {machine}; refusing shutdown')
            return False
        vmx = self._purple_registered_vmx()
        if vmx is None:
            return False
        active = self._purple_running_vms()
        if active is None:
            return False
        if machine not in active:
            Log.success(f'PURPLE: {machine} already stopped')
            return True
        Log.info(f'PURPLE: requesting VMware Tools graceful shutdown of {machine}')
        try:
            result = subprocess.run(
                ['vmrun', '-T', 'ws', 'stop', vmx[machine], 'soft'],
                capture_output=True, text=True, check=False, timeout=45,
            )
            if result.returncode:
                Log.warning(f'PURPLE: soft shutdown returned an error for {machine}; verifying guest power')
        except subprocess.TimeoutExpired:
            Log.warning(f'PURPLE: VMware soft-stop command timed out for {machine}; checking guest power')
        except OSError as exc:
            Log.error(f'PURPLE: VMware soft-stop command unavailable: {exc}')
            return False
        if self._purple_wait_for_power(machine, running=False, timeout=120):
            Log.success(f'PURPLE: {machine} stopped gracefully')
            return True
        Log.error(
            f'PURPLE: {machine} did not stop within the graceful window. '
            'No hard power-off attempted; manual guest diagnosis required'
        )
        return False

    def _purple_start_machine(self, machine):
        if machine not in self._purple_start_order:
            Log.error(f'PURPLE: unknown machine {machine}; refusing start')
            return False
        vmx = self._purple_registered_vmx()
        if vmx is None:
            return False
        active = self._purple_running_vms()
        if active is None:
            return False
        if machine in active:
            Log.success(f'PURPLE: {machine} already running')
            return True
        Log.info(f'PURPLE: starting installed VM {machine} without reprovisioning')
        try:
            result = subprocess.run(
                ['vmrun', '-T', 'ws', 'start', vmx[machine], 'nogui'],
                capture_output=True, text=True, check=False, timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            Log.error(f'PURPLE: VMware VM start failed for {machine}: {exc}')
            return False
        if result.returncode != 0:
            Log.error(f'PURPLE: VMware VM start returned an error for {machine}')
            return False
        if not self._purple_wait_for_power(machine, running=True, timeout=60):
            Log.error(f'PURPLE: {machine} did not reach VMware running state')
            return False
        Log.success(f'PURPLE: {machine} VM powered on (guest/application readiness is separate)')
        return True

    def _stop_purple_vms(self):
        """Stop only the installed PURPLE guests; never force power off."""
        if not self._purple_power_action_ready():
            return False
        for machine in self._purple_stop_order:
            if not self._purple_soft_stop(machine):
                return False
        remaining = self._purple_running_vms()
        if remaining is None:
            return False
        if remaining:
            Log.error('PURPLE: guest shutdown incomplete: ' + ', '.join(remaining))
            return False
        Log.success('PURPLE: all registered guests stopped; other VMware labs untouched')
        return True

    def _start_purple_vms(self):
        """Power on existing VMs only; this is NOT a fresh-install path."""
        if not self._purple_power_action_ready():
            return False
        for machine in self._purple_start_order:
            if not self._purple_start_machine(machine):
                return False
        Log.success('PURPLE: all guests powered on; AD and Wazuh service readiness must be checked separately')
        return True

    def stop(self):
        """Shut down members, then DCs, then the router without Vagrant NAT."""
        if self._course1_unwired():
            return False
        if self.lab_name == 'PURPLE':
            return self._stop_purple_vms()
        if self.lab_name not in ('GOAD', 'NORTH'):
            return super().stop()
        if not getattr(self, '_last_bounded_vagrant_reaped', True):
            Log.error('GOAD Kingdoms: an earlier Vagrant controller was not reaped; refusing concurrent VM changes')
            return False
        running = self._running_instance_vms()
        if running is None:
            return False
        if not running:
            Log.success('GOAD_NOMAD: all instance VMs are already stopped')
            return True

        Log.info('GOAD Kingdoms: local shutdown; Windows members first, domain controllers next, router last')
        # The canonical roster lists DCs before member servers/workstations.
        for machine in reversed(self.goad_nomad_windows):
            if machine in running:
                self._stop_machine_via_vmware(machine)

        remaining = self._running_instance_vms()
        if remaining is None:
            return False
        windows_remaining = [name for name in remaining if name in self.goad_nomad_windows]
        if windows_remaining:
            Log.error('GOAD Kingdoms: Windows shutdown incomplete; keeping router available: ' + ', '.join(windows_remaining))
            return False
        if 'GOAD-ROUTER' in remaining:
            self._stop_machine_via_vmware('GOAD-ROUTER')

        remaining = self._running_instance_vms()
        if remaining is None:
            return False
        if remaining:
            Log.error('GOAD Kingdoms: shutdown incomplete; still running: ' + ', '.join(remaining))
            return False
        Log.success('GOAD Kingdoms: all instance VMs stopped and VMware state verified (no Vagrant NAT communicator)')
        return True

    def _restore_exercise_nic_contract_offline(self):
        """Reassert persistent exercise isolation while restored guests are off."""
        running = self._running_instance_vms()
        if running is None:
            return False

        active_windows = [
            machine for machine in self.goad_nomad_windows if machine in running
        ]
        if active_windows:
            Log.error(
                'GOAD Kingdoms: refusing offline NIC normalization while Windows '
                'guests are running: ' + ', '.join(active_windows)
            )
            return False

        pattern = re.compile(
            r'^\s*ethernet0\.startConnected\s*=.*$',
            re.IGNORECASE | re.MULTILINE,
        )

        for machine in self.goad_nomad_windows:
            vmx = self._vmx_path(machine)
            if not vmx or not os.path.isfile(vmx):
                Log.error(
                    f'GOAD Kingdoms: restored VMX is missing for {machine}; '
                    'cannot reassert exercise NIC isolation'
                )
                return False

            with open(vmx, 'r', encoding='utf-8') as handle:
                text = handle.read()

            replacement = 'ethernet0.startConnected = "FALSE"'
            if pattern.search(text):
                text = pattern.sub(replacement, text)
            else:
                if text and not text.endswith('\n'):
                    text += '\n'
                text += replacement + '\n'

            with open(vmx, 'w', encoding='utf-8') as handle:
                handle.write(text)

            with open(vmx, 'r', encoding='utf-8') as handle:
                verify = handle.read()
            if not re.search(
                r'^\s*ethernet0\.startConnected\s*=\s*"FALSE"\s*$',
                verify,
                re.IGNORECASE | re.MULTILINE,
            ):
                Log.error(
                    f'GOAD Kingdoms: failed to restore {machine} persistent '
                    'management NIC isolation'
                )
                return False

            Log.success(
                f'GOAD Kingdoms: {machine} restored with '
                'ethernet0.startConnected=FALSE'
            )

        return True

    def reset(self):
        """Restore the latest snapshot and normalize segmented exercise state.

        Some VMware Workstation/Vagrant plugin builds start guests during
        ``snapshot pop`` even when ``--no-start`` is supplied. The generated
        Vagrantfile also intentionally carries ``ethernet0.startConnected=TRUE``
        for provisioning compatibility, so an auto-start can overwrite a clean
        exercise snapshot's persistent management-NIC state.

        Treat ``--no-start`` as a preference, not a guarantee. If the provider
        starts restored guests in recorded exercise mode, stop that restored
        range locally, reassert ``ethernet0.startConnected=FALSE`` while every
        Windows VM is powered off, and only then return control to GOAD's
        existing hardened ``start()`` path.
        """
        if self._course1_unwired():
            return False
        if self.lab_name not in ('GOAD', 'NORTH'):
            return super().reset()

        if not getattr(self, '_last_bounded_vagrant_reaped', True):
            Log.error(
                'GOAD Kingdoms: previous Vagrant cleanup is incomplete; '
                'refusing snapshot restore'
            )
            return False

        mode = self.get_runtime_mode()
        if self.lab_name == 'NORTH':
            # Vagrant pop picks the *oldest* parent push when VMware reports
            # a nested 'parent/child' snapshot tree, and the provider may
            # auto-start restored guests despite --no-start. This breaks
            # exercise isolation before NIC normalization and was observed
            # during the first NORTH reset acceptance test.
            #
            # NORTH only: resolve the newest matching generation across all
            # five *original* registered VMX, require every guest to be off,
            # then use the official vmrun offline revert. Full KINGDOMS
            # retains its existing Vagrant snapshot behavior unchanged.
            try:
                restore_north_offline_snapshots(
                    self.path, self._vmx_path, log=Log.info,
                )
            except NorthSnapshotRestoreError as exc:
                Log.error(
                    'NORTH snapshot restore refused or partially failed: '
                    f'{exc}. Do not retry until the guest/snapshot state is audited'
                )
                return False
        else:
            Log.info(
                'GOAD Kingdoms: restoring latest snapshot without auto-start; '
                'segmented lifecycle will normalize restored state afterward'
            )
            if not self._run_vagrant_bounded(
                ['snapshot', 'pop', '--no-delete', '--no-start'],
                timeout=900,
            ):
                Log.error('GOAD Kingdoms: snapshot restore failed')
                return False

        running = self._running_instance_vms()
        if running is None:
            return False

        if mode == 'exercise':
            if running:
                Log.warning(
                    'GOAD Kingdoms: VMware provider auto-started restored guests '
                    'despite --no-start; stopping them before exercise NIC '
                    'normalization: ' + ', '.join(running)
                )
                if not self.stop():
                    Log.error(
                        'GOAD Kingdoms: could not stop auto-started restored guests; '
                        'refusing to continue reset'
                    )
                    return False

            if not self._restore_exercise_nic_contract_offline():
                return False

            Log.success(
                'GOAD Kingdoms: snapshot restored and offline exercise NIC '
                'contract reasserted; ready for hardened segmented start'
            )
            return True

        Log.success(
            f'GOAD Kingdoms: snapshot restored for recorded {mode} mode; '
            'ready for hardened segmented start'
        )
        return True

    def install(self):
        """Bring up a segmented GOAD instance with fail-closed Windows recovery."""
        if self._course1_unwired():
            return False
        if self.lab_name not in ('GOAD', 'NORTH'):
            return super().install()
        if not getattr(self, '_last_bounded_vagrant_reaped', True):
            Log.error('GOAD Kingdoms: previous Vagrant cleanup is incomplete; refusing guest bring-up')
            return False

        # This override owns the complete Kingdoms bring-up path, so it must
        # explicitly retain the inherited host-network preflight.  Without it,
        # a missing host-address helper/timer was discovered only after every
        # guest had spent minutes coming up and provisioning routes were finally
        # enabled.  Fail (or repair the host setup) before touching any VM.
        if not self.prepare_install():
            Log.error(
                'GOAD Kingdoms: segmented VMware host-network preflight failed; '
                'no guest bring-up was attempted'
            )
            return False

        if not self._sync_goad_nomad_inventories():
            return False

        if not self._sync_goad_nomad_vagrantfile_compatibility():
            return False

        # Bring up the router independently so a Windows guest failure cannot
        # prevent creation of the routing plane. Linux keeps the normal SSH path.
        Log.info('GOAD_NOMAD: bringing up segmented router')
        if not self._bring_up_router():
            Log.error('GOAD_NOMAD: failed to bring up GOAD-ROUTER')
            return False

        # A fresh Windows box can fail its first VMware/Vagrant guest operation
        # for two different reasons: Tools may genuinely be absent, or Tools may
        # already be healthy while Vagrant's guest-communication/provisioner
        # transition is still unstable. _ensure_vmware_tools() covers the first
        # case and proves baseline guest readiness for both. Any failed first
        # vagrant up then gets one clean graceful-stop -> up --provision recovery.
        for machine in self.goad_nomad_windows:
            Log.info(f'GOAD_NOMAD: bringing up {machine}')
            north_direct = None
            if self.lab_name == 'NORTH':
                north_direct = self._north_existing_canonical_ready(machine)
                if north_direct is False:
                    return False
                if north_direct is None and machine == 'GOAD-WS01':
                    north_direct = self._north_existing_ws01_orphan_before_vagrant(
                        machine
                    )
                    if north_direct is False:
                        return False
            if north_direct is True:
                # Only the strict authenticated canonical guest proof permits
                # skipping Vagrant on the same registered running VM. This
                # includes the source-provisioned DC01 recovered by the operator
                # after its original first-up attempt failed.
                first_up = True
            else:
                first_up = self.command.run_vagrant(['up', machine], self.path)

            # A *fresh* NORTH Windows box may be healthy on its vmnet8 NIC
            # after the VMware Vagrant provider failed inside its guest adapter
            # operation. Re-running the same Vagrant adapter action for 600s is
            # circular. Only the exact VMX + in-guest MAC and Tools proof can
            # authorize replaying existing Windows Vagrant scripts directly.
            if self.lab_name == 'NORTH' and not first_up:
                north_direct = self._north_direct_first_boot_recovery(machine)
                if north_direct is False:
                    return False

            tools_ready = (north_direct is True or
                           self._ensure_vmware_tools(machine))
            if not tools_ready and self.lab_name == 'NORTH':
                north_direct = self._north_direct_first_boot_recovery(machine)
                if north_direct is False:
                    return False
                if north_direct is True:
                    tools_ready = True

            recovery_ready = False
            if not tools_ready:
                recovery_ready = self._authenticated_guest_recovery_ready(machine)
                if not recovery_ready:
                    return False
                Log.warning(
                    f'GOAD Kingdoms: {machine} has authenticated WinRM and healthy '
                    'VMware Tools but has not reached its canonical KINGDOMS address; '
                    'allowing one bounded recovery provision cycle'
                )

            # A failed first up always gets the deterministic recovery cycle.
            # Also recover an existing/resumed guest when Vagrant itself returns
            # success but strict Kingdoms readiness is still missing. This is the
            # exact interrupted state where the NAT adapter works, the lab NIC is
            # APIPA, and fix_ip.ps1 has not completed.
            if (not first_up or not tools_ready) and north_direct is not True:
                # A *verified* forwarded WinRM/Tools guest must not re-enter a
                # second Vagrant guest adapter operation merely because VIX
                # telemetry could not identify its NAT IP. Fail with a precise
                # identity/bootstrap error instead of spending another 600s.
                if self.lab_name == 'NORTH' and recovery_ready:
                    Log.error(
                        f'NORTH: {machine} has authenticated forwarded WinRM '
                        'but no verified direct recovery; refusing circular '
                        'Vagrant guest adapter retry'
                    )
                    return False
                if not self._recover_failed_windows_vagrant_up(machine):
                    Log.error(
                        f'GOAD_NOMAD: {machine} still failed after clean Vagrant recovery'
                    )
                    return False

            # The mayfly/windows10 WS01 box can be a TIMEBASED_EVAL image
            # whose exhausted grace triggers recurring WLMS shutdowns.
            # Run the *existing* Kingdoms settings/eval_rearm role through
            # the verified Vagrant NAT WinRM mapping immediately after
            # WS01 is created, BEFORE the long build.yml/AD provisioning.
            # This also prevents a 30-minute fresh install from passing
            # VMware bring-up only to lose WS01 during first Ansible.
            if self.lab_name == 'NORTH' and machine == 'GOAD-WS01':
                maintenance = self._script('north-ws01-eval-maintenance.py')
                if maintenance is None:
                    Log.error('NORTH: WS01 license maintenance helper is missing')
                    return False
                try:
                    repaired = subprocess.run(
                        ['python3', maintenance, '--provider-dir', self.path],
                        check=False, timeout=2400,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    Log.error(f'NORTH: WS01 license maintenance failed: {exc}')
                    return False
                if repaired.returncode != 0:
                    Log.error(
                        'NORTH: WS01 time-based Windows evaluation is not ready; '
                        'refusing AD provisioning with a shutdown-prone guest'
                    )
                    return False
                # WS01 evaluation rearm can remove or interrupt VMware Tools.
                # Prove exact VMX and both NIC MACs before any bounded repair,
                # then retain the existing strict post-rearm readiness gate.
                if not self._north_tools_transition_gate(machine, 'post-ws01-eval'):
                    Log.error('NORTH: WS01 post-evaluation VMware Tools recovery blocked')
                    return False
                if not self._north_post_rearm_guest_ready(machine, timeout=180):
                    Log.error('NORTH: WS01 post-rearm lab WinRM/IP is not ready')
                    return False

        # The host has no vmnet20/vmnet30 adapters, so local Ansible must
        # temporarily reach those protected networks through GOAD-ROUTER after
        # Vagrant has brought the complete instance up.
        if self.lab_name == 'NORTH':
            # Native reduced topology has exactly one parent-domain route.
            # Do not run the GOAD helper that adds an Essos route.
            if not self._enable_provisioning_routes():
                return False
            return True

        route_script = GoadPath.get_script_file('provisioning-routes.sh')
        if not os.path.isfile(route_script):
            Log.error(f'GOAD_NOMAD provisioning route helper not found: {route_script}')
            return False

        Log.info('GOAD_NOMAD: enabling temporary host routes for local Ansible provisioning')
        route_result = subprocess.run(
            ['sudo', '-n', 'bash', route_script, 'enable'],
            check=False,
        )
        if route_result.returncode != 0:
            Log.error('GOAD_NOMAD: failed to enable temporary provisioning routes')
            return False

        Log.warning(
            'GOAD_NOMAD: provisioning routes are temporary and must be removed before exercise mode'
        )
        return True

    def _ensure_installed_member_time_policy(self, machine, host):
        """Backfill the bounded NT5DS rediscovery policy on installed members.

        Fresh Kingdoms installs receive this policy through Ansible. Existing
        installed ranges are migrated here after direct WinRM is available so
        a transient early-boot NT5DS discovery miss cannot leave W32Time in the
        Windows default 15-minute peer-resolution backoff. This changes only
        W32Time client retry policy; it never rewrites trust or directory state.
        """
        if machine not in ('GOAD-SRV02', 'GOAD-SRV03', 'GOAD-WS01'):
            return True

        script = r"""
$ErrorActionPreference = 'Stop'
$parameters = 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\Parameters'
$ntpClient = 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpClient'

$type = (Get-ItemProperty $parameters -Name Type -ErrorAction Stop).Type
if ($type -ine 'NT5DS') {
    throw "W32Time Type is '$type', expected NT5DS"
}

$changed = $false
$desired = @{
    ResolvePeerBackoffMinutes = 1
    ResolvePeerBackoffMaxTimes = 0
}

foreach ($entry in $desired.GetEnumerator()) {
    $current = Get-ItemPropertyValue $ntpClient -Name $entry.Key -ErrorAction SilentlyContinue
    if ($null -eq $current -or [int]$current -ne [int]$entry.Value) {
        New-ItemProperty $ntpClient -Name $entry.Key -Value ([int]$entry.Value) -PropertyType DWord -Force | Out-Null
        $changed = $true
    }
}

$reloadState = 'not-required'
if ($changed) {
    # W32Time may still be START_PENDING during a cold boot. Error 1061
    # (0x425) means the service cannot accept the configuration-control
    # notification yet, so retry within a small bounded window instead of
    # failing the entire installed-range start.
    $reloadState = 'failed'
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        & w32tm.exe /config /update | Out-Null
        $updateRc = $LASTEXITCODE
        if ($updateRc -eq 0) {
            $reloadState = 'applied'
            break
        }

        if ($attempt -lt 12) {
            Start-Sleep -Seconds 5
        }
    }

    if ($reloadState -ne 'applied') {
        throw "w32tm /config /update did not become available within 60s; last exit code $updateRc"
    }
}

Write-Output ("KINGDOMS_NT5DS_BACKOFF_READY|changed={0}|reload={1}|minutes=1|max_times=0" -f $changed.ToString().ToLowerInvariant(),$reloadState)
"""

        try:
            result = self._lab_winrm_session(host).run_ps(script)
        except Exception as exc:
            Log.error(f'GOAD Kingdoms: NT5DS backoff policy failed for {machine}: {exc}')
            return False

        if (
            result.status_code == 0
            and b'KINGDOMS_NT5DS_BACKOFF_READY' in result.std_out
        ):
            detail = result.std_out.decode(errors="replace").strip()
            Log.success(f'GOAD Kingdoms: {machine} NT5DS peer rediscovery policy ready ({detail})')
            return True

        detail = (
            result.std_err.decode(errors="replace").strip()
            or result.std_out.decode(errors="replace").strip()
            or f'PowerShell status {result.status_code}'
        )
        Log.error(f'GOAD Kingdoms: NT5DS backoff policy failed for {machine}: {detail}')
        return False

    def _wait_installed_ad_ready(self, machine, host, timeout=300):
        """Wait for the AD dependency contract required by a cold start.

        WinRM alone is not sufficient for Active Directory guests. Domain
        controllers must be advertising before dependent guests are allowed to
        boot, and members must establish their secure Netlogon session and
        authenticated domain-time source before startup is considered complete.
        This is validation only: no trust, machine-password or W32Time state is
        rewritten here.
        """
        contracts = {
            'GOAD-DC01': {
                'kind': 'dc',
                'domain': 'sevenkingdoms.local',
                'expected_source': None,
            },
            'GOAD-DC02': {
                'kind': 'dc',
                'domain': 'north.sevenkingdoms.local',
                'expected_source': 'kingslanding.sevenkingdoms.local',
            },
            'GOAD-DC03': {
                'kind': 'dc',
                'domain': 'essos.local',
                'expected_source': None,
            },
            'GOAD-SRV02': {
                'kind': 'member',
                'domain': 'north.sevenkingdoms.local',
                'dc': 'winterfell.north.sevenkingdoms.local',
            },
            'GOAD-SRV03': {
                'kind': 'member',
                'domain': 'essos.local',
                'dc': 'meereen.essos.local',
            },
            'GOAD-WS01': {
                'kind': 'member',
                'domain': 'north.sevenkingdoms.local',
                'dc': 'winterfell.north.sevenkingdoms.local',
            },
        }
        contract = contracts.get(machine)
        if contract is None:
            Log.error(f'GOAD Kingdoms: no installed-start AD contract for {machine}')
            return False

        if contract['kind'] == 'dc':
            expected_source = contract.get('expected_source')
            source_check = ''
            if expected_source:
                source_check = f"""
$source = (& w32tm.exe /query /source 2>$null | Out-String).Trim().TrimEnd('.')
if ($LASTEXITCODE -ne 0 -or $source -ine '{expected_source}') {{
    throw "W32Time source is '$source', expected {expected_source}"
}}
"""
            script = f"""
$ErrorActionPreference = 'Stop'
$Env:ADPS_LoadDefaultDrive = '0'

foreach ($serviceName in @('NTDS','DNS','ADWS','Netlogon','Kdc','W32Time')) {{
    $service = Get-Service -Name $serviceName -ErrorAction Stop
    if ($service.Status -ne 'Running') {{
        throw "$serviceName is $($service.Status)"
    }}
}}

foreach ($shareName in @('SYSVOL','NETLOGON')) {{
    if (-not (Get-SmbShare -Name $shareName -ErrorAction SilentlyContinue)) {{
        throw "$shareName share is missing"
    }}
}}

$generic = @(& nltest.exe '/dsgetdc:{contract['domain']}' /force 2>&1)
if ($LASTEXITCODE -ne 0) {{
    throw "DC Locator is not ready: $($generic -join ' ')"
}}

$timeserv = @(& nltest.exe '/dsgetdc:{contract['domain']}' /timeserv /force 2>&1)
if ($LASTEXITCODE -ne 0) {{
    throw "TIMESERV advertising is not ready: $($timeserv -join ' ')"
}}

{source_check}
Write-Output 'KINGDOMS_INSTALLED_AD_READY'
"""
        else:
            script = f"""
$ErrorActionPreference = 'Stop'

Resolve-DnsName '{contract['dc']}' -ErrorAction Stop | Out-Null

$secure = Test-ComputerSecureChannel -Server '{contract['dc']}' -ErrorAction Stop
if (-not $secure) {{
    throw 'machine secure channel is not healthy'
}}

$sc = @(& nltest.exe '/sc_query:{contract['domain']}' 2>&1)
if ($LASTEXITCODE -ne 0) {{
    throw "Netlogon secure session is not ready: $($sc -join ' ')"
}}

$source = (& w32tm.exe /query /source 2>$null | Out-String).Trim().TrimEnd('.')
if ($LASTEXITCODE -ne 0 -or $source -ine '{contract['dc']}') {{
    throw "W32Time source is '$source', expected {contract['dc']}"
}}

Write-Output 'KINGDOMS_INSTALLED_AD_READY'
"""

        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                result = self._lab_winrm_session(host).run_ps(script)
                if (
                    result.status_code == 0
                    and b'KINGDOMS_INSTALLED_AD_READY' in result.std_out
                ):
                    Log.success(
                        f'GOAD Kingdoms: {machine} AD dependency readiness proven'
                    )
                    return True
                last_error = (
                    result.std_err.decode(errors='replace').strip()
                    or result.std_out.decode(errors='replace').strip()
                    or f'PowerShell status {result.status_code}'
                )
            except Exception as exc:
                last_error = exc
            time.sleep(5)

        suffix = f': {last_error}' if last_error else ''
        Log.error(
            f'GOAD Kingdoms: {machine} AD dependency readiness did not converge '
            f'within {timeout}s{suffix}'
        )
        return False

    def _start_existing_instance(self, vm_name=None):
        """Power on an installed range in AD dependency order without Vagrant NAT.

        Cold starts are deliberately serialized across directory dependencies:
        KINGSLANDING must be ready before WINTERFELL, child/root DC readiness
        must be proven before members are started, and every member must regain
        its authenticated domain/time relationship before start succeeds.
        """
        if self.get_runtime_mode() not in ('exercise', 'provisioning'):
            Log.error('GOAD Kingdoms: no recorded installed mode; complete installation before using start')
            return False
        if vm_name is not None and vm_name not in self.goad_nomad_windows + ['GOAD-ROUTER']:
            Log.error(f'GOAD Kingdoms: unknown instance machine: {vm_name}')
            return False

        vmxs = {name: self._vmx_path(name) for name in self.goad_nomad_windows}
        if not all(vmxs.values()) or not self._vmx_path('GOAD-ROUTER'):
            Log.error('GOAD Kingdoms: installed VM files are missing; start will not recreate or provision guests')
            return False
        if not self._sync_goad_nomad_inventories():
            return False
        if not self._sync_goad_nomad_vagrantfile_compatibility():
            return False
        if not self._bring_up_router():
            return False

        if vm_name == 'GOAD-ROUTER':
            return True

        # Explicit dependency closure for cold starts. DC02 depends on the
        # forest-root PDC for time; NORTH members depend on DC02; SRV03 depends
        # on the ESSOS DC. A single-guest start includes the same prerequisites.
        dependencies = {
            'GOAD-DC01': (),
            'GOAD-DC02': ('GOAD-DC01',),
            'GOAD-DC03': (),
            'GOAD-SRV02': ('GOAD-DC01', 'GOAD-DC02'),
            'GOAD-SRV03': ('GOAD-DC03',),
            'GOAD-WS01': ('GOAD-DC01', 'GOAD-DC02'),
        }
        canonical_order = [
            name for name in (
                'GOAD-DC01',
                'GOAD-DC02',
                'GOAD-DC03',
                'GOAD-SRV02',
                'GOAD-WS01',
                'GOAD-SRV03',
            )
            if name in vmxs
        ]

        if vm_name is None:
            start_order = canonical_order
        else:
            required = set(dependencies.get(vm_name, ()))
            required.add(vm_name)
            start_order = [name for name in canonical_order if name in required]

        # Use the router's management NIC to establish routes before checking
        # protected-zone Windows addresses. Windows NAT settings remain untouched.
        if not self._apply_router_policy('provisioning'):
            return False
        if not self._enable_provisioning_routes():
            return False

        running = self._running_instance_vms()
        if running is None:
            return False
        running = set(running)

        # Keep one bounded budget for the complete dependency chain. Individual
        # WinRM/AD gates are capped so one guest cannot consume the whole start.
        deadline = time.monotonic() + 900

        for machine in start_order:
            vmx = vmxs[machine]
            if machine not in running:
                Log.info(
                    f'GOAD Kingdoms: powering on {machine} after its AD dependencies '
                    'are ready (no Vagrant NAT discovery)'
                )
                try:
                    result = subprocess.run(
                        ['vmrun', '-T', 'ws', 'start', vmx, 'nogui'],
                        check=False, timeout=60,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    Log.error(f'GOAD Kingdoms: local power-on failed for {machine}: {exc}')
                    return False
                if result.returncode != 0:
                    Log.error(f'GOAD Kingdoms: local power-on failed for {machine}')
                    return False
                running.add(machine)

                # VMware may re-touch host vmnet interfaces while a guest is
                # attached. Reassert the routed management plane before every
                # dependency readiness check.
                if not self._enable_provisioning_routes():
                    return False

            host = self.management_hosts[machine]
            remaining = int(deadline - time.monotonic())
            if remaining <= 0:
                Log.error('GOAD Kingdoms: installed range dependency-readiness budget exhausted')
                return False

            Log.info(f'GOAD Kingdoms: verifying {machine} directly at {host}:5986')
            if not self._wait_lab_winrm_ready(
                machine, host, timeout=min(300, remaining)
            ):
                return False

            if machine in ('GOAD-SRV02', 'GOAD-SRV03', 'GOAD-WS01'):
                if not self._ensure_installed_member_time_policy(machine, host):
                    return False

            remaining = int(deadline - time.monotonic())
            if remaining <= 0:
                Log.error('GOAD Kingdoms: installed range AD-readiness budget exhausted')
                return False

            Log.info(f'GOAD Kingdoms: waiting for {machine} AD dependency readiness')
            if not self._wait_installed_ad_ready(
                machine, host, timeout=min(300, remaining)
            ):
                return False

        # Final reassertion after the complete requested chain is attached.
        if not self._enable_provisioning_routes():
            return False

        Log.success(
            'GOAD Kingdoms: requested installed guests are ready in AD dependency '
            'order over local management; no NAT communicator used'
        )
        return True

    def _bring_up_router(self):
        """Installed ranges use local power-on and deterministic management SSH.

        A recorded mode identifies an existing managed deployment. An unknown
        or fresh deployment retains the Vagrant provisioning path. Never fall
        back to NAT after a management failure and obscure the original error.
        """
        if self.get_runtime_mode() not in ('exercise', 'provisioning'):
            return self.command.run_vagrant(['up', 'GOAD-ROUTER'], self.path)

        vmx = self._vmx_path('GOAD-ROUTER')
        if not vmx:
            Log.error('GOAD Kingdoms: installed router VMX is missing; refusing to recreate it during start')
            return False
        running = self._running_instance_vms()
        if running is None:
            return False
        try:
            if 'GOAD-ROUTER' not in running:
                result = subprocess.run(
                    ['vmrun', '-T', 'ws', 'start', vmx, 'nogui'],
                    check=False, timeout=60,
                )
                if result.returncode != 0:
                    Log.error('GOAD Kingdoms: local router power-on failed')
                    return False

            # VMware can recreate the host interfaces during power-on. Repair
            # synchronously, then validate before using the router's .1 address.
            hostaddr_service = (
                'kingdoms-north-vmnet-hostaddrs.service'
                if self.lab_name == 'NORTH'
                else 'goad-nomad-vmnet-hostaddrs.service'
            )
            repair = subprocess.run(
                ['sudo', '-n', 'systemctl', 'restart',
                 hostaddr_service],
                check=False, timeout=50,
            )
            checker = self._script('check-vmware-networks.sh')
            ssh = self._script('router-ssh.sh')
            if repair.returncode != 0 or checker is None or ssh is None:
                return False
            check_args = ['bash', checker]
            if self.lab_name == 'NORTH':
                check_args.extend(('--north', '--live'))
            if subprocess.run(check_args, check=False, timeout=30).returncode != 0:
                return False

            Log.info('GOAD Kingdoms: waiting for router management SSH at 10.4.99.1:22')
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                try:
                    ready = subprocess.run(
                        ['bash', ssh,
                         'test "$(cat /proc/sys/net/ipv4/ip_forward)" = 1 && '
                         'sudo -n systemctl is-active --quiet nftables'],
                        env=self._provider_env(), check=False, timeout=15,
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                        text=True,
                    )
                    if ready.returncode == 0:
                        Log.success('GOAD Kingdoms: router management ready without NAT discovery')
                        return True
                except subprocess.TimeoutExpired:
                    pass
                time.sleep(3)
        except (OSError, subprocess.TimeoutExpired) as exc:
            Log.error(f'GOAD Kingdoms: local router startup failed: {exc}')
            return False

        Log.error(
            'GOAD Kingdoms: router management did not become ready within 180s; '
            'check vmnet99, the router SSH service/key and nftables. '
            'No NAT fallback or router reprovisioning was attempted.'
        )
        return False

    def prepare_install(self):
        if self._course1_unwired():
            return False
        # This method is the first provider hook executed by the hardened
        # install/start/ws01 paths, before GOAD-ROUTER or any Windows guest is
        # powered on. Refuse to create a duplicate-MAC condition before VMware
        # has an opportunity to register the conflicting adapter. Require the
        # operator to prime sudo before entering the lifecycle as well.
        if not self._check_segmented_instance_conflicts():
            return False
        if not self._require_cached_sudo():
            return False
        return super().prepare_install()

    def _fresh_install_bootstrap_pending(self):
        """Return True only between fresh provider bring-up and the first playbook.

        A zero-state install has healthy Windows/WinRM endpoints before Active
        Directory exists. The normal provisioning mode transition is deliberately
        AD-aware, so using it here creates a circular dependency: it waits for
        NTDS/DC Locator before Ansible has had a chance to promote the DCs.

        The install timing profile gives us an explicit lifecycle marker for this
        narrow state. Installed/maintenance instances have a recorded runtime mode
        and continue through the normal AD-aware mode controller.
        """
        # A prior first install may have completed all five VM bring-ups yet
        # stopped at management-plane preparation (before build.yml). The
        # console can grant a one-call authorization after verifying the exact
        # failed receipt, matching provider owner, roster and live VMware VMX.
        # Never use this for established AD or normal snapshot/start paths.
        if (self.lab_name == 'NORTH'
                and getattr(self, '_north_pre_ad_resume_authorized', False) is True
                and self.get_runtime_mode() == 'unknown'):
            return True
        profile = getattr(self, '_kingdoms_install_profile', None)
        return (
            self.lab_name in ('GOAD', 'NORTH')
            and self.get_runtime_mode() == 'unknown'
            and isinstance(profile, dict)
            and profile.get('provider_success') is True
            and profile.get('status') == 'ansible_running'
        )

    def prepare_provisioning(self):
        """Prepare fresh pre-AD bootstrap without weakening installed lifecycle."""
        if self._course1_unwired():
            return False
        if not self.is_goad_nomad_segmented():
            return super().prepare_provisioning()

        if not self._fresh_install_bootstrap_pending():
            return super().prepare_provisioning()

        Log.info(
            'GOAD Kingdoms: fresh install bootstrap before AD exists; '
            'preparing routed WinRM management without AD readiness'
        )

        if not self._require_cached_sudo():
            return False
        if not self._apply_router_policy('provisioning'):
            return False
        if not self._enable_provisioning_routes():
            return False
        if not self._validate_management_plane():
            Log.error(
                'GOAD Kingdoms: fresh pre-AD management plane is not ready; '
                'refusing to start Ansible'
            )
            return False

        Log.success(
            'GOAD Kingdoms: fresh pre-AD management plane ready; '
            'Ansible may create the directory services'
        )
        return True

    def set_runtime_mode(self, mode):
        if self._course1_unwired():
            return False
        # Re-check immediately before every provisioning/exercise transition.
        # This covers long-running starts where the sudo timestamp may have
        # expired since prepare_install() and prevents the compatibility mode
        # controller from ever becoming an interactive password prompt.
        if self.is_goad_nomad_segmented() and not self._require_cached_sudo():
            return False
        return super().set_runtime_mode(mode)