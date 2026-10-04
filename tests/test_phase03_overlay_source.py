"""Offline source contract for Kingdoms Phase 03 overlay scaffolding."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "ansible" / "phase03.yml"
APPLY = ROOT / "scripts" / "apply-phase03.sh"
VALIDATE = ROOT / "scripts" / "validate-phase03-runtime.sh"
RESET = ROOT / "scripts" / "reset-phase03.sh"
DIAG = ROOT / "scripts" / "phase03" / "diagnostics"


class Phase03OverlaySourceTests(unittest.TestCase):
    def test_required_files_exist(self):
        for path in (PLAYBOOK, APPLY, VALIDATE, RESET):
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), path)

    def test_shell_entrypoints_parse(self):
        scripts = [APPLY, VALIDATE, RESET, *sorted(DIAG.glob("*.sh"))]
        for script in scripts:
            with self.subTest(script=script):
                result = subprocess.run(
                    ["bash", "-n", str(script)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_playbook_is_scoped_to_north_hosts(self):
        text = PLAYBOOK.read_text()
        self.assertIn("hosts: dc02:srv02:ws01", text)
        self.assertIn("north.sevenkingdoms.local", text)
        self.assertIn("phase03_apply", text)
        self.assertIn("any_errors_fatal: true", text)
        for forbidden in ("dc01", "dc03", "srv03", "all:"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(f"hosts: {forbidden}", text)

    def test_apply_fails_closed_and_runs_readiness_first(self):
        text = APPLY.read_text()
        self.assertIn("--confirm", text)
        self.assertIn("working tree must be clean", text)
        self.assertIn("verify-test-source.sh", text)
        self.assertNotIn("kingdoms/phase03-overlay", text)
        self.assertIn("validate-phase03-readiness.sh", text)
        self.assertIn("-e phase03_apply=true", text)
        self.assertIn("ad/GOAD/data/inventory", text)
        self.assertIn("ad/GOAD/providers/vmware/inventory", text)
        self.assertIn("--list-hosts", text)
        self.assertIn("required Phase 03 host missing", text)
        self.assertNotIn('"$PROVIDER/inventory"', text)
        self.assertLess(
            text.index("validate-phase03-readiness.sh"),
            text.index("ansible-playbook"),
        )

    def test_phase03_runtime_source_gates_do_not_pin_retired_feature_branch(self):
        scripts = [
            ROOT / "scripts" / "apply-phase03.sh",
            ROOT / "scripts" / "phase03" / "check-http-ldaps-readonly-relay.sh",
            ROOT / "scripts" / "phase03" / "check-ldap-readonly-relay.sh",
            ROOT / "scripts" / "phase03" / "check-wpad-permanent-prereqs.sh",
            ROOT / "scripts" / "phase03" / "start-smb-interactive-relay.sh",
            ROOT / "scripts" / "phase03" / "diagnostics" / "diagnose-http-ldaps-listener.sh",
        ]

        for script in scripts:
            with self.subTest(script=script):
                text = script.read_text()
                self.assertIn("verify-test-source.sh", text)
                self.assertNotIn("kingdoms/phase03-overlay", text)

    def test_final_regression_dependencies_do_not_pin_retired_feature_branches(self):
        scripts = [
            ROOT / "scripts" / "validate-phase02-readiness.sh",
            ROOT / "scripts" / "validate-rdp-runtime.sh",
            ROOT / "scripts" / "validate-network-segmentation-runtime.sh",
            ROOT / "scripts" / "validate-ws01-runtime.sh",
            ROOT / "scripts" / "phase03" / "check-rbcd-prereqs.sh",
            ROOT / "scripts" / "phase03" / "check-shadow-prereqs.sh",
            ROOT / "scripts" / "phase03" / "check-adidns-prereqs.sh",
            ROOT / "scripts" / "phase03" / "check-webdav-shortcut-prereqs.sh",
            ROOT / "scripts" / "phase03" / "verify-wpad-reset.sh",
            ROOT / "scripts" / "phase03" / "verify-http-ldaps-callback-clean.sh",
        ]

        for script in scripts:
            with self.subTest(script=script):
                text = script.read_text()
                self.assertNotIn("kingdoms/phase03-overlay", text)
                self.assertNotIn("kingdoms/rdp-access-contract", text)

    def test_reset_is_non_destructive_at_checkpoint(self):
        text = RESET.read_text().lower()
        self.assertIn("no permanent phase 03 state-changing fixture", text)
        for forbidden in (
            "remove-ad",
            "delete-ad",
            "vagrant destroy",
            "goad.sh -t destroy",
            "rm -rf",
            "git reset --hard",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_no_embedded_phase03_secrets(self):
        corpus = "\n".join(
            p.read_text(errors="replace")
            for p in [PLAYBOOK, APPLY, VALIDATE, RESET, *sorted(DIAG.glob("*.sh"))]
        ).lower()
        for forbidden in (
            "winter2022",
            "sexywolfy",
            "fightp3aceandhonor!",
            "youwillnotkerboroast1ngmeeeeee",
            "/p:rickon",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, corpus)

    def test_wpad_preflight_prepares_harmless_pac_and_managed_victim_session(self):
        script = (DIAG / "wpad-preflight.sh").read_text()
        self.assertIn('return "DIRECT";', script)
        self.assertIn("wpad.dat", script)
        self.assertIn("ensure-wpad-rickon-session.sh", script)
        self.assertIn("no WS01 network-state mutation", script)

    def test_wpad_victim_session_is_owned_and_cleaned_safely(self):
        ensure = (DIAG / "ensure-wpad-rickon-session.sh").read_text()
        cleanup = (DIAG / "cleanup-wpad-rickon-session.sh").read_text()

        self.assertIn("kingdoms-phase03-rickon.service", ensure)
        self.assertIn("check-rickon-prereqs.sh", ensure)
        self.assertIn("validate-rickon-session.sh", ensure)
        self.assertIn("ensured-by-wpad", ensure)
        self.assertIn("remains owned by this WPAD exercise", ensure)
        self.assertNotIn('rm -f -- "$MARKER"\n  bash scripts/phase03/validate-rickon-session.sh', ensure)
        self.assertIn("PHASE03_WPAD_RICKON_ENSURED_BY_EXERCISE=True", ensure)

        self.assertIn("ensured-by-wpad", cleanup)
        self.assertIn("shared permanent Rickon", cleanup)
        self.assertIn("systemctl --user start", cleanup)
        self.assertNotIn("systemctl --user stop", cleanup)
        self.assertIn("PHASE03_WPAD_RICKON_PRESERVED=True", cleanup)
        self.assertNotIn("systemctl --user disable", cleanup)

    def test_wpad_observer_fails_closed_if_pac_is_missing(self):
        script = (DIAG / "start-wpad-observers.sh").read_text()
        self.assertIn("harmless PAC file missing", script)
        self.assertIn("wpad-preflight.sh", script)

    def test_wpad_completion_always_rolls_back_after_validation(self):
        script = (ROOT / "scripts" / "phase03" / "complete-wpad-exercise.sh").read_text()
        self.assertIn("validate-wpad-chain.sh", script)
        self.assertIn("rollback-wpad-runtime.sh", script)
        self.assertIn("trap cleanup EXIT", script)
        self.assertIn("trap 'exit 130' INT", script)
        self.assertIn("trap 'exit 143' TERM", script)
        self.assertIn("automatic WPAD rollback", script)
        self.assertIn("cleanup-wpad-rickon-session.sh", script)
        self.assertIn("AUTOMATIC WPAD VICTIM-SESSION CLEANUP", script)
        self.assertIn("PHASE03_WPAD_EXERCISE_COMPLETE=True", script)
        self.assertIn("Waiting for WPAD lifecycle lock", script)
        self.assertIn("WPAD lifecycle lock acquired", script)
        self.assertIn("PHASE03_WPAD_WATCHDOG_TIMER_CANCELLED=True", script)
        self.assertIn("PHASE03_WPAD_WATCHDOG_DISARMED=True", script)
        self.assertIn('systemctl stop --no-block "$WATCHDOG_UNIT.timer"', script)
        self.assertIn('rm -f -- "$ACTIVE"', script)
        result = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts" / "phase03" / "complete-wpad-exercise.sh")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wpad_atomic_launcher_arms_fifteen_minute_watchdog_only_after_readiness(self):
        script = (ROOT / "scripts" / "phase03" / "start-wpad-exercise.sh").read_text()
        self.assertIn("check-wpad-permanent-prereqs.sh", script)
        self.assertIn("wpad-preflight.sh", script)
        self.assertIn("start-mitm6-ws01.sh", script)
        self.assertIn("start-wpad-observers.sh", script)
        self.assertIn("start-mitm6-ws01.sh 9>&-", script)
        self.assertIn("start-wpad-observers.sh 9>&-", script)
        self.assertIn("flock -u 9", script)
        self.assertIn("exec 9>&-", script)
        self.assertIn('WPAD_WATCHDOG_DELAY:-15m', script)
        self.assertIn("systemd-run", script)
        self.assertIn("--collect", script)
        self.assertIn("token_hex(16)", script)
        self.assertIn("token=$TOKEN", script)
        self.assertIn("kingdoms-phase03-wpad-watchdog", script)
        self.assertIn("PHASE03_WPAD_EXERCISE_ARMED=True", script)
        self.assertLess(script.index("start-wpad-observers.sh"), script.index("systemd-run"))
        self.assertIn("cleanup_on_error", script)

    def test_wpad_watchdog_is_privileged_scoped_and_marker_gated(self):
        script = (ROOT / "scripts" / "phase03" / "watchdog-wpad-exercise-root.sh").read_text()
        self.assertIn("flock", script)
        self.assertIn("if [[ ! -f \"$ACTIVE\" ]]", script)
        self.assertIn('grep -Fxq "token=$TOKEN" "$ACTIVE"', script)
        self.assertIn("stale WPAD watchdog generation", script)
        self.assertIn("stop-wpad-runtime.sh", script)
        self.assertIn("WPAD_SKIP_LOCAL_STOP=1", script)
        self.assertIn("runuser -u", script)
        self.assertIn("cleanup-wpad-rickon-session.sh", script)
        self.assertIn("PHASE03_WPAD_WATCHDOG_ROLLBACK_COMPLETE=True", script)
        self.assertIn('rm -f -- "$ACTIVE"', script)

    def test_wpad_transition_guard_is_applied_to_downstream_exercises(self):
        guard = (ROOT / "scripts" / "phase03" / "assert-wpad-exercise-clean.sh"
                ).read_text()
        self.assertIn("phase03-wpad-active", guard)
        self.assertIn("complete-wpad-exercise.sh", guard)

        downstream = [
            "check-http-ldaps-readonly-relay.sh",
            "start-http-ldaps-readonly-relay.sh",
            "check-ldap-readonly-relay.sh",
            "start-ldap-readonly-relay.sh",
            "check-rbcd-prereqs.sh",
            "start-rbcd-stage1-add-computer.sh",
            "check-shadow-prereqs.sh",
            "start-shadow-relay.sh",
            "check-adidns-prereqs.sh",
            "apply-adidns-proof.sh",
            "check-webdav-shortcut-prereqs.sh",
            "start-webdav-shortcut-observer.sh",
            "apply-webdav-dns-support.sh",
            "prepare-webdav-client-runtime.sh",
            "apply-webdav-shortcut-proof.sh",
            "arm-webdav-shortcut-interaction.sh",
        ]
        for name in downstream:
            with self.subTest(name=name):
                text = (ROOT / "scripts" / "phase03" / name).read_text()
                self.assertIn("assert-wpad-exercise-clean.sh", text)

    def test_wpad_rickon_readiness_waits_for_windows_session_before_arming(self):
        script = (DIAG / "ensure-wpad-rickon-session.sh").read_text()
        self.assertIn("wait_for_healthy_session", script)
        self.assertIn("seq 1 12", script)
        self.assertIn("sleep 5", script)
        self.assertIn("within 60 seconds", script)

    def test_rickon_failure_diagnostic_is_sanitized_and_auth_only(self):
        script = (DIAG / "diagnose-rickon-session.sh").read_text()
        self.assertIn("journalctl --user -u", script)
        self.assertIn("PHASE03_RICKON_AUTH_ONLY", script)
        self.assertIn("/auth-only", script)
        self.assertIn("/args-from:stdin", script)
        self.assertIn("[REDACTED]", script)
        self.assertIn("skipping parallel auth-only probe", script)
        self.assertNotIn('cat "$CREDENTIAL_FILE"\n', script)

    def test_rickon_quser_no_user_state_is_clean_negative_evidence(self):
        playbook = (ROOT / "ansible" / "phase03-validate-rickon-session.yml").read_text()
        self.assertIn("No User exists", playbook)
        self.assertIn("PHASE03_RICKON_ACTIVE=FALSE", playbook)
        self.assertIn("PHASE03_QUSER=No interactive users", playbook)

    def test_wpad_observer_handles_privileged_capture_file(self):
        script = (DIAG / "start-wpad-observers.sh").read_text()
        self.assertIn('sudo rm -f "$PCAP"', script)
        self.assertIn('-Z "$USER"', script)
        self.assertIn("kingdoms-wpad-tcpdump.log", script)

    def test_mitm6_background_launch_never_prompts_for_sudo(self):
        script = (DIAG / "start-mitm6-ws01.sh").read_text()
        self.assertIn("sudo -v", script)
        self.assertIn("sudo -n stdbuf", script)
        self.assertNotIn("sudo stdbuf", script)
        self.assertLess(script.index("sudo -v"), script.index("sudo -n stdbuf"))
        self.assertIn("sudo authentication leaked into the background mitm6 launch", script)

    def test_ws01_renew6_trigger_is_scoped_and_observable(self):
        shell = (DIAG / "trigger-ws01-renew6.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-trigger-ws01-renew6.yml").read_text()
        self.assertIn("hosts: ws01", playbook)
        self.assertIn("10.4.10.31", playbook)
        self.assertIn("ipconfig.exe /renew6", playbook)
        self.assertIn("Get-DnsClientServerAddress", playbook)
        self.assertIn("kingdoms-mitm6.log", shell)
        self.assertIn("WPAD HTTP observer log missing", shell)
        self.assertIn("WPAD packet capture is not running", shell)
        self.assertIn("WPAD_WAIT_SECONDS:-360", shell)
        self.assertIn("WPAD_POLL_SECONDS:-10", shell)
        self.assertIn("still waiting for Windows WPAD discovery", shell)
        self.assertIn("PHASE03_WPAD_AUTODISCOVERY_OBSERVED=True", shell)
        self.assertIn('dns.qry.name contains \\"wpad\\"', shell)
        self.assertIn('http.request.uri == \\"/wpad.dat\\"', shell)
        self.assertNotIn("Waiting 8 seconds", shell)
        self.assertNotIn("validate-rickon-session.sh", shell)

    def test_wpad_chain_validator_requires_same_capture_sequence(self):
        script = (ROOT / "scripts" / "phase03" / "validate-wpad-chain.sh").read_text()
        self.assertIn("DHCPv6 Solicit", script)
        self.assertIn("DHCPv6 Advertise", script)
        self.assertIn("DHCPv6 Request", script)
        self.assertIn("DHCPv6 Reply", script)
        self.assertIn("attacker-controlled IPv6 DNS", script)
        self.assertIn("GET /wpad.dat", script)
        self.assertIn("reply <= dns <= http", script)
        self.assertIn("WS01_MAC", script)
        self.assertIn("-e eth.src", script)
        self.assertIn('eth.src == $WS01_MAC', script)
        self.assertNotIn("WS01_V6", script)

    def test_wpad_cleanup_is_scoped_and_preserves_evidence(self):
        script = (DIAG / "stop-wpad-runtime.sh").read_text()
        self.assertIn("mitm6", script)
        self.assertIn("http[.]server", script)
        self.assertIn("tcpdump", script)
        self.assertIn("kill -TERM", script)
        self.assertIn("kill -KILL", script)
        self.assertNotIn('rm -f "$PCAP"', script)
        self.assertIn("dnsmasq", script)

    def test_ldap_readonly_relay_profile_is_mutation_disabled(self):
        preflight = (ROOT / "scripts" / "phase03" / "check-ldap-readonly-relay.sh").read_text()
        start = (ROOT / "scripts" / "phase03" / "start-ldap-readonly-relay.sh").read_text()
        stop = (ROOT / "scripts" / "phase03" / "stop-ldap-readonly-relay.sh").read_text()
        for option in ("--no-dump", "--no-da", "--no-acl"):
            self.assertIn(option, preflight)
            self.assertIn(option, start)
        for option in ("--no-http-server", "--no-wcf-server", "--no-raw-server"):
            self.assertIn(option, start)
        self.assertIn("-smb2support", preflight)
        self.assertIn("-smb2support", start)
        self.assertNotIn("--smb2support", preflight)
        self.assertNotIn("--smb2support", start)
        self.assertIn('ldaps://$TARGET', start)
        self.assertIn("TCP/445", preflight)
        self.assertIn("Responder is not running", preflight)
        self.assertIn("kill -TERM", stop)
        self.assertNotIn("--delegate-access", start)
        self.assertNotIn("--shadow-credentials", start)
        self.assertNotIn("--add-computer", start)

    def test_rbcd_preflight_is_read_only_and_scoped_to_ws01(self):
        wrapper = (ROOT / "scripts" / "phase03" / "check-rbcd-prereqs.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-rbcd-preflight.yml").read_text()
        self.assertIn("hosts: dc02", playbook)
        self.assertIn("Get-ADComputer -Identity 'WS01'", playbook)
        self.assertIn("msDS-AllowedToActOnBehalfOfOtherIdentity", playbook)
        self.assertIn("PHASE03_RBCD_SELF_CAN_WRITE", playbook)
        self.assertIn("PHASE03_RBCD_MAQ", playbook)
        self.assertIn("PHASE03RBCD$", playbook)
        self.assertIn("phase03-rbcd-preflight.yml", wrapper)
        for forbidden in ("Set-AD", "New-ADComputer", "Remove-ADComputer"):
            self.assertNotIn(forbidden, playbook)

    def test_rbcd_baseline_capture_preserves_exact_pre_attack_state(self):
        wrapper = (ROOT / "scripts" / "phase03" / "capture-rbcd-baseline.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-rbcd-baseline.yml").read_text()
        self.assertIn("msDS-AllowedToActOnBehalfOfOtherIdentity", playbook)
        self.assertIn("RBCDBase64", playbook)
        self.assertIn("GetSecurityDescriptorBinaryForm", playbook)
        self.assertIn("CandidateExisted", playbook)
        self.assertIn("phase03-rbcd-baseline.json", playbook)
        self.assertIn("mode: '0600'", playbook)
        self.assertIn("python3 -m json.tool", wrapper)
        for forbidden in ("Set-AD", "New-ADComputer", "Remove-ADComputer"):
            self.assertNotIn(forbidden, playbook)

    def test_headless_rdp_runtime_restore_is_guarded_and_scoped(self):
        wrapper = (ROOT / "scripts" / "restore-headless-rdp-runtime.sh").read_text()
        playbook = (ROOT / "ansible" / "restore-headless-rdp-runtime.yml").read_text()

        self.assertIn("--confirm", wrapper)
        self.assertIn("verify-test-source.sh", wrapper)
        self.assertIn("restore-headless-rdp-runtime.yml", wrapper)
        self.assertIn("sync-ws01-rdp-pin.sh", wrapper)
        self.assertIn("systemctl --user start", wrapper)
        self.assertIn("KINGDOMS_HEADLESS_RDP_RUNTIME_RESTORED=True", wrapper)

        self.assertIn("hosts: dc02", playbook)
        self.assertIn("connect_bot", playbook)
        self.assertIn("NORTH\\robb.stark", playbook)
        self.assertIn("robb.stark", playbook)
        self.assertIn("NTAccount", playbook)
        self.assertIn("SecurityIdentifier", playbook)
        self.assertIn("KINGDOMS_CONNECT_BOT_PRINCIPAL_CHECK=PASS", playbook)
        self.assertIn("Disable-ScheduledTask", playbook)
        self.assertIn("Name='mstsc.exe'", playbook)
        self.assertIn("KINGDOMS_HEADLESS_RDP_LEGACY_CLEAN=True", playbook)
        for forbidden in (
            "Remote Desktop Users",
            "SeRemoteInteractiveLogonRight",
            "Set-AD",
            "New-AD",
            "Set-NetFirewall",
        ):
            self.assertNotIn(forbidden, playbook)

        result = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts" / "restore-headless-rdp-runtime.sh")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_final_regression_forwards_instance_context_to_phase03_runtime(self):
        script = (ROOT / "scripts" / "validate-phase03-final-regression.sh").read_text()
        self.assertIn('INSTANCE="$INSTANCE"', script)
        self.assertIn('PROVIDER="$PROVIDER"', script)
        self.assertIn('GOAD_PROVIDER_DIR="$PROVIDER"', script)
        self.assertIn("bash scripts/validate-phase03-runtime.sh", script)

    def test_all_phase03_shell_scripts_parse(self):
        phase03 = ROOT / "scripts" / "phase03"
        for script in sorted(phase03.rglob("*.sh")):
            with self.subTest(script=script):
                result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_rbcd_stage1_creates_only_reserved_candidate(self):
        start = (ROOT / "scripts" / "phase03" / "start-rbcd-stage1-add-computer.sh").read_text()
        verify = (ROOT / "ansible" / "phase03-rbcd-verify-stage1.yml").read_text()
        self.assertIn("--add-computer", start)
        self.assertIn("PHASE03RBCD", start)
        self.assertIn("--no-dump", start)
        self.assertIn("--no-da", start)
        self.assertIn("--no-acl", start)
        self.assertNotIn("--delegate-access", start)
        self.assertNotIn("--shadow-credentials", start)
        self.assertIn("phase03-rbcd-baseline.json", start)
        self.assertIn("phase03-rbcd-password", start)
        self.assertIn("PHASE03_RBCD_STAGE1_CANDIDATE_EXISTS", verify)
        self.assertIn("PHASE03_RBCD_STAGE1_RBCD_PRESENT", verify)
        for forbidden in ("Set-AD", "New-ADComputer", "Remove-ADComputer"):
            self.assertNotIn(forbidden, verify)

    def test_ws01_system_http_trigger_is_temporary_and_system_scoped(self):
        shell = (DIAG / "trigger-ws01-system-http.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-trigger-ws01-system-http.yml").read_text()
        self.assertIn("hosts: ws01", playbook)
        self.assertIn("New-ScheduledTaskPrincipal -UserId 'SYSTEM'", playbook)
        self.assertIn("Invoke-WebRequest", playbook)
        self.assertIn("-UseDefaultCredentials", playbook)
        self.assertIn("10.4.10.254", playbook)
        self.assertIn("Unregister-ScheduledTask", playbook)
        self.assertIn("ntlmrelayx is not running", shell)
        self.assertIn("TCP/80", shell)

    def test_rbcd_stage2_verifier_is_read_only(self):
        wrapper = (ROOT / "scripts" / "phase03" / "verify-rbcd-stage2.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-rbcd-verify-stage2.yml").read_text()
        self.assertIn("System.DirectoryServices.ActiveDirectorySecurity", playbook)
        self.assertIn("GetSecurityDescriptorBinaryForm", playbook)
        self.assertIn("[System.Security.AccessControl.RawSecurityDescriptor]::new($binary, 0)", playbook)
        self.assertIn("PHASE03_RBCD_STAGE2_RAW_TYPE", playbook)
        self.assertNotIn("New-Object System.Security.AccessControl.RawSecurityDescriptor", playbook)
        self.assertNotIn("[byte[]]$raw, 0", playbook)
        self.assertIn("PHASE03_RBCD_STAGE2_DELEGATION_PRESENT", playbook)
        self.assertIn("PHASE03RBCD$", playbook)
        self.assertIn("phase03-rbcd-verify-stage2.yml", wrapper)
        for forbidden in ("Set-AD", "New-ADComputer", "Remove-ADComputer"):
            self.assertNotIn(forbidden, playbook)

    def test_rbcd_s4u_proof_uses_ticket_cache_and_read_only_cifs_check(self):
        script = (ROOT / "scripts" / "phase03" / "prove-rbcd-s4u.sh").read_text()
        self.assertIn("impacket-getST", script)
        self.assertIn("-impersonate", script)
        self.assertIn("cifs/$TARGET_FQDN", script)
        self.assertIn("PHASE03RBCD$", script)
        self.assertIn('KRB5CCNAME="$TGT_CACHE"', script)
        self.assertIn('KRB5CCNAME="$ST_CACHE"', script)
        self.assertIn('export KRB5CCNAME="FILE:$TGT_CACHE"', script)
        self.assertIn(r'printf "%s\n" "$PASSWORD" | "$KINIT"', script)
        self.assertNotIn("sh -c", script)
        self.assertNotIn('KRB5CCNAME="FILE:$TGT_CACHE" \\\n    "$GETST"', script)
        self.assertNotIn('export KRB5CCNAME="FILE:$ST_CACHE"', script)
        self.assertIn("kinit", script)
        self.assertIn("use C$", script)
        self.assertIn("-inputfile", script)
        self.assertNotIn("wmiexec", script)
        self.assertNotIn("psexec", script)

    def test_rbcd_rollback_restores_baseline_and_cleans_only_ephemera(self):
        script = (ROOT / "scripts" / "phase03" / "rollback-rbcd.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-rbcd-rollback.yml").read_text()
        self.assertIn("phase03-rbcd-baseline.json", script)
        self.assertIn("Phase 03 poisoning/relay runtime is still active", script)
        self.assertIn("Set-ADComputer", playbook)
        self.assertIn("Remove-ADComputer", playbook)
        self.assertIn("PHASE03_RBCD_RESET_RBCD_MATCH", playbook)
        self.assertIn("PHASE03_RBCD_RESET_CANDIDATE_MATCH", playbook)
        self.assertIn("PHASE03_RBCD_RESET_COMPLETE=True", playbook)
        self.assertIn('rm -f -- "$SECRET_FILE"', script)
        self.assertIn('rm -rf -- "$WORK"', script)
        self.assertNotIn('rm -f -- "$BASELINE"', script)
        self.assertNotIn("kdestroy", script)

    def test_phase03_status_docs_are_not_duplicated_or_corrupted(self):
        scope = (ROOT / "docs" / "kingdoms-phase03-north-scope.md").read_text()
        runtime = (ROOT / "docs" / "kingdoms-phase03-runtime-checkpoint.md").read_text()
        self.assertEqual(scope.count("# Kingdoms — Phase 03 NORTH Scope and GOAD Part 4 Parity"), 1)
        self.assertEqual(runtime.count("# Kingdoms — Phase 03 Runtime Checkpoint"), 1)
        self.assertIn("| RBCD rollback |", scope)
        self.assertIn("RBCD is therefore closed end-to-end", runtime)

    def test_interactive_smb_relay_listener_is_scoped_to_castelblack(self):
        script = (ROOT / "scripts" / "phase03" / "start-smb-interactive-relay.sh").read_text()
        self.assertIn("10.4.10.22", script)
        self.assertIn("vmnet10", script)
        self.assertIn("-smb2support", script)
        self.assertTrue(any(line.strip() == "-i" for line in script.splitlines()))
        self.assertTrue(any(line.strip() == "--keep-relaying" for line in script.splitlines()))
        self.assertIn("127.0.0.1:11000+", script)
        self.assertIn("Responder.conf", script)
        self.assertIn("Responder SMB server must be Off", script)
        self.assertIn("Responder HTTP server must be Off", script)
        self.assertIn("SMB=Off HTTP=Off", script)
        self.assertNotIn("-socks", script)

    def test_status_docs_record_interactive_smb_relay_as_proven(self):
        runtime = (ROOT / "docs" / "kingdoms-phase03-runtime-checkpoint.md").read_text()
        scope = (ROOT / "docs" / "kingdoms-phase03-north-scope.md").read_text()
        self.assertIn("Interactive SMB relay to CASTELBLACK is **PROVEN**", runtime)
        self.assertIn("NORTH\\ROBB.STARK", runtime)
        self.assertIn("NORTH\\EDDARD.STARK", runtime)
        self.assertIn("| Interactive SMB relay |", scope)
        self.assertIn("| SOCKS relay |", scope)

    def test_status_docs_record_socks_smb_relay_as_proven(self):
        runtime = (ROOT / "docs" / "kingdoms-phase03-runtime-checkpoint.md").read_text()
        scope = (ROOT / "docs" / "kingdoms-phase03-north-scope.md").read_text()
        self.assertIn("SOCKS SMB relay to CASTELBLACK is **PROVEN**", runtime)
        self.assertIn("127.0.0.1:1080", runtime)
        self.assertIn("AdminStatus FALSE", runtime)
        self.assertIn("AdminStatus TRUE", runtime)
        self.assertIn("STATUS_ACCESS_DENIED", runtime)
        self.assertIn("| SOCKS relay |", scope)
        self.assertIn("| PROVEN |", scope)
        self.assertNotIn("SOCKS relay proof.", runtime)

    def test_status_docs_record_smb_execution_consequence_as_proven(self):
        runtime = (ROOT / "docs" / "kingdoms-phase03-runtime-checkpoint.md").read_text()
        scope = (ROOT / "docs" / "kingdoms-phase03-north-scope.md").read_text()
        self.assertIn("SMB remote execution on CASTELBLACK is **PROVEN**", runtime)
        self.assertIn(r"NT AUTHORITY\SYSTEM", runtime)
        self.assertIn("rpc_s_access_denied", runtime)
        self.assertIn("RemoteRegistry", runtime)
        self.assertIn("| SMB remote execution consequence |", scope)
        self.assertIn("| SMB share authorization consequence |", scope)
        self.assertNotIn("LSASS/DPAPI/share/SMB-execution consequences.", runtime)

    def test_status_docs_record_lsass_consequence_as_proven(self):
        runtime = (ROOT / "docs" / "kingdoms-phase03-runtime-checkpoint.md").read_text()
        scope = (ROOT / "docs" / "kingdoms-phase03-north-scope.md").read_text()
        self.assertIn("LSASS credential-material access on CASTELBLACK is **PROVEN**", runtime)
        self.assertIn("89,796,074", runtime)
        self.assertIn("username_count=27", runtime)
        self.assertIn("STATUS_NO_SUCH_FILE", runtime)
        self.assertIn("MDMP", runtime)
        self.assertIn("| LSASS credential-material consequence |", scope)
        self.assertIn("| DPAPI credential-material consequence |", scope)

    def test_status_docs_record_dpapi_as_proven(self):
        runtime = (ROOT / "docs" / "kingdoms-phase03-runtime-checkpoint.md").read_text()
        scope = (ROOT / "docs" / "kingdoms-phase03-north-scope.md").read_text()
        self.assertIn("DPAPI credential-material consequence", runtime)
        self.assertIn("**PROVEN**", runtime)
        self.assertIn("| DPAPI credential-material consequence |", scope)
        self.assertNotIn("Not yet runtime-proven as a separated consequence set", scope)

    def test_shadow_credentials_helpers_exist_and_parse(self):
        phase03 = ROOT / "scripts" / "phase03"
        required = [
            phase03 / "check-shadow-prereqs.sh",
            phase03 / "capture-shadow-baseline.sh",
            phase03 / "start-shadow-relay.sh",
            phase03 / "verify-shadow-mutation.sh",
            phase03 / "prove-shadow-pkinit.sh",
            phase03 / "rollback-shadow.sh",
            ROOT / "ansible" / "phase03-shadow-preflight.yml",
            ROOT / "ansible" / "phase03-shadow-baseline.yml",
            ROOT / "ansible" / "phase03-shadow-verify.yml",
            ROOT / "ansible" / "phase03-shadow-rollback.yml",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertTrue(item.is_file(), item)
        for script in required[:6]:
            with self.subTest(script=script):
                result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_shadow_verification_is_read_only_and_rollback_is_baseline_driven(self):
        verify = (ROOT / "ansible" / "phase03-shadow-verify.yml").read_text()
        rollback = (ROOT / "ansible" / "phase03-shadow-rollback.yml").read_text()
        wrapper = (ROOT / "scripts" / "phase03" / "rollback-shadow.sh").read_text()
        self.assertIn("PHASE03_SHADOW_VERIFY_KCL_COUNT", verify)
        self.assertNotIn("Set-ADComputer", verify)
        self.assertIn("phase03-shadow-baseline.json", wrapper)
        self.assertIn("PHASE03_SHADOW_RESET_KCL_MATCH", rollback)
        self.assertIn("PHASE03_SHADOW_RESET_COMPLETE=True", rollback)

    def test_shadow_pkinit_proof_is_ephemeral(self):
        script = (ROOT / "scripts" / "phase03" / "prove-shadow-pkinit.sh").read_text()
        self.assertIn("-no-hash", script)
        self.assertIn("-no-save", script)
        self.assertIn("PHASE03_SHADOW_PKINIT_TGT=True", script)

    def test_status_docs_record_shadow_credentials_as_proven(self):
        runtime = (ROOT / "docs" / "kingdoms-phase03-runtime-checkpoint.md").read_text()
        scope = (ROOT / "docs" / "kingdoms-phase03-north-scope.md").read_text()
        self.assertIn("Shadow Credentials against `WS01$` is **PROVEN**", runtime)
        self.assertIn("PHASE03_SHADOW_PKINIT_TGT=True", runtime)
        self.assertIn("KCL_MATCH=True", runtime)
        self.assertIn("| Shadow Credentials |", scope)
        self.assertNotIn("| Shadow Credentials | Not yet configured/proven | GAP |", scope)

    def test_adidns_preflight_is_read_only_and_scoped_to_north(self):
        wrapper = (ROOT / "scripts" / "phase03" / "check-adidns-prereqs.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-adidns-preflight.yml").read_text()
        self.assertIn("hosts: dc02", playbook)
        self.assertIn("Get-DnsServerZone", playbook)
        self.assertIn("north.sevenkingdoms.local", playbook)
        self.assertIn("PHASE03_ADIDNS_ZONE_DYNAMIC_UPDATE", playbook)
        self.assertIn("PHASE03_ADIDNS_BROAD_CREATE_DNSNODE", playbook)
        self.assertIn("lDAPDisplayName=dnsNode", playbook)
        self.assertIn("phase03-adidns", playbook)
        self.assertIn("wpad", playbook)
        for forbidden in (
            "Add-DnsServerResourceRecord",
            "Remove-DnsServerResourceRecord",
            "Set-DnsServer",
            "Set-ADObject",
            "New-ADObject",
            "Remove-ADObject",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, playbook)
        self.assertIn("ADIDNS preflight requires neutral state", wrapper)

    def test_adidns_preflight_checks_operator_tooling_without_mutation(self):
        wrapper = (ROOT / "scripts" / "phase03" / "check-adidns-prereqs.sh").read_text()
        self.assertIn("dig", wrapper)
        self.assertIn("bloodyAD", wrapper)
        self.assertIn("adidnsdump", wrapper)
        self.assertIn("dnstool.py", wrapper)
        self.assertIn("nsupdate", wrapper)
        self.assertIn("ldapsearch", wrapper)
        self.assertIn("phase03-adidns", wrapper)

    def test_adidns_rollback_uses_original_owner_context(self):
        script = (ROOT / "scripts" / "phase03" / "rollback-adidns.sh").read_text()
        self.assertIn("KRB5CCNAME", script)
        self.assertIn("adidns.ccache", script)
        self.assertIn("ldapdelete", script)
        self.assertIn("phase03-adidns", script)
        self.assertIn("PHASE03_ADIDNS_ROLLBACK_COMPLETE=True", script)

    def test_adidns_rollback_playbook_is_read_only_verification(self):
        playbook = (ROOT / "ansible" / "phase03-adidns-rollback.yml").read_text()
        self.assertIn("PHASE03_ADIDNS_RESET_COMPLETE=True", playbook)
        self.assertIn("PHASE03_ADIDNS_RESET_RECORD_MATCH", playbook)
        self.assertIn("PHASE03_ADIDNS_RESET_NODE_MATCH", playbook)
        for forbidden in ("Remove-ADObject", "Remove-DnsServerResourceRecord", "Set-ADObject", "New-ADObject"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, playbook)

    def test_adidns_owner_rollback_accepts_base_search_success_without_full_dn_match(self):
        script = (ROOT / "scripts" / "phase03" / "rollback-adidns.sh").read_text()
        self.assertIn('if [[ "$LDAP_RC" -eq 0 ]]; then', script)
        self.assertNotIn('grep -Fq "dn: $NODE_DN"', script)
        self.assertIn("ldapdelete -Y GSSAPI -Q", script)

    def test_status_docs_record_adidns_as_proven_and_helpers_are_complete(self):
        runtime = (ROOT / "docs" / "kingdoms-phase03-runtime-checkpoint.md").read_text()
        scope = (ROOT / "docs" / "kingdoms-phase03-north-scope.md").read_text()
        phase03 = ROOT / "scripts" / "phase03"
        self.assertIn("ADIDNS end-to-end proof", runtime)
        self.assertIn("ADIDNS is therefore closed end-to-end", runtime)
        self.assertIn("owner-context Kerberos/GSSAPI LDAP cleanup", runtime)
        self.assertIn("| ADIDNS |", scope)
        self.assertNotIn("| ADIDNS | Generic capability exists, no Phase 03 fixture yet | GAP |", scope)
        for name in (
            "check-adidns-prereqs.sh",
            "capture-adidns-baseline.sh",
            "apply-adidns-proof.sh",
            "verify-adidns-proof.sh",
            "rollback-adidns.sh",
        ):
            with self.subTest(name=name):
                self.assertTrue((phase03 / name).is_file(), name)

    def test_webdav_shortcut_preflight_is_read_only(self):
        wrapper = (ROOT / "scripts" / "phase03" / "check-webdav-shortcut-prereqs.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-webdav-shortcut-preflight.yml").read_text()
        self.assertIn("hosts: ws01", playbook)
        self.assertIn("WebClient", playbook)
        self.assertIn("MRxDAV", playbook)
        self.assertIn("phase03-webdav.lnk", playbook)
        self.assertIn("phase03-webdav.url", playbook)
        self.assertIn("NORTH\\rickon.stark", playbook)
        self.assertIn("PHASE03_WEBDAV_RICKON_EXPLORER", playbook)
        self.assertIn("WebDAV preflight requires neutral state", wrapper)
        for forbidden in ("Set-Service", "Start-Service", "Stop-Service", "New-Item", "Set-ItemProperty", "Remove-Item"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, playbook)

    def test_webdav_shortcut_preflight_checks_listener_and_tool_state(self):
        wrapper = (ROOT / "scripts" / "phase03" / "check-webdav-shortcut-prereqs.sh").read_text()
        self.assertIn("TCP/$port is free", wrapper)
        self.assertIn("responder", wrapper)
        self.assertIn("impacket-ntlmrelayx", wrapper)
        self.assertIn("tcpdump", wrapper)
        self.assertIn("10.4.10.31", wrapper)

    def test_webdav_shortcut_baseline_is_exact_and_read_only(self):
        wrapper = (ROOT / "scripts" / "phase03" / "capture-webdav-shortcut-baseline.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-webdav-shortcut-baseline.yml").read_text()
        self.assertIn("phase03-webdav-baseline.json", playbook)
        self.assertIn("mode: '0600'", playbook)
        self.assertIn("CandidateLnkExists", playbook)
        self.assertIn("CandidateUrlExists", playbook)
        self.assertIn("WebClientState", playbook)
        self.assertIn("WebClientStartMode", playbook)
        self.assertIn("MRxDAVState", playbook)
        self.assertIn("PHASE03_WEBDAV_BASELINE_VALID=True", wrapper)
        for forbidden in ("Set-Service", "Start-Service", "Stop-Service", "New-Item", "Remove-Item", "Set-ItemProperty"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, playbook)

    def test_webdav_shortcut_fixture_files_exist_and_parse(self):
        phase03 = ROOT / "scripts" / "phase03"
        required = [
            phase03 / "start-webdav-shortcut-observer.sh",
            phase03 / "apply-webdav-shortcut-proof.sh",
            phase03 / "verify-webdav-shortcut-proof.sh",
            phase03 / "rollback-webdav-shortcut.sh",
            ROOT / "ansible" / "phase03-webdav-shortcut-apply.yml",
            ROOT / "ansible" / "phase03-webdav-shortcut-verify.yml",
            ROOT / "ansible" / "phase03-webdav-shortcut-rollback.yml",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertTrue(item.is_file(), item)
        for script in required[:4]:
            result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_webdav_shortcut_rollback_uses_captured_baseline(self):
        script = (ROOT / "scripts" / "phase03" / "rollback-webdav-shortcut.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-webdav-shortcut-rollback.yml").read_text()
        self.assertIn("phase03-webdav-baseline.json", script)
        self.assertIn("PHASE03_WEBDAV_RESET_COMPLETE=True", playbook)
        self.assertIn("PHASE03_WEBDAV_ROLLBACK_COMPLETE=True", script)

    def test_webdav_rickon_refresh_helper_targets_existing_headless_session(self):
        script = (ROOT / "scripts" / "phase03" / "diagnostics" / "refresh-rickon-desktop.sh").read_text()
        self.assertIn("10.4.10.31", script)
        self.assertIn("xdotool", script)
        self.assertIn("Super_L+d", script)
        self.assertIn("F5", script)
        self.assertIn("PHASE03_WEBDAV_RICKON_DESKTOP_REFRESH=True", script)

    def test_webdav_explicit_interaction_helpers_exist_and_parse(self):
        required = [
            ROOT / "scripts" / "phase03" / "arm-webdav-shortcut-interaction.sh",
            ROOT / "scripts" / "phase03" / "diagnostics" / "trigger-rickon-webdav-shortcut.sh",
            ROOT / "ansible" / "phase03-webdav-shortcut-arm.yml",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertTrue(item.is_file(), item)
        for script in required[:2]:
            result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_webdav_arm_normalizes_optional_icon_index(self):
        playbook = (ROOT / "ansible" / "phase03-webdav-shortcut-arm.yml").read_text()
        self.assertIn("PHASE03_WEBDAV_ARM_PREVIOUS_ICON_NORMALIZED", playbook)
        self.assertIn(r"-replace ',\s*\d+\s*$',''", playbook)
        self.assertIn("PHASE03_WEBDAV_SHORTCUT_ARMED=True", playbook)
        self.assertEqual(playbook.count("register: webdav_arm"), 1)
        self.assertEqual(playbook.count("PHASE03_WEBDAV_SHORTCUT_ARMED=True"), 1)

    def test_webdav_hostname_dns_support_fixture_exists_and_parses(self):
        required = [
            ROOT / "ansible" / "phase03-webdav-dns-baseline.yml",
            ROOT / "ansible" / "phase03-webdav-dns-verify.yml",
            ROOT / "scripts" / "phase03" / "capture-webdav-dns-baseline.sh",
            ROOT / "scripts" / "phase03" / "apply-webdav-dns-support.sh",
            ROOT / "scripts" / "phase03" / "rollback-webdav-dns-support.sh",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertTrue(item.is_file(), item)
        for script in required[2:]:
            result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_webdav_explicit_interaction_uses_hostname_not_ip_literal(self):
        playbook = (ROOT / "ansible" / "phase03-webdav-shortcut-arm.yml").read_text()
        self.assertIn("phase03-webdav.north.sevenkingdoms.local@80", playbook)
        self.assertNotIn("$webdavPath = '\\\\10.4.10.254@80", playbook)

    def test_webdav_client_runtime_support_preserves_startup_mode(self):
        wrapper = (ROOT / "scripts" / "phase03" / "prepare-webdav-client-runtime.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-webdav-client-runtime.yml").read_text()
        self.assertIn("PHASE03_WEBDAV_RUNTIME_READY=True", playbook)
        self.assertIn("WebClientStartMode", playbook)
        self.assertIn("Start-Service -Name WebClient", playbook)
        self.assertNotIn("Set-Service -Name WebClient", playbook)
        result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "phase03" / "prepare-webdav-client-runtime.sh")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_webdav_verifier_normalizes_icon_and_checks_hostname_target(self):
        playbook = (ROOT / "ansible" / "phase03-webdav-shortcut-verify.yml").read_text()
        self.assertIn("PHASE03_WEBDAV_VERIFY_ICON_NORMALIZED", playbook)
        self.assertIn("PHASE03_WEBDAV_VERIFY_TARGET_MATCH", playbook)
        self.assertIn("PHASE03_WEBDAV_VERIFY_ARGUMENTS_MATCH", playbook)
        self.assertIn("phase03-webdav.north.sevenkingdoms.local@80", playbook)
        self.assertIn(r"-replace ',\s*\d+\s*$',''", playbook)

    def test_webdav_dns_support_rollback_is_idempotent(self):
        script = (ROOT / "scripts" / "phase03" / "rollback-webdav-dns-support.sh").read_text()
        verifier = (ROOT / "ansible" / "phase03-webdav-dns-reset-verify.yml").read_text()
        self.assertIn("PHASE03_WEBDAV_DNS_SUPPORT_ALREADY_CLEAN=True", script)
        self.assertIn("PHASE03_WEBDAV_DNS_RESET_COMPLETE=True", verifier)
        self.assertIn("phase03-webdav-dns-baseline.json", verifier)

    def test_status_docs_record_webdav_shortcut_as_proven(self):
        runtime = (ROOT / "docs" / "kingdoms-phase03-runtime-checkpoint.md").read_text()
        scope = (ROOT / "docs" / "kingdoms-phase03-north-scope.md").read_text()
        self.assertIn("WebDAV / .lnk victim-interaction proof", runtime)
        self.assertIn("WebDAV/.lnk is therefore closed end-to-end", runtime)
        self.assertIn("OPTIONS /kingdoms.ico", runtime)
        self.assertIn("| WebDAV/.lnk |", scope)
        self.assertNotIn("| WebDAV/.lnk/.url | No dedicated WS01 Phase 03 victim flow yet | GAP |", scope)

    def test_wpad_permanent_preflight_is_neutral_and_captures_baseline(self):
        wrapper = (ROOT / "scripts" / "phase03" / "check-wpad-permanent-prereqs.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-wpad-baseline.yml").read_text()
        self.assertIn("phase03-wpad-baseline.json", playbook)
        self.assertIn("mode: '0600'", playbook)
        self.assertIn("IPv6DnsServers", playbook)
        self.assertIn("IPv6Addresses", playbook)
        self.assertIn("neutral Phase 03 runtime", wrapper)
        self.assertIn("WINTERFELL TCP/636 reachable", wrapper)
        self.assertIn("PHASE03_WPAD_BASELINE_VALID=True", wrapper)
        for forbidden in ("Start-Service", "Stop-Service", "Set-DnsClientServerAddress", "ipconfig.exe /renew6"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, playbook)

    def test_wpad_permanent_preflight_checks_expected_tooling(self):
        wrapper = (ROOT / "scripts" / "phase03" / "check-wpad-permanent-prereqs.sh").read_text()
        for tool in ("mitm6", "impacket-ntlmrelayx", "tcpdump", "tshark", "nc"):
            with self.subTest(tool=tool):
                self.assertIn(tool, wrapper)

    def test_wpad_deterministic_rollback_is_scoped_and_reboot_free(self):
        wrapper = ROOT / "scripts" / "phase03" / "rollback-wpad-runtime.sh"
        playbook = ROOT / "ansible" / "phase03-wpad-rollback.yml"

        self.assertTrue(wrapper.is_file(), wrapper)
        self.assertTrue(playbook.is_file(), playbook)

        shell = wrapper.read_text()
        yml = playbook.read_text()

        self.assertIn("stop-wpad-runtime.sh", shell)
        self.assertIn("verify-wpad-reset.sh", shell)
        self.assertLess(
            shell.index("===== STOP TEMPORARY MITM6 / WPAD RUNTIME ====="),
            shell.index("===== RESTORE WS01 IPV6 / DNS STATE ====="),
        )
        self.assertLess(
            shell.index("===== RESTORE WS01 IPV6 / DNS STATE ====="),
            shell.index("===== VERIFY EXACT CAPTURED BASELINE ====="),
        )
        self.assertIn("mitm6 is still active", shell)
        self.assertIn("PHASE03_WPAD_DETERMINISTIC_ROLLBACK_COMPLETE=True", shell)

        self.assertIn("hosts: ws01", yml)
        self.assertIn("phase03-wpad-baseline.json", yml)
        self.assertIn("ipconfig.exe /release6", yml)
        self.assertIn("PrefixOrigin", yml)
        self.assertIn("SuffixOrigin", yml)
        self.assertIn("Remove-NetIPAddress", yml)
        self.assertIn("netsh.exe interface ipv6 set dnsservers", yml)
        self.assertIn("source=dhcp", yml)
        self.assertIn("Clear-DnsClientCache", yml)
        self.assertIn("PHASE03_WPAD_ROLLBACK_COMPLETE=True", yml)
        self.assertIn("Refusing automatic rollback", yml)

        for forbidden in (
            "Restart-Computer",
            "shutdown.exe",
            "Disable-NetAdapter",
            "Enable-NetAdapter",
            "Restart-NetAdapter",
            "Set-DnsClientServerAddress",
            "AddressFamily IPv4",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, yml)

        result = subprocess.run(
            ["bash", "-n", str(wrapper)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wpad_runtime_capability_snapshot_is_read_only(self):
        script = (ROOT / "scripts" / "phase03" / "check-wpad-runtime-capabilities.sh").read_text()
        self.assertIn("PHASE03_WPAD_CAPABILITY_SNAPSHOT_COMPLETE=True", script)
        self.assertIn("mitm6 supports", script)
        self.assertIn("NTLMRELAYX WPAD / HTTP / LDAPS OPTIONS", script)
        self.assertNotIn("start ", script.lower())
        result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "phase03" / "check-wpad-runtime-capabilities.sh")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wpad_reset_verifier_compares_exact_captured_state(self):
        wrapper = (ROOT / "scripts" / "phase03" / "verify-wpad-reset.sh").read_text()
        playbook = (ROOT / "ansible" / "phase03-wpad-reset-verify.yml").read_text()
        self.assertIn("PHASE03_WPAD_RESET_IPV6_MATCH", playbook)
        self.assertIn("PHASE03_WPAD_RESET_DNSV6_MATCH", playbook)
        self.assertIn("PHASE03_WPAD_RESET_COMPLETE=True", playbook)
        self.assertIn("mitm6 is still active", wrapper)
        result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "phase03" / "verify-wpad-reset.sh")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_http_ldaps_readonly_fixture_exists_and_parses(self):
        phase03 = ROOT / "scripts" / "phase03"
        required = [
            phase03 / "check-http-ldaps-readonly-relay.sh",
            phase03 / "start-http-ldaps-readonly-relay.sh",
            phase03 / "trigger-http-ldaps-readonly-relay.sh",
            phase03 / "prove-http-ldaps-readonly-relay.sh",
            phase03 / "stop-http-ldaps-readonly-relay.sh",
            phase03 / "verify-http-ldaps-callback-clean.sh",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertTrue(item.is_file(), item)
                result = subprocess.run(["bash", "-n", str(item)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_http_ldaps_runtime_is_mutation_disabled_and_http_only(self):
        script = (ROOT / "scripts" / "phase03" / "start-http-ldaps-readonly-relay.sh").read_text()
        self.assertIn("ldaps://$TARGET", script)
        for option in ("--no-dump", "--no-da", "--no-acl", "--no-smb-server", "--no-wcf-server", "--no-raw-server"):
            with self.subTest(option=option):
                self.assertIn(option, script)
        self.assertNotIn("--no-http-server", script)
        self.assertIn("PHASE03_HTTP_LDAPS_RUNTIME_READY=True", script)

    def test_http_ldaps_proof_requires_ws01_and_readonly_enumeration(self):
        script = (ROOT / "scripts" / "phase03" / "prove-http-ldaps-readonly-relay.sh").read_text()
        self.assertIn("NORTH\\WS01$", script)
        self.assertIn("READONLY_ENUMERATION=True", script)
        self.assertIn("PHASE03_HTTP_LDAPS_PROVEN=True", script)
        self.assertIn("mutation-like ntlmrelayx output detected", script)

    def test_http_ldaps_callback_cleanup_is_read_only(self):
        playbook = (ROOT / "ansible" / "phase03-http-ldaps-callback-clean.yml").read_text()
        self.assertIn("PHASE03_HTTP_LDAPS_CALLBACK_TASK_EXISTS", playbook)
        self.assertIn("PHASE03_HTTP_LDAPS_CALLBACK_CLEAN=True", playbook)
        for forbidden in ("Register-ScheduledTask", "Unregister-ScheduledTask", "Start-ScheduledTask"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, playbook)

    def test_http_ldaps_runtime_tracks_real_listener_pid(self):
        start = (ROOT / "scripts" / "phase03" / "start-http-ldaps-readonly-relay.sh").read_text()
        stop = (ROOT / "scripts" / "phase03" / "stop-http-ldaps-readonly-relay.sh").read_text()
        self.assertIn("listener_pid_80", start)
        self.assertIn("pid_cmdline", start)
        self.assertIn("ntlmrelayx process owning TCP/80", start)
        self.assertIn("PHASE03_HTTP_LDAPS_RUNTIME_READY=True", start)
        self.assertIn("recovered orphaned ntlmrelayx TCP/80 listener", stop)
        self.assertIn("refusing to kill PID", stop)
        for script in (
            ROOT / "scripts" / "phase03" / "start-http-ldaps-readonly-relay.sh",
            ROOT / "scripts" / "phase03" / "stop-http-ldaps-readonly-relay.sh",
        ):
            result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_http_ldaps_start_is_detached_and_trigger_recovers_listener(self):
        start = (ROOT / "scripts" / "phase03" / "start-http-ldaps-readonly-relay.sh").read_text()
        trigger = (ROOT / "scripts" / "phase03" / "trigger-http-ldaps-readonly-relay.sh").read_text()
        self.assertIn('setsid -f "$RUNTIME" "$FIFO"', start)
        self.assertNotIn("nohup stdbuf", start)
        self.assertIn("</dev/null", start)
        self.assertIn("listener did not survive detached startup", start)
        self.assertIn("listener_pid_80", trigger)
        self.assertIn("recovered live ntlmrelayx listener", trigger)
        self.assertIn("PASS: HTTP relay runtime is active", trigger)
        for script in (
            ROOT / "scripts" / "phase03" / "start-http-ldaps-readonly-relay.sh",
            ROOT / "scripts" / "phase03" / "trigger-http-ldaps-readonly-relay.sh",
        ):
            result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_http_ldaps_listener_diagnostic_is_scoped_and_non_triggering(self):
        script = (DIAG / "diagnose-http-ldaps-listener.sh").read_text()
        self.assertIn("setsid -f stdbuf", script)
        self.assertIn("ss -H -lntp 'sport = :80'", script)
        self.assertIn("ps -eo pid,ppid,sid,pgid,user,stat,etime,args --forest", script)
        self.assertIn("pgrep -af 'ntlmrelayx|python'", script)
        self.assertIn("/proc/$pid/cmdline", script)
        self.assertIn("SURVIVAL WINDOW", script)
        self.assertIn("kill -TERM", script)
        self.assertIn("CLEANUP REFUSED", script)
        self.assertIn("PHASE03_HTTP_LDAPS_LISTENER_DIAGNOSTIC_COMPLETE=True", script)
        self.assertNotIn("phase03-trigger-ws01-system-http", script)
        self.assertNotIn("ansible-playbook", script)
        self.assertNotIn("--delegate-access", script)
        self.assertNotIn("--shadow-credentials", script)
        self.assertNotIn("--add-computer", script)

    def test_http_ldaps_detached_stdin_is_kept_open(self):
        helper = (
            ROOT / "scripts" / "phase03" / "run-with-open-stdin.sh"
        ).read_text()
        start = (
            ROOT / "scripts" / "phase03"
            / "start-http-ldaps-readonly-relay.sh"
        ).read_text()

        self.assertIn("mkfifo -m 600", helper)
        self.assertIn('exec 3<>"$FIFO"', helper)
        self.assertIn('exec "$@" <&3', helper)
        self.assertIn("run-with-open-stdin.sh", start)
        self.assertIn('"$FIFO"', start)
        self.assertIn('setsid -f "$RUNTIME" "$FIFO"', start)

        result = subprocess.run(
            [
                "bash",
                "-n",
                str(
                    ROOT / "scripts" / "phase03"
                    / "run-with-open-stdin.sh"
                ),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_http_ldaps_detach_preserves_operator_owned_evidence(self):
        start = (ROOT / "scripts" / "phase03" / "start-http-ldaps-readonly-relay.sh").read_text()
        preflight = (ROOT / "scripts" / "phase03" / "check-http-ldaps-readonly-relay.sh").read_text()
        proof = (ROOT / "scripts" / "phase03" / "prove-http-ldaps-readonly-relay.sh").read_text()
        self.assertIn("setsid -f", start)
        self.assertIn(': >"$LOG"', start)
        self.assertIn("LOG_OWNER=", start)
        self.assertIn("LOG_MODE=", start)
        self.assertIn("relay log exists but is not readable", proof)
        self.assertIn("setsid not found", preflight)
        for script in (
            ROOT / "scripts" / "phase03" / "start-http-ldaps-readonly-relay.sh",
            ROOT / "scripts" / "phase03" / "check-http-ldaps-readonly-relay.sh",
            ROOT / "scripts" / "phase03" / "prove-http-ldaps-readonly-relay.sh",
        ):
            result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_status_docs_close_wpad_and_http_ldaps_permanentization(self):
        runtime = (ROOT / "docs" / "kingdoms-phase03-runtime-checkpoint.md").read_text()
        scope = (ROOT / "docs" / "kingdoms-phase03-north-scope.md").read_text()

        self.assertIn("mitm6/WPAD permanentization is therefore closed", runtime)
        self.assertIn("PHASE03_WPAD_RESET_COMPLETE=True", runtime)
        self.assertIn("HTTP -> LDAPS permanentization is therefore closed", runtime)
        self.assertIn("PHASE03_HTTP_LDAPS_PROVEN=True", runtime)
        self.assertIn("PHASE03_HTTP_LDAPS_CALLBACK_CLEAN=True", runtime)
        self.assertIn("Phase 03 infrastructure/configuration acceptance is **COMPLETE**", runtime)
        self.assertIn("PHASE03_FINAL_REGRESSION_COMPLETE=True", runtime)
        self.assertIn("RDP_RELEASE_ACCEPTANCE_COMPLETE=True", runtime)
        self.assertIn("PROVEN / PERMANENTIZED", scope)
        self.assertIn("Status: COMPLETE / runtime-validated / frozen for integration", scope)
        self.assertIn("Final Phase 03 orchestrator: **11 PASS / 0 FAIL**", scope)
        self.assertIn("RDP fresh desktop-logon release matrix: **15/15 PASS**", scope)
        self.assertNotIn(
            "Promote proven mitm6/WPAD and HTTP->LDAPS flows",
            runtime,
        )
        self.assertNotIn(
            "Promote the already-proven mitm6/WPAD and HTTP->LDAPS flows",
            scope,
        )

    def test_phase03_arp_cache_is_ignored_as_runtime_artifact(self):
        gitignore = (ROOT / ".gitignore").read_text().splitlines()
        self.assertIn("/arp.cache", gitignore)

    def test_segmentation_runtime_supports_explicit_rdp_bot_mode(self):
        segmentation = (
            ROOT / "scripts" / "validate-network-segmentation-runtime.sh"
        ).read_text()
        final = (
            ROOT / "scripts" / "validate-phase03-final-regression.sh"
        ).read_text()

        self.assertIn(
            'RDP_BOT_MODE="${KINGDOMS_RDP_BOT_MODE:-legacy}"',
            segmentation,
        )
        self.assertIn(
            '--bot-mode "${RDP_BOT_MODE}"',
            segmentation,
        )
        self.assertIn("foreach ($name in 'ntlm_bot','responder_bot')", segmentation)
        self.assertNotIn(
            "foreach ($name in 'connect_bot','ntlm_bot','responder_bot')",
            segmentation,
        )
        self.assertIn("KINGDOMS_RDP_BOT_MODE=headless", final)

    def test_segmentation_bot_health_waits_for_running_tasks_and_keeps_evidence(self):
        segmentation = (
            ROOT / "scripts" / "validate-network-segmentation-runtime.sh"
        ).read_text()

        self.assertIn("SCHED_S_TASK_RUNNING", segmentation)
        self.assertIn("BOT_SAMPLE|NAME=", segmentation)
        self.assertIn("if ($state -eq 'Running')", segmentation)
        self.assertIn("Start-Sleep -Seconds 2", segmentation)
        self.assertIn("$name=PASS|STATE=Ready|LAST=0", segmentation)
        self.assertIn("REASON=completed-result", segmentation)
        self.assertIn('tee "${LOG_DIR}/bots.log"', segmentation)
        self.assertIn("inspect ${LOG_DIR}/bots.log", segmentation)

    def test_phase03_validators_do_not_default_to_historical_instances(self):
        scripts = [
            ROOT / "scripts" / "apply-phase03.sh",
            ROOT / "scripts" / "validate-phase02-readiness.sh",
            ROOT / "scripts" / "validate-phase03-readiness.sh",
            ROOT / "scripts" / "validate-phase03-final-regression.sh",
        ]
        for script in scripts:
            with self.subTest(script=script):
                text = script.read_text()
                self.assertNotIn("cebee3-goad-vmware", text)
                self.assertNotIn("6ebce2-goad-vmware", text)
                self.assertIn("GOAD_PROVIDER_DIR", text)

    def test_phase03_final_regression_orchestrates_closed_contracts(self):
        script = (ROOT / "scripts" / "validate-phase03-final-regression.sh").read_text()

        self.assertIn("PHASE03_EXPECTED_BRANCH", script)
        self.assertIn("verify-test-source.sh", script)
        self.assertIn("git branch --show-current", script)
        self.assertIn("git rev-parse --abbrev-ref --symbolic-full-name '@{u}'", script)
        self.assertNotIn("BRANCH='kingdoms/phase03-overlay'", script)
        self.assertIn("validate-phase03-runtime.sh", script)
        self.assertIn("check-rbcd-prereqs.sh", script)
        self.assertIn("check-shadow-prereqs.sh", script)
        self.assertIn("check-adidns-prereqs.sh", script)
        self.assertIn("check-webdav-shortcut-prereqs.sh", script)
        self.assertIn("verify-wpad-reset.sh", script)
        self.assertIn("verify-http-ldaps-callback-clean.sh", script)
        self.assertIn("validate-phase02-readiness.sh", script)
        self.assertIn("PHASE02_RDP_BOT_MODE=headless", script)
        self.assertIn("validate-rdp-runtime.sh --phase01 --bot-mode headless", script)
        self.assertIn("validate-network-segmentation-runtime.sh", script)
        self.assertIn("validate-ws01-runtime.sh", script)
        self.assertIn("validate-rickon-session.sh", script)
        self.assertIn("Waiting for the supervised Rickon session", script)
        self.assertIn("240-second lifecycle window", script)
        self.assertIn("PHASE03_FINAL_REGRESSION_COMPLETE=True", script)
        self.assertNotIn("validate-kingdoms-release-acceptance.sh", script)

        result = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts" / "validate-phase03-final-regression.sh")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_checkpoint_does_not_modify_lab_yet(self):
        text = PLAYBOOK.read_text().lower()
        self.assertNotIn("win_regedit", text)
        self.assertNotIn("win_feature", text)
        self.assertNotIn("win_service", text)
        self.assertNotIn("win_file", text)
        self.assertNotIn("win_copy", text)
        self.assertNotIn("set-acl", text)
        self.assertNotIn("set-ad", text)


if __name__ == "__main__":
    unittest.main()