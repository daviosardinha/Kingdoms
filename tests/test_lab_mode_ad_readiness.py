"""Regression contract for AD-aware Kingdoms mode transitions."""

from pathlib import Path
import os
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAB_MODE = ROOT / "scripts" / "lab-mode.sh"


class LabModeAdReadinessTests(unittest.TestCase):
    def setUp(self):
        self.text = LAB_MODE.read_text(encoding="utf-8")

    def test_provisioning_restarts_dcs_before_members_and_waits_for_identity(self):
        text = self.text

        self.assertIn("configure_windows_nat_provisioning()", text)
        self.assertIn('for vm in "${DOMAIN_CONTROLLERS[@]}"', text)
        self.assertIn('wait_domain_controller_ready "${vm}"', text)
        self.assertIn('for vm in "${DOMAIN_MEMBERS[@]}"', text)
        self.assertIn('wait_domain_member_ready "${vm}"', text)

        fn = text[text.index("configure_windows_nat_provisioning()"):
                  text.index("configure_windows_nat_exercise()")]
        self.assertLess(
            fn.index('for vm in "${DOMAIN_CONTROLLERS[@]}"'),
            fn.index('for vm in "${DOMAIN_MEMBERS[@]}"'),
        )

    def test_exercise_restarts_members_before_domain_controllers(self):
        text = self.text
        fn = text[text.index("configure_windows_nat_exercise()"):
                  text.index("verify_persistent_state()")]

        self.assertLess(
            fn.index('for vm in "${DOMAIN_MEMBERS[@]}"'),
            fn.index('for vm in "${EXERCISE_DOMAIN_CONTROLLERS[@]}"'),
        )
        self.assertIn("preflight_domain_health", text)

    def test_exercise_restart_uses_guestops_without_runtime_nat_hotplug(self):
        text = self.text

        for token in (
            "prove_isolated_guest_ready()",
            'proving authenticated readiness through VMware Guest Operations',
            'ethernet0 remains persistently OFF and runtime disconnected',
            'READINESS_TRANSPORT=guestops',
            'authenticated post-reboot readiness proven through VMware Guest Operations',
            'prove_isolated_guest_ready "${vm}" member',
            'prove_isolated_guest_ready "${vm}" dc',
        ):
            self.assertIn(token, text)

        fn = text[text.index("prove_isolated_guest_ready()"):
                  text.index("configure_windows_nat_exercise()")]

        self.assertIn('[[ "${persistent}" == "FALSE" ]]', fn)
        self.assertIn('is_running "${vmx}"', fn)
        self.assertIn('READINESS_TRANSPORT=guestops', fn)
        self.assertNotIn('vmrun_named_device_action', fn)
        self.assertNotIn('connectNamedDevice', fn)
        self.assertNotIn('disconnectNamedDevice', fn)

        readiness = fn.index('case "${kind}" in')
        final_proof = fn.index(
            'authenticated post-reboot readiness proven through VMware Guest Operations'
        )
        self.assertLess(readiness, final_proof)

    def test_provisioning_powers_on_cleanly_stopped_guests_before_readiness(self):
        text = self.text
        ensure = text[text.index("ensure_vm_nat_state()"):
                      text.index("vagrant_powershell_ready()")]

        self.assertIn(
            '[[ "${desired}" == "TRUE" && "${action}" == "connect" ]]',
            ensure,
        )
        self.assertIn("VM is powered off; starting it for provisioning readiness", ensure)
        self.assertIn('vmrun -T ws start "${vmx}" nogui', ensure)
        self.assertIn('wait_started "${vmx}"', ensure)
        self.assertIn("did not start for provisioning readiness", ensure)
        self.assertIn("runtime connect requested while VM is powered off", ensure)

        provisioning = text[text.index("configure_windows_nat_provisioning()"):
                            text.index("prove_isolated_guest_ready()")]
        self.assertLess(
            provisioning.index('ensure_vm_nat_state "${vm}" TRUE connect'),
            provisioning.index('wait_domain_controller_ready "${vm}"'),
        )
        self.assertLess(
            provisioning.rindex('ensure_vm_nat_state "${vm}" TRUE connect'),
            provisioning.index('wait_domain_member_ready "${vm}"'),
        )

    def test_vmware_management_nic_is_pinned_before_direct_lifecycle_power_on(self):
        text = self.text

        self.assertIn("pin_vmware_management_nic_identity()", text)
        helper = text[text.index("pin_vmware_management_nic_identity()"):
                      text.index("get_start_connected()")]

        for token in (
            'ethernet0.addresstype',
            'ethernet0.generatedAddress',
            'ethernet0.address',
            'uuid.action',
            'ethernet0.checkMACAddress',
            'KINGDOMS_VMWARE_MANAGEMENT_NIC_PINNED',
            'type=static',
            'refusing to pin VMware management NIC identity while VM is running',
        ):
            self.assertIn(token, helper)

        self.assertIn('address_type == "generated"', helper)
        self.assertIn('address_type == "static"', helper)
        self.assertIn('set_value(updated, "ethernet0.address", pinned)', helper)
        self.assertIn('remove_key(updated, "ethernet0.generatedAddress")', helper)
        self.assertIn('remove_key(updated, "ethernet0.generatedAddressOffset")', helper)
        self.assertNotIn('uuid.bios =', helper)
        self.assertNotIn('uuid.location =', helper)

        ensure = text[text.index("ensure_vm_nat_state()"):
                      text.index("vagrant_powershell_ready()")]

        self.assertGreaterEqual(
            ensure.count('pin_vmware_management_nic_identity "${vmx}"'),
            2,
        )

        stop_wait = ensure.index('wait_stopped "${vmx}"')
        first_pin = ensure.index('pin_vmware_management_nic_identity "${vmx}"')
        persist = ensure.index('set_start_connected "${vmx}" "${desired}"')
        self.assertLess(stop_wait, first_pin)
        self.assertLess(first_pin, persist)

        powered_off = ensure.index(
            'VM is powered off; starting it for provisioning readiness'
        )
        second_pin = ensure.index(
            'pin_vmware_management_nic_identity "${vmx}"',
            first_pin + 1,
        )
        direct_start = ensure.index(
            'vmrun -T ws start "${vmx}" nogui',
            powered_off,
        )
        self.assertLess(powered_off, second_pin)
        self.assertLess(second_pin, direct_start)

    def test_isolated_readiness_fails_fast_if_guest_is_powered_off(self):
        text = self.text
        fn = text[text.index("prove_isolated_guest_ready()"):
                  text.index("configure_windows_nat_exercise()")]

        self.assertIn(
            'authenticated exercise-readiness probe requires the VM to be powered on',
            fn,
        )
        self.assertLess(
            fn.index('is_running "${vmx}"'),
            fn.index('READINESS_TRANSPORT=guestops'),
        )

    def test_vmware_named_device_actions_remain_provisioning_only(self):
        text = self.text
        helper = text[text.index("vmrun_named_device_action()"):
                      text.index("ensure_vm_nat_state()")]
        self.assertIn("connectNamedDevice", helper)
        self.assertIn("disconnectNamedDevice", helper)
        self.assertIn("attempt<=attempts", helper)
        self.assertIn('if output="$(vmrun -T ws', helper)
        self.assertIn("rc=$?", helper)
        self.assertIn("already.*connected", helper)
        self.assertIn("already.*disconnected", helper)

        ensure = text[text.index("ensure_vm_nat_state()"):
                      text.index("guestops_credential_value()")]
        self.assertIn('vmrun_named_device_action "${vm}" "${action}" 15 2', ensure)
        self.assertNotIn("connectNamedDevice", ensure)
        self.assertNotIn("disconnectNamedDevice", ensure)
        self.assertNotIn("|| true", ensure)

        isolated = text[text.index("prove_isolated_guest_ready()"):
                        text.index("configure_windows_nat_exercise()")]
        self.assertNotIn('vmrun_named_device_action', isolated)
        self.assertIn('READINESS_TRANSPORT=guestops', isolated)

    def test_guestops_capture_and_time_diagnostic_are_distinct_top_level_functions(self):
        text = self.text
        self.assertEqual(text.count("\nvmware_guest_powershell_capture() {"), 1)
        self.assertEqual(text.count("\nguestops_time_check() ("), 1)
        self.assertEqual(text.count("\npowershell_capture() {"), 1)
        self.assertNotIn("vmware_guest_guestops_time_check", text)
    def test_guestops_capture_is_authenticated_bounded_and_cleans_up(self):
        text = self.text
        helper = text[text.index("guestops_credential_value()"):
                      text.index("vagrant_powershell_ready()")]

        for token in (
            'inventory_disable_vagrant',
            '[GOAD-WS01]="srv02"',
            'copyFileFromHostToGuest',
            'runProgramInGuest',
            'copyFileFromGuestToHost',
            'deleteFileInGuest',
            'guest_script',
            'host_script',
            "'-File'",
            "'Bypass'",
            'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe',
            'Start-Process',
            'RedirectStandardOutput =',
            'RedirectStandardError =',
            'wrapper_encoded',
            'timeout --kill-after=1 "${remaining}" vmrun',
            'mktemp',
        ):
            self.assertIn(token, text)

        self.assertIn('guestops_credential_value "${vm}" ansible_user', helper)
        self.assertIn('guestops_credential_value "${vm}" ansible_password', helper)
        self.assertIn('powershell_capture()', helper)
        self.assertIn('guestops)', helper)
        self.assertIn('vmware_guest_powershell_capture', helper)

        self.assertNotIn('inner_encoded', helper)
        self.assertNotIn("'EncodedCommand',", helper)
        self.assertIn('copyFileFromHostToGuest', helper)

    def test_dc_readiness_uses_selected_transport_and_limits_nat_self_heal_to_vagrant(self):
        text = self.text
        dc = text[text.index("wait_domain_controller_ready()"):
                  text.index("wait_domain_member_ready()")]

        self.assertIn('local last_state="reason=transport"', dc)
        self.assertIn('powershell_capture "${vm}" "${script}" "${probe_timeout}"', dc)
        self.assertIn("reason=guest_probe_failure", dc)
        self.assertIn("reason=guest_probe_no_ready_marker", dc)
        self.assertIn("bounded VMware transport self-heal", dc)
        self.assertIn('[[ "${READINESS_TRANSPORT:-vagrant}" == "vagrant" ]]', dc)
        self.assertIn('vmrun_named_device_action "${vm}" connect 3 2 || true', dc)
        self.assertIn("last PowerShell readiness output follows", dc)
        self.assertIn('tail -80', dc)

    def test_failed_lifecycle_has_fail_closed_network_isolation_path(self):
        text = self.text
        fn = text[text.index("enter_exercise_failsafe()"):
                  text.index("enter_provisioning_mode()")]

        self.assertIn("set_state recovery-required", fn)
        self.assertIn('bash "${ROUTES}" disable', fn)
        self.assertIn('ensure_vm_nat_state "${vm}" FALSE disconnect', fn)
        self.assertIn("verify_persistent_state FALSE", fn)
        self.assertIn("apply_router_policy exercise", fn)
        self.assertIn("policy drop;", fn)
        self.assertIn("mode remains recovery-required", fn)
        self.assertIn("set_state exercise", fn)
        self.assertIn("does not claim AD/domain readiness", fn)

        self.assertLess(fn.index('bash "${ROUTES}" disable'), fn.index("apply_router_policy exercise"))
        self.assertLess(
            fn.index('ensure_vm_nat_state "${vm}" FALSE disconnect'),
            fn.index("apply_router_policy exercise"),
        )
        self.assertLess(fn.index("set_state recovery-required"), fn.index("set_state exercise"))

        main = text[text.index("main()"):]
        self.assertIn("exercise-failsafe)", main)

    def test_status_reports_local_vm_state_even_when_router_query_fails(self):
        text = self.text
        fn = text[text.index("show_status()"):
                  text.index("enter_exercise_mode()")]

        self.assertIn("[UNAVAILABLE] router management/policy query failed", fn)
        self.assertIn("router_status=1", fn)
        self.assertIn("=== WINDOWS VM NETWORK STATE ===", fn)
        self.assertIn('return "${router_status}"', fn)

    def test_targeted_guestops_readiness_command_uses_isolated_readiness_contract(self):
        text = self.text
        fn = text[text.index("guestops_readiness_check()"):
                  text.index("enter_provisioning_mode()")]

        self.assertIn('kind="dc"', fn)
        self.assertIn('kind="member"', fn)
        self.assertIn('prove_isolated_guest_ready "${vm}" "${kind}"', fn)
        self.assertIn("targeted GuestOps readiness passed", fn)

        main = text[text.index("main()"): ]
        self.assertIn("guestops-readiness-check)", main)
        self.assertIn('guestops_readiness_check "${2:-GOAD-DC02}"', main)

    def test_guestops_time_check_runs_exact_child_time_probe_once(self):
        text = self.text
        start = text.index("\nguestops_time_check() (") + 1
        end = text.index("\npowershell_capture() {", start)
        fn = text[start:end]

        for token in (
            'w32tm.exe /query /source',
            'nltest.exe \'/dsgetdc:${domain}\' /timeserv /force',
            'KINGDOMS_TIME_DIAG|stage=source',
            'KINGDOMS_DC_TIME_NOT_READY',
            'KINGDOMS_DC_TIME_READY',
            'READINESS_TRANSPORT=guestops',
            'AD_READINESS_PROBE_TIMEOUT_SECONDS',
        ):
            self.assertIn(token, fn)

        main = text[text.index("main()"): ]
        self.assertIn("guestops-time-check)", main)
        self.assertIn('guestops_time_check "${2:-GOAD-DC02}"', main)

    def test_winrm_helpers_use_explicit_nested_timeout(self):
        text = self.text
        helpers = text[text.index("vagrant_powershell_ready()"):
                       text.index("ensure_child_dc_time_ready()")]

        self.assertIn('local timeout_seconds="$3"', helpers)
        self.assertEqual(helpers.count('timeout "${timeout_seconds}" vagrant winrm'), 2)
        self.assertNotIn("timeout 90 vagrant winrm", helpers)

    def test_readiness_deadlines_cap_selected_transport_to_remaining_budget(self):
        text = self.text

        for token in (
            "readonly AD_READINESS_TIMEOUT_SECONDS=300",
            "readonly AD_READINESS_PROBE_TIMEOUT_SECONDS=15",
            "readonly AD_READINESS_RETRY_DELAY_SECONDS=5",
            "readonly AD_REPAIR_TIMEOUT_SECONDS=90",
        ):
            self.assertIn(token, text)

        child = text[text.index("ensure_child_dc_time_ready()"):
                     text.index("wait_domain_controller_ready()")]
        dc = text[text.index("wait_domain_controller_ready()"):
                  text.index("wait_domain_member_ready()")]
        member = text[text.index("wait_domain_member_ready()"):
                      text.index("preflight_domain_health()")]

        for fn in (child, dc, member):
            self.assertIn('local started="${SECONDS}"', fn)
            self.assertIn(
                "while (( SECONDS - started < AD_READINESS_TIMEOUT_SECONDS )); do",
                fn,
            )
            self.assertIn("remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))", fn)
            self.assertIn(
                '(( remaining < probe_timeout )) && probe_timeout="${remaining}"',
                fn,
            )
            self.assertNotIn("for attempt in {1..60}", fn)

        self.assertIn(
            'powershell_capture "${vm}" "${probe_script}" "${probe_timeout}"',
            child,
        )
        self.assertIn(
            'powershell_capture "${vm}" "${script}" "${probe_timeout}"',
            dc,
        )
        self.assertIn(
            'powershell_capture "${vm}" "${script}" "${probe_timeout}"',
            member,
        )

        # A repair is allowed a larger inner timeout, but never more than the
        # parent readiness window still has left.
        for fn in (child, member):
            self.assertIn('repair_timeout="${AD_REPAIR_TIMEOUT_SECONDS}"', fn)
            self.assertIn(
                '(( remaining < repair_timeout )) && repair_timeout="${remaining}"',
                fn,
            )
            self.assertIn(
                'powershell_capture "${vm}" "${repair_script}" "${repair_timeout}"',
                fn,
            )

        for fn in (child, dc, member):
            self.assertNotIn('vagrant_powershell_capture "${vm}"', fn)

    def test_declared_300s_readiness_budget_is_not_attempt_math(self):
        text = self.text
        relevant = text[text.index("ensure_child_dc_time_ready()"):
                        text.index("preflight_domain_health()")]

        self.assertNotIn("$((attempt * 5))", relevant)
        self.assertNotIn("for attempt in {1..60}", relevant)
        self.assertGreaterEqual(
            relevant.count("AD_READINESS_TIMEOUT_SECONDS - elapsed"),
            3,
        )

    def test_dc_readiness_is_ad_aware_not_merely_winrm(self):
        text = self.text

        for token in (
            "ADPS_LoadDefaultDrive",
            "Get-ADRootDSE",
            "SYSVOL",
            "NETLOGON",
            "nltest.exe '/dsgetdc:",
            "KINGDOMS_DC_RUNTIME_READY",
        ):
            self.assertIn(token, text)

    def test_child_dc_time_hierarchy_is_explicit_and_repaired_before_members(self):
        text = self.text

        for token in (
            'DC_TIME_PARENT_DOMAIN',
            '[GOAD-DC02]="sevenkingdoms.local"',
            'DC_TIME_PARENT_SERVER',
            '[GOAD-DC02]="kingslanding.sevenkingdoms.local"',
            'ensure_child_dc_time_ready()',
            "nltest.exe '/dsgetdc:${parent_domain}' /timeserv /force",
            "w32tm.exe /stripchart /computer:${parent_server}",
            "w32tm.exe /config /syncfromflags:domhier /update",
            "w32tm.exe /resync /rediscover /nowait",
            "KINGDOMS_DC_TIME_REPAIRED",
            "KINGDOMS_DC_TIME_REPAIR_DEFERRED",
            "KINGDOMS_DC_TIME_REPAIR_FAILED",
        ):
            self.assertIn(token, text)

        fn = text[text.index("wait_domain_controller_ready()"):
                  text.index("wait_domain_member_ready()")]
        self.assertIn('ensure_child_dc_time_ready "${vm}"', fn)

    def test_recorded_exercise_preflights_child_time_before_member_isolation(self):
        text = self.text
        fn = text[text.index("enter_exercise_mode()"):
                  text.index("enter_provisioning_mode()")]

        self.assertIn("preflight_exercise_time_dependencies", fn)
        self.assertLess(
            fn.index("preflight_exercise_time_dependencies"),
            fn.index("configure_windows_nat_exercise"),
        )

        dep = text[text.index("preflight_exercise_time_dependencies()"):
                   text.index("configure_windows_nat_provisioning()")]
        self.assertIn('prove_isolated_guest_ready "${vm}" dc', dep)
        self.assertIn('DC_TIME_PARENT_DOMAIN', dep)

    def test_shell_marker_parser_ignores_clixml_after_valid_time_marker(self):
        text = self.text
        start = text.index("last_marker_line() {")
        end = text.index("ensure_child_dc_time_ready() {", start)
        helper = text[start:end]

        sample = (
            "\ufeffKINGDOMS_DC_TIME_NOT_READY|reason=source|"
            "source=Local CMOS Clock|"
            "expected=kingslanding.sevenkingdoms.local\r\n\r\n"
            "#< CLIXML\r\n<Objs Version=\"1.1.0.1\">progress</Objs>\r\n"
        )

        script = helper + r'''
output="$1"
last_marker_line "$output" \
    'KINGDOMS_DC_TIME_READY|' \
    'KINGDOMS_DC_TIME_NOT_READY|'
'''
        result = subprocess.run(
            ["bash", "-c", script, "marker-test", sample],
            capture_output=True,
            text=True,
            timeout=3,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            "KINGDOMS_DC_TIME_NOT_READY|reason=source|"
            "source=Local CMOS Clock|"
            "expected=kingslanding.sevenkingdoms.local",
        )

        self.assertIn('*"${prefix}"*', helper)

    def test_child_time_preserves_guest_marker_and_bounds_guestops_transport_failure(self):
        text = self.text
        fn = text[text.index("ensure_child_dc_time_ready()"):
                  text.index("wait_domain_controller_ready()")]

        for token in (
            'local capture_rc=0',
            'local consecutive_transport_failures=0',
            'capture_rc=$?',
            'last_marker_line "${output}"',
            "'KINGDOMS_GUESTOPS_ERROR|'",
            "'KINGDOMS_DC_TIME_READY|'",
            "'KINGDOMS_DC_TIME_NOT_READY|'",
            "'KINGDOMS_DC_TIME_REPAIRED|'",
            "'KINGDOMS_DC_TIME_REPAIR_DEFERRED|'",
            "'KINGDOMS_DC_TIME_REPAIR_FAILED|'",
            'reason=no_time_marker|capture_rc=0',
            'consecutive_transport_failures >= 3',
            'child-domain time probe transport failed 3 consecutive times after AD readiness',
        ):
            self.assertIn(token, fn)

        # Marker extraction must not be nested only inside a successful
        # transport return; current guest output remains useful evidence.
        probe_capture = fn.index('if output="$(powershell_capture "${vm}" "${probe_script}" "${probe_timeout}")"')
        marker_extract = fn.index('last_marker_line "${output}"', probe_capture)
        ready_check = fn.index('if [[ "${marker}" == KINGDOMS_DC_TIME_READY\\|* ]]' , marker_extract)
        self.assertLess(probe_capture, marker_extract)
        self.assertLess(marker_extract, ready_check)

        self.assertNotIn("grep -E 'KINGDOMS_DC_TIME_", fn)
        self.assertNotIn("grep -F 'KINGDOMS_GUESTOPS_ERROR|'", fn)

    def test_child_dc_time_repair_uses_deterministic_parent_dns_and_ntp_prereqs(self):
        text = self.text
        fn = text[text.index("ensure_child_dc_time_ready()"):
                  text.index("wait_domain_controller_ready()")]

        self.assertIn("_ldap._tcp.pdc._msdcs.${parent_domain}", fn)
        self.assertIn("Resolve-DnsName", fn)
        self.assertIn("KINGDOMS_DC_TIME_REPAIR_DEFERRED|stage=parent_pdc_dns", fn)
        self.assertIn("KINGDOMS_DC_TIME_REPAIR_DEFERRED|stage=parent_ntp_path", fn)
        self.assertNotIn("KINGDOMS_DC_TIME_REPAIR_DEFERRED|stage=parent_domain_locator", fn)
        self.assertNotIn("KINGDOMS_DC_TIME_REPAIR_DEFERRED|stage=parent_timeserv_locator", fn)

        # DC Locator is still primed during rediscovery, but a transient 1355 is
        # no longer a hard prerequisite before W32Time recovery is attempted.
        self.assertIn("Prime DC Locator best-effort", fn)
        self.assertIn("nltest.exe '/dsgetdc:${parent_domain}' /timeserv /force", fn)

        for marker in (
            "KINGDOMS_DC_TIME_REPAIRED|",
            "KINGDOMS_DC_TIME_REPAIR_DEFERRED|",
            "KINGDOMS_DC_TIME_REPAIR_FAILED|",
        ):
            self.assertIn(marker, fn)
        self.assertIn("repair_deferred=$((repair_deferred + 1))", fn)
        self.assertIn("repair_invocations=$((repair_invocations + 1))", fn)
        self.assertIn("parent prerequisite is not ready yet", fn)
        self.assertIn("recovery failed after prerequisites were proven", fn)
    def test_child_dc_time_repair_is_bounded_and_never_rewrites_trust(self):
        text = self.text
        fn = text[text.index("ensure_child_dc_time_ready()"):
                  text.index("wait_domain_controller_ready()")]

        self.assertIn("repair_attempted == 0", fn)
        self.assertIn("consecutive_source_failures >= 6", fn)
        self.assertIn("syncAttempt -le 12", fn)

        for forbidden in (
            "Reset-ComputerMachinePassword",
            "/sc_reset:",
            "netdom resetpwd",
        ):
            self.assertNotIn(forbidden, fn)

    def test_member_readiness_proves_trust_account_lookup_and_domain_time(self):
        text = self.text

        for token in (
            "Test-ComputerSecureChannel -Server",
            "System.Security.Principal.NTAccount",
            "Translate([System.Security.Principal.SecurityIdentifier])",
            "w32tm.exe /query /source",
            "expected=${dc}",
            "KINGDOMS_MEMBER_RUNTIME_READY",
        ):
            self.assertIn(token, text)

    def test_member_readiness_emits_exact_failure_class(self):
        text = self.text
        fn = text[text.index("wait_domain_member_ready()"):
                  text.index("preflight_domain_health()")]

        for marker in (
            "KINGDOMS_MEMBER_NOT_READY|reason=dns",
            "KINGDOMS_MEMBER_NOT_READY|reason=secure_channel",
            "KINGDOMS_MEMBER_NOT_READY|reason=account_translation",
            "KINGDOMS_MEMBER_NOT_READY|reason=netlogon_session",
            "KINGDOMS_MEMBER_NOT_READY|reason=time|source=",
            "reason=transport",
        ):
            self.assertIn(marker, fn)

        self.assertIn(
            'did not regain domain identity readiness for ${domain} within 300s; ${last_state}',
            fn,
        )

    def test_member_lifecycle_uses_one_bounded_time_only_repair(self):
        text = self.text
        fn = text[text.index("wait_domain_member_ready()"):
                  text.index("preflight_domain_health()")]

        for token in (
            "consecutive_time_failures >= 6",
            "time_repair_attempted == 0",
            "w32tm.exe /config /syncfromflags:domhier /update",
            "nltest.exe '/dsgetdc:${domain}' /timeserv /force",
            "w32tm.exe /stripchart /computer:${dc}",
            "nltest.exe '/sc_query:${domain}'",
            "Restart-Service W32Time -Force",
            "w32tm.exe /resync /rediscover /nowait",
            "KINGDOMS_MEMBER_TIME_REPAIRED",
            "KINGDOMS_MEMBER_TIME_REPAIR_FAILED",
        ):
            self.assertIn(token, fn)

        # Normal lifecycle may recover W32Time only. Directory trust repair
        # remains an explicit maintenance/provisioning operation.
        for forbidden in (
            "Reset-ComputerMachinePassword",
            "/sc_reset:",
            "netdom resetpwd",
        ):
            self.assertNotIn(forbidden, fn)

    def test_time_repair_requires_identity_probe_to_reach_time_stage(self):
        text = self.text
        fn = text[text.index("wait_domain_member_ready()"):
                  text.index("preflight_domain_health()")]

        self.assertLess(
            fn.index("Resolve-DnsName '${dc}'"),
            fn.index("Test-ComputerSecureChannel -Server '${dc}'"),
        )
        self.assertLess(
            fn.index("Test-ComputerSecureChannel -Server '${dc}'"),
            fn.index("System.Security.Principal.NTAccount"),
        )
        self.assertLess(
            fn.index("System.Security.Principal.NTAccount"),
            fn.index("nltest.exe '/sc_query:${domain}'"),
        )
        self.assertLess(
            fn.index("nltest.exe '/sc_query:${domain}'"),
            fn.index("w32tm.exe /query /source"),
        )
        self.assertIn(
            'if [[ "${last_state}" == reason=time\\|* ]]; then',
            fn,
        )

    def test_member_time_recovery_requires_live_netlogon_session(self):
        text = self.text
        fn = text[text.index("wait_domain_member_ready()"):
                  text.index("preflight_domain_health()")]

        for token in (
            "KINGDOMS_MEMBER_NOT_READY|reason=netlogon_session",
            "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=netlogon_session",
            "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=netlogon_session_lost",
            "netlogon_session=ready",
        ):
            self.assertIn(token, fn)

    def test_time_repair_failure_marker_is_not_hidden(self):
        text = self.text
        fn = text[text.index("wait_domain_member_ready()"):
                  text.index("preflight_domain_health()")]

        self.assertIn(
            "KINGDOMS_MEMBER_TIME_(REPAIRED|REPAIR_FAILED)",
            fn,
        )
        self.assertIn(
            'elif [[ "${marker}" == KINGDOMS_MEMBER_TIME_REPAIR_FAILED\\|* ]]; then',
            fn,
        )
        self.assertIn(
            'bounded domain-time recovery failed: ${marker}',
            fn,
        )
        self.assertNotIn(
            "time-recovery command returned without a success marker",
            fn,
        )


class GuestOpsDeadlineTests(unittest.TestCase):
    def run_fixture(self, stall="", run_delay=0, run_rc=0, budget=2,
                    failure="", check=False, credential_failure=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bindir = root / "bin"
            hostdir = root / "host-results"
            bindir.mkdir()
            hostdir.mkdir()
            vmx = root / "fixture.vmx"
            vmx.touch()
            source = root / "lab-mode-functions.sh"
            source.write_text(
                LAB_MODE.read_text().rsplit('\nmain "$@"', 1)[0],
                encoding="utf-8",
            )
            fake_vmrun = bindir / "vmrun"
            fake_vmrun.write_text('''#!/usr/bin/env bash
set -eu
operation=""
for arg in "$@"; do
    case "$arg" in
        list|runProgramInGuest|copyFileFromGuestToHost|deleteFileInGuest)
            operation="$arg" ;;
    esac
done
printf '%s\n' "$operation" >> "$TEST_CALLS"
if [[ "$TEST_STALL" == "$operation" ]]; then
    exec sleep 30
fi
if [[ "$TEST_FAILURE" == "$operation" ]]; then
    printf 'Error: rejected %s / %s\n' "$TEST_USER" "$TEST_PASSWORD" >&2
    exit 7
fi
case "$operation" in
    list)
        printf 'Total running VMs: 1\n%s\n' "$TEST_VMX" ;;
    runProgramInGuest)
        sleep "$TEST_RUN_DELAY"
        printf '%s\n' "$TEST_OUTPUT" > "$TEST_GUEST_RESULT"
        exit "$TEST_RUN_RC" ;;
    copyFileFromGuestToHost)
        cp "$TEST_GUEST_RESULT" "${@: -1}" ;;
    deleteFileInGuest)
        rm -f "$TEST_GUEST_RESULT" ;;
    *) exit 99 ;;
esac
''', encoding="utf-8")
            fake_vmrun.chmod(0o700)
            env = {
                **os.environ,
                "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
                "TEST_CALLS": str(root / "calls"),
                "TEST_VMX": str(vmx),
                "TEST_HOST_DIR": str(hostdir),
                "TEST_GUEST_RESULT": str(root / "guest-result"),
                "TEST_STALL": stall,
                "TEST_RUN_DELAY": str(run_delay),
                "TEST_RUN_RC": str(run_rc),
                "TEST_FAILURE": failure,
                "TEST_USER": "NORTH\\fixture-admin",
                "TEST_PASSWORD": "fixture*[a]\\secret&",
                "TEST_OUTPUT": "KINGDOMS_GUESTOPS_CAPTURE=PASS" if check else "fixture guest output",
                "TEST_CHECK": "1" if check else "0",
                "TEST_CREDENTIAL_FAILURE": "1" if credential_failure else "0",
            }
            harness = '''
source "$1"
vmx_for() { printf '%s\n' "$TEST_VMX"; }
guestops_credential_value() {
    if [[ "$TEST_CREDENTIAL_FAILURE" == 1 ]]; then
        printf 'Fixture inventory unavailable\n' >&2
        return 1
    fi
    case "$2" in
        ansible_user) printf '%s\n' "$TEST_USER" ;;
        ansible_password) printf '%s\n' "$TEST_PASSWORD" ;;
    esac
}
mktemp() { command mktemp "$TEST_HOST_DIR/kingdoms-guestops.XXXXXX"; }
READINESS_TRANSPORT=guestops
if [[ "$TEST_CHECK" == 1 ]]; then
    get_start_connected() { printf 'FALSE\n'; }
    guestops_check GOAD-DC02
else
    powershell_capture GOAD-DC02 "Write-Output 'fixture'" "$2"
fi
'''
            started = time.monotonic()
            result = subprocess.run(
                ["bash", "-c", harness, "guestops-test", str(source), str(budget)],
                env=env, capture_output=True, text=True, timeout=8,
            )
            elapsed = time.monotonic() - started
            self.assertEqual(list(hostdir.iterdir()), [])
            calls = (root / "calls").read_text().splitlines()
            return result, elapsed, calls, (root / "guest-result").exists()

    def test_guest_output_and_exit_status_survive_result_collection(self):
        for run_rc in (0, 9):
            with self.subTest(run_rc=run_rc):
                result, _, calls, guest_result_exists = self.run_fixture(run_rc=run_rc)
                self.assertEqual(result.returncode, run_rc, result.stderr)
                self.assertTrue(result.stdout.startswith("fixture guest output\n"))
                if run_rc:
                    self.assertIn(f"KINGDOMS_GUESTOPS_ERROR|stage=run|rc={run_rc}|", result.stdout)
                else:
                    self.assertEqual(result.stdout, "fixture guest output\n")
                self.assertEqual(calls, [
                    "list", "runProgramInGuest", "copyFileFromGuestToHost",
                    "deleteFileInGuest",
                ])
                self.assertFalse(guest_result_exists)

    def test_stalled_tools_calls_share_one_probe_deadline(self):
        for stall, run_delay, budget, expected_rc in (
            ("list", 0, 1, 124),
            ("runProgramInGuest", 0, 1, 124),
            # Leave headroom for Bash's integer SECONDS clock so the delayed
            # launch reliably reaches the operation this case intends to stall.
            ("copyFileFromGuestToHost", 1, 3, 124),
            ("deleteFileInGuest", 1, 3, 0),
        ):
            with self.subTest(stall=stall):
                result, elapsed, calls, _ = self.run_fixture(
                    stall=stall, run_delay=run_delay, budget=budget,
                )
                self.assertEqual(result.returncode, expected_rc, result.stderr)
                self.assertLess(elapsed, budget + 1.5)
                self.assertEqual(calls[-1], stall)
                if stall == "deleteFileInGuest":
                    self.assertEqual(result.stdout, "fixture guest output\n")
                else:
                    expected_stage = {
                        "list": "list", "runProgramInGuest": "run",
                        "copyFileFromGuestToHost": "copy",
                    }[stall]
                    self.assertIn(f"KINGDOMS_GUESTOPS_ERROR|stage={expected_stage}|", result.stdout)

    def test_guestops_errors_identify_failed_stage_and_redact_credentials(self):
        for operation, stage in (("runProgramInGuest", "run"),
                                 ("copyFileFromGuestToHost", "copy")):
            with self.subTest(operation=operation):
                result, elapsed, calls, _ = self.run_fixture(failure=operation, budget=1)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"KINGDOMS_GUESTOPS_ERROR|stage={stage}|rc=7|", result.stdout)
                self.assertIn("Error: rejected [REDACTED] / [REDACTED]", result.stdout)
                self.assertNotIn("NORTH\\fixture-admin", result.stdout + result.stderr)
                self.assertNotIn("fixture*[a]\\secret&", result.stdout + result.stderr)
                self.assertLess(elapsed, 2.5)
                if stage == "run":
                    self.assertEqual(calls.count("copyFileFromGuestToHost"), 1)

    def test_missing_credentials_stop_before_guest_execution(self):
        result, _, calls, _ = self.run_fixture(credential_failure=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Fixture inventory unavailable", result.stderr)
        self.assertEqual(calls, ["list"])

    def test_guestops_check_runs_one_capture_without_readiness_loop(self):
        result, _, calls, _ = self.run_fixture(check=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GuestOps execution and output capture passed", result.stdout)
        self.assertEqual(calls, [
            "list", "runProgramInGuest", "copyFileFromGuestToHost", "deleteFileInGuest",
        ])


if __name__ == "__main__":
    unittest.main()
