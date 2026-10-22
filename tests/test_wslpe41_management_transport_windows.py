"""PowerShell 5.1 stream tests, also over real loopback WinRM on hosted CI only.

No lab is contacted. Loopback setup requires the explicit hosted-runner flag;
ordinary Windows runs execute only harmless local child-process tests.
"""
import base64
import hashlib
import os
from pathlib import Path
import random
import secrets
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from kingdoms import wslpe41_operator_management as management


@unittest.skipUnless(os.name == 'nt', 'Requires real Windows PowerShell 5.1')
class WindowsTransportTests(unittest.TestCase):
    def session(self):
        session = Mock()
        # The real source exits at its wrong-guest guard, before any mutation.
        env = {**os.environ, 'COMPUTERNAME': 'WSLPE-TRANSPORT-TEST'}

        def execute(*_):
            call = session.protocol.run_command.call_args
            self.assertTrue(call.kwargs['skip_cmd_shell'])
            result = subprocess.run(
                [call.args[1], *call.args[2]],
                input=b''.join(c.args[2] for c in session.protocol.send_command_input.call_args_list),
                capture_output=True, timeout=60, env=env, check=False,
            )
            session.last_result = result
            return result.stdout, result.stderr, result.returncode

        session.protocol.get_command_output.side_effect = execute
        return session

    def old_command(self, script):
        # Reproduce the cmd.exe limit locally. Opening another remote shell for
        # this obsolete path adds no coverage of the production stdin runner.
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        result = subprocess.run(
            ['cmd.exe', '/d', '/c', 'powershell.exe', '-EncodedCommand', encoded],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False,
            env={**os.environ, 'COMPUTERNAME': 'WSLPE-TRANSPORT-TEST'},
        )
        return SimpleNamespace(status_code=result.returncode, std_out=result.stdout, std_err=result.stderr)

    def test_actual_inspection_reaches_guest_guard_beyond_cmd_limit(self):
        session = self.session()
        with self.assertRaisesRegex(management.ManagementBlocked, 'Wrong standalone guest'):
            management.invoke(session, 'Inspect')
        call = session.protocol.run_command.call_args
        argv = [call.args[1], *call.args[2]]
        self.assertLess(len(' '.join(argv)), 2048)
        payload = b''.join(c.args[2] for c in session.protocol.send_command_input.call_args_list)
        script = base64.b64decode(payload).decode('utf-8')
        self.assertGreater(len(base64.b64encode(script.encode('utf-16le'))), 8191)
        old = self.old_command(script)
        self.assertNotEqual(old.status_code, 0)
        self.assertNotIn(b'WSLPE_OPERATOR_ERROR=', old.std_out)
        self.assertIn(b'command line is too long', old.std_err.lower())

    def test_full_sized_prepare_wrapper_keeps_exact_recovery_source(self):
        # Benign fixture only; no account, firewall, listener or recovery writes.
        source = (
            "param($Mode,$Nonce,$SourceBase64)\n"
            "if ($PSVersionTable.PSVersion.Major -ne 5) { throw 'Expected Windows PowerShell 5.1' }\n"
            "if ($Mode -cne 'Prepare' -or $Nonce -cne ('a'*32)) { throw 'Arguments changed' }\n"
            "$hash=[Security.Cryptography.SHA256]::Create().ComputeHash([Convert]::FromBase64String($SourceBase64));\n"
            "Write-Output ('SOURCE_SHA256=' + [BitConverter]::ToString($hash).Replace('-',''));\n"
            "Write-Output 'WSLPE_OPERATOR_PREPARED=PASS'\n#"
            + random.Random(41).randbytes(4000).hex() + '\n'
        )
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'fixture.ps1'
            script.write_bytes(source.encode('utf-8'))
            session = self.session()
            with patch.object(management, 'SCRIPT', script):
                management.invoke(session, 'Prepare', nonce='a' * 32, install=True)
            self.assertIn(
                ('SOURCE_SHA256=' + hashlib.sha256(source.encode('utf-8')).hexdigest().upper()).encode('ascii'),
                session.last_result.stdout,
            )
        call = session.protocol.run_command.call_args
        self.assertLess(len(' '.join([call.args[1], *call.args[2]])), 2048)
        session.protocol.cleanup_command.assert_called_once()
        session.protocol.close_shell.assert_called_once()

    def test_loader_errors_also_emit_diagnostic_marker(self):
        with patch.object(management, 'run_powershell', return_value=SimpleNamespace(
                status_code=0, std_out=b'WSLPE_OPERATOR_POLICY=PASS\n', std_err=b'')) as run:
            management.invoke(Mock(), 'Verify')
        script = run.call_args.args[1]
        # Break only the compressed public source, before scriptblock execution.
        start = script.index("$b='") + len("$b='")
        end = script.index("'", start)
        broken = script[:start] + 'invalid-base64' + script[end:]
        result = management.run_powershell(self.session(), broken)
        self.assertEqual(result.status_code, 1)
        self.assertTrue(result.std_out.startswith(b'WSLPE_OPERATOR_ERROR='))
        self.assertEqual(len(result.std_out.splitlines()), 1)


@unittest.skipUnless(
    os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
    and os.environ.get('KINGDOMS_TEST_LOOPBACK_WINRM') == '1',
    'Real WinRM fixture is restricted to the explicitly enabled disposable hosted CI runner',
)
class LoopbackWinRMTests(WindowsTransportTests):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('COMPUTERNAME', '').upper() == 'WSLPE-WS01':
            raise RuntimeError('A lab VM cannot be used as the CI transport fixture')
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.username = 'wslpeci-' + secrets.token_hex(4)
        cls.password = 'Ci!42' + secrets.token_urlsafe(32)
        cls.env = {**os.environ, 'KINGDOMS_CI_WINRM_USER': cls.username,
                   'KINGDOMS_CI_WINRM_PASSWORD': cls.password}
        cls.fixture = Path(__file__).parent / 'fixtures' / 'wslpe-management-winrm-ci.ps1'
        cls.state = Path(cls.temp.name) / 'state.json'
        cls.addClassCleanup(cls.configure, 'Cleanup')
        cls.configure('Setup')

    @classmethod
    def configure(cls, mode):
        result = subprocess.run(
            ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-File',
             str(cls.fixture), '-Mode', mode, '-StatePath', str(cls.state)],
            env=cls.env, stdin=subprocess.DEVNULL, capture_output=True, timeout=90, check=False,
        )
        if result.returncode:
            # Fixture source never writes the generated password to output.
            detail = result.stderr.decode('utf-8', errors='replace').replace(cls.password, '[redacted]')
            raise RuntimeError(f'CI-only WinRM {mode} failed: {detail[:1500]}')

    def session(self):
        import winrm
        session = winrm.Session(
            'http://127.0.0.1:5985/wsman',
            auth=(os.environ['COMPUTERNAME'] + '\\' + self.username, self.password),
            transport='ntlm', message_encryption='always', proxy=None,
            # First logon of the temporary CI account can initialize a profile.
            operation_timeout_sec=60, read_timeout_sec=70,
        )
        for name in ('run_command', 'send_command_input', 'cleanup_command', 'close_shell'):
            setattr(session.protocol, name, Mock(wraps=getattr(session.protocol, name)))
        original = session.protocol.get_command_output
        def capture(*args):
            stdout, stderr, status = original(*args)
            session.last_result = SimpleNamespace(stdout=stdout, stderr=stderr, returncode=status)
            return stdout, stderr, status
        session.protocol.get_command_output = Mock(side_effect=capture)
        self.addCleanup(session.protocol.transport.close_session)
        return session

    def test_secure_service_policy_over_real_winrm_preserves_network_and_listeners(self):
        source = base64.b64encode(management.SCRIPT.read_bytes()).decode('ascii')
        # Only the explicitly enabled hosted fixture's temporary account runs
        # this test. Registry policy is restored in finally; no lab is contacted.
        script = r'''
$ErrorActionPreference='Stop'
if ($env:USERNAME -cnotmatch '^wslpeci-[a-f0-9]{8}$' -or $env:COMPUTERNAME -eq 'WSLPE-WS01') {
    throw 'Expected disposable CI account'
}
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseInput(
    [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__SOURCE__')), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Production script parse failed' }
foreach ($definition in $ast.FindAll({ param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -in @('Set-SecureWinRM','Get-WSBool')
}, $false)) { Invoke-Expression $definition.Extent.Text }
$path='SOFTWARE\Policies\Microsoft\Windows\WinRM\Service'
$key=[Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($path, $true)
$existed=$null -ne $key
$saved=@{}
foreach ($name in @('AllowBasic','AllowUnencryptedTraffic')) {
    $present=$existed -and $key.GetValueNames() -contains $name
    $saved[$name]=@{Present=$present}
    if ($present) { $saved[$name].Value=$key.GetValue($name); $saved[$name].Kind=$key.GetValueKind($name) }
}
if ($key) { $key.Dispose() }
function Snapshot-Management {
    return (@{
        Profiles=@(Get-NetConnectionProfile | Select-Object InterfaceIndex,NetworkCategory | Sort-Object InterfaceIndex)
        Listeners=@(Get-WSManInstance winrm/config/listener -Enumerate | Select-Object Address,Transport,Port,Hostname,CertificateThumbprint | Sort-Object Transport,Address)
        Rules=@(Get-NetFirewallRule | Select-Object Name,Enabled,Profile,Action | Sort-Object Name)
    } | ConvertTo-Json -Depth 5 -Compress)
}
$before=Snapshot-Management
$StatePath=Join-Path $env:TEMP ('wslpe-policy-' + [guid]::NewGuid().ToString('N') + '.clixml')
$state=[pscustomobject]@{Instance='ci-only'; Nonce='unchanged'}
try {
    Set-SecureWinRM $state
    if ((Get-Item WSMan:\localhost\Service\Auth\Basic).SourceOfValue -ne 'GPO' -or
        (Get-Item WSMan:\localhost\Service\AllowUnencrypted).SourceOfValue -ne 'GPO') {
        throw 'Effective WinRM values must come from service policy'
    }
    if ((Snapshot-Management) -cne $before) { throw 'Management policy altered network, listeners or firewall' }
    if ((Import-Clixml -LiteralPath $StatePath).Nonce -cne 'unchanged') { throw 'Recovery nonce changed' }
    Write-Output 'WSLPE_CI_SECURE_POLICY=PASS'
} finally {
    $key=[Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($path, $true)
    if ($key) {
        foreach ($name in $saved.Keys) {
            if ($saved[$name].Present) { $key.SetValue($name,$saved[$name].Value,$saved[$name].Kind) }
            else { $key.DeleteValue($name,$false) }
        }
        $empty=$key.ValueCount -eq 0 -and $key.SubKeyCount -eq 0
        $key.Dispose()
        if (-not $existed -and $empty) { [Microsoft.Win32.Registry]::LocalMachine.DeleteSubKey($path) }
    }
    if (Test-Path -LiteralPath $StatePath) { Remove-Item -LiteralPath $StatePath }
}
'''.replace('__SOURCE__', source)
        result = management.run_powershell(self.session(), script)
        self.assertEqual(result.status_code, 0, management.failure_detail(result))
        self.assertIn(b'WSLPE_CI_SECURE_POLICY=PASS', result.std_out)

if __name__ == '__main__':
    unittest.main()
