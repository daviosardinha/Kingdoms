"""Kingdoms RDP contract; stdlib-only tests, no lab access or credential probes."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'ansible/roles/linux/guacamole_create_connections/filter_plugins/kingdoms_rdp.py'
spec = importlib.util.spec_from_file_location('kingdoms_rdp', PLUGIN)
rdp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rdp)


class RdpAccessContractTests(unittest.TestCase):
    def setUp(self):
        self.lab = json.loads((ROOT / 'ad/GOAD/data/config.json').read_text())['lab']
        self.hosts = self.lab['hosts']
        self.domain = 'north.sevenkingdoms.local'
        self.users = self.lab['domains'][self.domain]['users']

    def text(self, path):
        return (ROOT / path).read_text()

    def allowed(self, host, user, domain=None, groups=None):
        domain = domain or self.domain
        groups = self.users[user]['groups'] if groups is None else groups
        return rdp.kingdoms_rdp_allowed(self.hosts[host], domain, user, groups, self.lab['domains'])

    def test_exact_three_host_allowlists(self):
        expected = {'dc02': [], 'srv02': ['north\\robb.stark'], 'ws01': ['north\\rickon.stark']}
        for host, members in expected.items():
            with self.subTest(host=host):
                self.assertEqual(self.hosts[host]['local_groups']['Remote Desktop Users'], members)
                self.assertEqual(self.hosts[host]['exact_local_groups'], ['Remote Desktop Users'])

    def test_no_other_hosts_opt_in(self):
        opted_in = {key for key, value in self.hosts.items() if value.get('exact_local_groups')}
        self.assertEqual(opted_in, {'dc02', 'srv02', 'ws01'})

    def test_five_user_fifteen_connection_matrix(self):
        for user in ('hodor', 'brandon.stark', 'jon.snow', 'samwell.tarly', 'rickon.stark'):
            for host in ('dc02', 'srv02', 'ws01'):
                with self.subTest(user=user, host=host):
                    self.assertEqual(self.allowed(host, user), user == 'rickon.stark' and host == 'ws01')

    def test_robb_exception_is_host_specific(self):
        self.assertTrue(self.allowed('dc02', 'robb.stark'))
        self.assertTrue(self.allowed('srv02', 'robb.stark'))
        self.assertFalse(self.allowed('ws01', 'robb.stark'))

    def test_existing_admin_routes_retained(self):
        for user in ('eddard.stark', 'catelyn.stark', 'robb.stark'):
            self.assertTrue(self.allowed('dc02', user))
        self.assertTrue(self.allowed('srv02', 'jeor.mormont'))
        self.assertTrue(self.allowed('ws01', 'eddard.stark'))

    def test_same_name_other_domain_not_allowed(self):
        self.assertFalse(self.allowed('ws01', 'rickon.stark', 'sevenkingdoms.local', []))
        self.assertFalse(self.allowed('srv02', 'robb.stark', 'sevenkingdoms.local', []))
        self.assertFalse(self.allowed('ws01', 'outsider', 'essos.local', ['Domain Admins']))

    def test_case_insensitive_qualified_identity(self):
        host = copy.deepcopy(self.hosts['ws01'])
        host['local_groups']['Remote Desktop Users'] = ['NORTH\\RICKON.STARK']
        self.assertTrue(rdp.kingdoms_rdp_allowed(host, self.domain, 'rickon.stark', [], self.lab['domains']))

    def test_unmanaged_legacy_hosts_keep_existing_generation(self):
        host = {'domain': 'legacy.local', 'local_groups': {'Remote Desktop Users': ['legacy\\Team']}}
        self.assertTrue(rdp.kingdoms_rdp_allowed(host, self.domain, 'someone', ['Team'], self.lab['domains']))

    def test_non_rdp_lab_data_unchanged_from_audited_baseline(self):
        # Intentional future non-RDP curriculum changes must explicitly rebaseline
        # this guard after review, not quietly pass as an RDP-only change.
        lab = copy.deepcopy(self.lab)
        for key in ('dc02', 'srv02', 'ws01'):
            lab['hosts'][key]['local_groups'].pop('Remote Desktop Users')
            lab['hosts'][key].pop('exact_local_groups')
        digest = hashlib.sha256(json.dumps(lab, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(digest, 'e1d1fdc7e11504344abea9ef00a17d20f6def0d6d12a1e756a9a31fec7ab22a2')

    def test_protected_foundation_files_unchanged(self):
        expected = {
            'ansible/roles/settings/user_rights/tasks/main.yml': '7325210bd188b827c9f289fb42488742c17b665edf4033a01ff1d5888f58f6f4',
            'ansible/roles/common/tasks/main.yml': 'aec530b0addc9088c89a57e6500c02deba0516c95d436c4745f54ed1238f9b1d',
            'ad/GOAD/scripts/rdp_scheduler.ps1': 'af1fa86d8cccb9a81addf95aecb30d3a8d93672075c34f7627869445a9f2c0d2',
            'ad/GOAD/files/dc02/bot_rdp.ps1': '4ead342fe794a1260093db797d73ce421cd1724a58a8ee6df14b0bf6e2d744b5',
            'ansible/roles/phase01/dc/files/anonymous-sid-translation-gpo.ps1': '97a4d301de121a7359da4b19d30408e490178345065974a738b200c8f7e468b1',
            'scripts/validate-phase01.py': '989b3565ff3a627fe1945373c821f646bab126b8b033a134829c0925aa649b5e',
        }
        for path, digest in expected.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)

    def test_pure_is_opt_in_and_restricted_to_rdp(self):
        text = self.text('ansible/roles/settings/adjust_rights/tasks/main.yml')
        self.assertIn("'pure' if item.key in (exact_local_groups | default([])) else 'present'", text)
        self.assertIn("difference(['Remote Desktop Users'])", text)
        self.assertIn('difference(local_groups.keys() | list)', text)
        self.assertNotIn('state: pure', text)

    def test_all_provisioning_entry_points_pass_opt_in(self):
        for path in ('ansible/ad-relations.yml', 'ansible/ws01.yml', 'ansible/kingdoms-rdp.yml'):
            with self.subTest(path=path):
                self.assertIn('exact_local_groups:', self.text(path))
                self.assertIn('settings/adjust_rights', self.text(path))

    def test_targeted_migration_does_not_reprovision_services_or_admins(self):
        text = self.text('ansible/kingdoms-rdp.yml')
        self.assertIn('hosts: dc02:srv02:ws01', text)
        self.assertNotIn('import_playbook:', text)
        self.assertNotIn('role: common', text)
        self.assertNotIn('Administrators:', text)
        self.assertIn("$cs.Domain -ine 'north.sevenkingdoms.local'", text)

    def test_existing_runtime_checks_require_exclusive_rickon(self):
        for path in ('scripts/validate-ws01-runtime.sh', 'scripts/validate-network-segmentation-runtime.sh'):
            with self.subTest(path=path):
                self.assertIn('$rdpUsers.Count -ne 1', self.text(path))
                self.assertIn('scripts/validate-rdp-runtime.sh', self.text(path))

    def test_runtime_reads_effective_allow_and_deny_and_nested_aliases(self):
        text = self.text('scripts/rdp-host-evidence.ps1')
        for token in ('SeRemoteInteractiveLogonRight', 'SeDenyRemoteInteractiveLogonRight',
                      'LsaEnumerateAccountsWithUserRight', 'S-1-5-32-544', 'S-1-5-32-555',
                      "$_ -notlike 'S-1-5-32-*'", '$tokens.Count -ne $before', 'gpresult.exe'):
            self.assertIn(token, text)
        self.assertIn('tokenGroups', self.text('scripts/rdp-directory-evidence.ps1'))

    def test_north_phase02_selects_exact_reduced_instance_inventory(self):
        phase02 = self.text('scripts/validate-phase02-readiness.sh')
        rdp = self.text('scripts/validate-rdp-runtime.sh')
        self.assertIn('KINGDOMS_PHASE02_PROFILE:-GOAD', phase02)
        self.assertIn('KINGDOMS_RDP_DATA_INVENTORY="$ROOT/ad/NORTH/data/inventory"', phase02)
        self.assertIn('KINGDOMS_RDP_INVENTORY="$(dirname "$PROVIDER")/inventory"', phase02)
        self.assertIn('KINGDOMS_RDP_SCENARIO_CONFIG="$ROOT/ad/NORTH/data/config.json"', phase02)
        self.assertIn('KINGDOMS_RDP_DATA_INVENTORY', rdp)
        self.assertIn('KINGDOMS_RDP_SCENARIO_CONFIG', rdp)
        self.assertIn('SCENARIO_EXTRA=(-e "@${SCENARIO_CONFIG}")', rdp)
        self.assertIn('"${SCENARIO_EXTRA[@]}"', rdp)

    def test_legacy_goad_rdp_defaults_remain_available(self):
        rdp = self.text('scripts/validate-rdp-runtime.sh')
        self.assertIn('KINGDOMS_RDP_DATA_INVENTORY:-${ROOT}/ad/GOAD/data/inventory', rdp)
        self.assertIn('KINGDOMS_RDP_INVENTORY:-${ROOT}/ad/GOAD/providers/vmware/inventory', rdp)
        self.assertIn('SCENARIO_CONFIG="${KINGDOMS_RDP_SCENARIO_CONFIG:-}"', rdp)

    def test_runtime_does_not_modify_windows_state(self):
        for path in ('scripts/rdp-host-evidence.ps1', 'scripts/rdp-directory-evidence.ps1'):
            text = self.text(path)
            for forbidden in ('Set-AD', 'Add-LocalGroupMember', 'Remove-LocalGroupMember',
                              'LsaAddAccountRights', 'LsaRemoveAccountRights', 'Start-ScheduledTask',
                              'gpupdate', 'secedit.exe', 'logoff.exe'):
                with self.subTest(path=path, forbidden=forbidden):
                    self.assertNotIn(forbidden, text)

    def test_directory_collector_skips_implicit_ad_drive_initialization(self):
        text = self.text('scripts/rdp-directory-evidence.ps1')
        disable = "$Env:ADPS_LoadDefaultDrive = '0'"
        module_import = 'Import-Module ActiveDirectory'
        self.assertIn(disable, text)
        self.assertLess(text.index(disable), text.index(module_import))

    def test_directory_token_groups_use_explicit_base_search(self):
        text = self.text('scripts/rdp-directory-evidence.ps1')
        self.assertIn('Get-ADUser -Identity $name -Server $cs.Name', text)
        self.assertIn('-SearchBase $resolved.DistinguishedName -SearchScope Base', text)
        self.assertIn('-Server $cs.Name -Properties tokenGroups,Enabled', text)
        self.assertIn('$matches.Count -ne 1', text)
        self.assertIn('$userSid -ne (ConvertTo-KingdomsSidValue $resolved.SID)', text)
        self.assertNotIn('-Identity $name -Properties tokenGroups', text)

    def test_sid_conversion_is_type_aware(self):
        text = self.text('scripts/rdp-directory-evidence.ps1')
        self.assertIn('$Sid -is [System.Security.Principal.SecurityIdentifier]', text)
        self.assertIn('$Sid -is [byte[]]', text)
        self.assertIn('$Sid -is [string]', text)
        self.assertIn('Unsupported directory SID representation', text)
        for path in ('scripts/rdp-directory-evidence.ps1', 'scripts/rdp-host-evidence.ps1'):
            self.assertNotIn('New-Object System.Security.Principal', self.text(path))

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell required for mocked directory queries')
    def test_directory_collector_mocked_queries(self):
        result = subprocess.run(
            ['pwsh', '-NoProfile', '-NonInteractive', '-File',
             str(ROOT / 'tests/test_rdp_directory_evidence.ps1')],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_never_claims_real_logins(self):
        self.assertIn('DESKTOP_LOGON_MATRIX=NOT_EXECUTED', self.text('scripts/rdp-host-evidence.ps1'))
        self.assertIn('WTSQuerySessionInformationW', self.text('scripts/rdp-host-evidence.ps1'))
        self.assertIn('Existing session evidence may predate', self.text('scripts/validate-rdp-runtime.sh'))

    def test_directory_transport_explicitly_preserves_json_text(self):
        text = self.text('ansible/validate-kingdoms-rdp.yml')
        self.assertIn("hostvars['dc02'].rdp_directory.output[0] | from_json | to_json", text)
        self.assertIn('exactly the six expected identities', self.text('scripts/rdp-host-evidence.ps1'))

    def test_bot_principal_is_compared_by_sid_not_name_format(self):
        text = self.text('scripts/rdp-host-evidence.ps1')
        self.assertIn("Resolve-KingdomsAccountSid 'NORTH\\robb.stark'", text)
        self.assertIn('$actualBotSid -ne $expectedBotSid', text)
        self.assertIn('CONNECT_BOT_PRINCIPAL=$taskIdentity', text)
        self.assertNotIn('$task.Principal.UserId -inotmatch', text)

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell required for host policy fixtures')
    def test_host_collector_fixture_matrix(self):
        result = subprocess.run(
            ['pwsh', '-NoProfile', '-NonInteractive', '-File',
             str(ROOT / 'tests/test_rdp_host_evidence.ps1')],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_guacamole_does_not_merge_legacy_ws01_over_kingdoms(self):
        text = self.text('extensions/guacamole/ansible/install.yml')
        self.assertIn("not (item == 'ws01' and 'ws01' in lab.hosts)", text)
        self.assertEqual(text.count('when: item.ansible_facts is defined'), 2)

    def test_guacamole_uses_same_predicate_for_create_and_cleanup(self):
        text = self.text('ansible/roles/linux/guacamole_create_connections/tasks/users_hosts.yml')
        self.assertEqual(text.count('kingdoms_rdp_allowed('), 3)
        self.assertIn('state: absent', text)
        self.assertIn("'Remote Desktop Users' in hosts_data.value.get('exact_local_groups', [])", text)
        self.assertIn('RDP-ws01-casterlyrock-', text)
        self.assertNotIn('password: {{user_password}} |', text)

    def test_guacamole_ws01_password_and_cache_handling(self):
        text = self.text('ansible/roles/linux/guacamole_create_connections/tasks/main.yml')
        self.assertIn('default(domains[item.value.domain].domain_password)', text)
        self.assertIn('connection_list: []', text)
        self.assertIn('RDP-ws01-casterlyrock-localadmin', text)

    def test_runtime_shell_syntax_and_help(self):
        script = ROOT / 'scripts/validate-rdp-runtime.sh'
        subprocess.run(['bash', '-n', str(script)], check=True)
        result = subprocess.run(['bash', str(script), '--help'], check=True, capture_output=True, text=True)
        self.assertIn('No credential attempts are made', result.stdout)

    def test_release_acceptance_uses_real_fresh_logons_and_restores_rickon(self):
        text = self.text('scripts/validate-rdp-release-acceptance.sh')
        self.assertIn('RDP_DESKTOP_LOGON_MATRIX=PASS:15/15', text)
        self.assertIn('RDP_RELEASE_ACCEPTANCE_COMPLETE=True', text)
        self.assertIn('EXPECTED_DENIALS_PASS=%d', text)
        self.assertIn('capture-rdp-release-event-baseline.yml', text)
        self.assertIn('validate-rdp-denial-event.yml', text)
        self.assertIn('RDP_SECURITY_BASELINE_RECORD_ID=', text)
        self.assertIn('RDP_RDPCORE_BASELINE_RECORD_ID=', text)
        self.assertIn('RDP_DENIAL_EVENT=PASS', text)
        self.assertIn("grep -Fq 'RDP_DENIAL_EVENT=PASS|'", text)
        self.assertIn('grep -Fq "|HOST=$host|"', text)
        self.assertNotIn('grep -Fq "RDP_DENIAL_EVENT=PASS|USER=$DOMAIN_NB\\\\$user|HOST=$host|"', text)
        self.assertIn('NXC_PATH="$nxc_path"', text)
        self.assertIn('xfreerdp3 /args-from:stdin', text)
        self.assertIn("RDP_FRESH_TOKEN_NONADMIN=PASS", text)
        self.assertIn('systemctl --user stop "$RICKON_SERVICE"', text)
        self.assertIn('systemctl --user start "$RICKON_SERVICE"', text)
        self.assertIn('validate-rickon-session.sh', text)
        self.assertIn('ansible/validate-rdp-fresh-rickon.yml', text)
        self.assertIn('ansible/logoff-rickon-rdp.yml', text)
        self.assertIn('RELEASE PLAYBOOK SYNTAX GATE', text)
        self.assertIn('--resume-latest', text)
        self.assertIn('verify_denial_evidence_set', text)
        self.assertNotIn('mktemp /tmp/kingdoms-rdp-release-probe', text)
        self.assertNotIn("Add-Type -TypeDefinition @'", text)
        self.assertNotIn('xfreerdp3 /p:', text)

        script = ROOT / 'scripts/validate-rdp-release-acceptance.sh'
        subprocess.run(['bash', '-n', str(script)], check=True)
        result = subprocess.run(
            ['bash', str(script), '--help'],
            check=True, capture_output=True, text=True)
        self.assertIn('fourteen fresh RDP attempts', result.stdout)
        self.assertIn('one fresh NORTH\\rickon.stark -> WS01 RDP desktop login', result.stdout)

    def test_fresh_rickon_probe_is_committed_outside_yaml(self):
        playbook = self.text('ansible/validate-rdp-fresh-rickon.yml')
        probe = self.text('ansible/files/validate-rdp-fresh-rickon.ps1')
        logoff = self.text('ansible/logoff-rickon-rdp.yml')

        self.assertIn("lookup('ansible.builtin.file'", playbook)
        self.assertIn('validate-rdp-fresh-rickon.ps1', playbook)
        self.assertIn("Add-Type -TypeDefinition @'", probe)
        self.assertIn("RDP_FRESH_SESSION=PASS", probe)
        self.assertIn("RDP_FRESH_TOKEN_NONADMIN=PASS", probe)
        self.assertIn("TOKEN_ADMIN_SID_PRESENT=$isAdmin", probe)
        self.assertIn("RICKON_LOGOFF_COMPLETE=True", logoff)
        self.assertNotIn('using System;', playbook)

    def test_release_event_playbooks_are_syntax_check_self_contained(self):
        baseline = self.text('ansible/capture-rdp-release-event-baseline.yml')
        validator = self.text('ansible/validate-rdp-denial-event.yml')

        self.assertIn("rdp_event_target | default('dc02')", baseline)
        self.assertIn("rdp_event_target | default('dc02')", validator)
        self.assertIn("rdp_event_user | default('hodor')", validator)
        self.assertIn("rdp_security_after_record_id | default(0)", validator)
        self.assertIn("rdp_rdpcore_after_record_id | default(0)", validator)

    def test_release_denial_baseline_uses_event_record_ids(self):
        baseline = self.text('ansible/capture-rdp-release-event-baseline.yml')
        validator = self.text('ansible/validate-rdp-denial-event.yml')

        self.assertIn('RDP_SECURITY_BASELINE_RECORD_ID=', baseline)
        self.assertIn('RDP_RDPCORE_BASELINE_RECORD_ID=', baseline)
        self.assertIn('RecordId', baseline)
        self.assertIn('SecurityAfterRecordId', validator)
        self.assertIn('RdpCoreAfterRecordId', validator)
        self.assertIn('$_.RecordId -gt $SecurityAfterRecordId', validator)
        self.assertIn('$_.RecordId -gt $RdpCoreAfterRecordId', validator)
        self.assertNotIn('SinceUtc', validator)

    def test_release_denial_validator_correlates_rdp_core_access_denial(self):
        playbook = self.text('ansible/validate-rdp-denial-event.yml')
        self.assertRegex(playbook, r"Id\s*=\s*4624,4625")
        self.assertIn("LogonType -eq '3'", playbook)
        self.assertIn("Id -eq 227", playbook)
        self.assertIn('User is not granted access to this connection', playbook)
        self.assertIn('RDPCORE_ACCESS_NOT_GRANTED', playbook)
        self.assertIn('SECURITY_4625_LOGON_TYPE_NOT_GRANTED', playbook)
        self.assertIn('RDP_DENIAL_CORRELATION', playbook)
        self.assertIn('DELTA_MS=', playbook)
        self.assertIn('$_.TimeCreated -ge $authTime', playbook)
        self.assertIn('$authTime.AddSeconds(2)', playbook)
        self.assertIn('Event 65 is useful', playbook)

    def test_rdp_release_denial_diagnostic_is_read_only_and_broad(self):
        playbook = self.text('ansible/diagnose-rdp-release-attempt.yml')
        diagnostic = self.text('scripts/diagnose-rdp-release-denial.sh')

        self.assertRegex(playbook, r"Id\s*=\s*4624,4625")
        self.assertIn("Credential Validation", playbook)
        self.assertIn("Id        = 4776", playbook)
        self.assertIn("TerminalServices-RemoteConnectionManager/Operational", playbook)
        self.assertIn("TerminalServices-LocalSessionManager/Operational", playbook)
        self.assertIn("-ErrorAction SilentlyContinue", playbook)
        self.assertIn("RDP_TARGET_DIAGNOSTIC_COMPLETE=True", playbook)
        self.assertIn("RDP_DC_DIAGNOSTIC_COMPLETE=True", playbook)
        self.assertIn('10.4.10.254', diagnostic)
        self.assertIn('diagnose-rdp-release-attempt.yml', diagnostic)
        for forbidden in ('xfreerdp', 'Set-AD', 'Add-LocalGroupMember',
                          'Remove-LocalGroupMember', 'gpupdate', 'logoff.exe'):
            self.assertNotIn(forbidden, diagnostic)

        script = ROOT / 'scripts/diagnose-rdp-release-denial.sh'
        subprocess.run(['bash', '-n', str(script)], check=True)

    def test_rdp_release_timeline_diagnostic_is_read_only(self):
        playbook = self.text('ansible/diagnose-rdp-release-timeline.yml')
        diagnostic = self.text('scripts/diagnose-rdp-release-timeline.sh')

        self.assertIn('RDP_TIMELINE_DIAGNOSTIC_COMPLETE=True', playbook)
        self.assertIn('SECURITY|ID={0}', playbook)
        self.assertIn('TerminalServices-RemoteConnectionManager/Operational', playbook)
        self.assertIn('TerminalServices-LocalSessionManager/Operational', playbook)
        self.assertIn('RemoteDesktopServices-RdpCoreTS/Operational', playbook)
        self.assertIn('SYSTEM_TIMELINE_COUNT=', playbook)
        self.assertIn('diagnose-rdp-release-timeline.yml', diagnostic)

        for forbidden in ('xfreerdp', 'Set-AD', 'Add-LocalGroupMember',
                          'Remove-LocalGroupMember', 'gpupdate', 'logoff.exe'):
            self.assertNotIn(forbidden, diagnostic)

        script = ROOT / 'scripts/diagnose-rdp-release-timeline.sh'
        subprocess.run(['bash', '-n', str(script)], check=True)

    def test_release_evidence_summary_is_read_only(self):
        text = self.text('scripts/summarize-rdp-release-evidence.sh')
        self.assertIn('RDP_RELEASE_EVIDENCE_SUMMARY_COMPLETE=True', text)
        self.assertIn('RDP_DENIAL_EVENT=', text)
        self.assertIn('RDP_DESKTOP_LOGON_MATRIX=', text)
        for forbidden in ('xfreerdp', 'Set-AD', 'Add-LocalGroupMember',
                          'Remove-LocalGroupMember', 'gpupdate', 'logoff.exe',
                          'systemctl --user stop', 'systemctl --user start'):
            self.assertNotIn(forbidden, text)

        script = ROOT / 'scripts/summarize-rdp-release-evidence.sh'
        subprocess.run(['bash', '-n', str(script)], check=True)

    def test_invalid_runtime_options_fail_closed(self):
        script = ROOT / 'scripts/validate-rdp-runtime.sh'
        for args in (['--host', 'dc01'], ['--bogus'], ['--source-only', '--phase01']):
            with self.subTest(args=args):
                result = subprocess.run(['bash', str(script), *args], capture_output=True)
                self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
