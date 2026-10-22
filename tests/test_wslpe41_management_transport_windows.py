"""Real Windows PowerShell 5.1 process tests; no lab or WinRM policy changes.

The WinRM SOAP option is covered separately with the real pywinrm serializer.
Here CreateProcess executes the exact generated command, including its size,
decompression, source parsing and error wrapper. This is not live VM acceptance.
"""
import base64
import hashlib
import os
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

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
                [call.args[1], *call.args[2]], stdin=subprocess.DEVNULL,
                capture_output=True, timeout=60, env=env, check=False,
            )
            session.last_result = result
            return result.stdout, result.stderr, result.returncode

        session.protocol.get_command_output.side_effect = execute
        return session

    def test_actual_inspection_reaches_guest_guard_beyond_cmd_limit(self):
        session = self.session()
        with self.assertRaisesRegex(management.ManagementBlocked, 'Wrong standalone guest'):
            management.invoke(session, 'Inspect')
        call = session.protocol.run_command.call_args
        argv = [call.args[1], *call.args[2]]
        self.assertGreater(len(' '.join(argv)), 8191)
        # Reproduce the previous route: cmd.exe rejects the very same command
        # before PowerShell can emit its guest-identity error marker.
        old = subprocess.run(
            ['cmd.exe', '/d', '/c', *argv], stdin=subprocess.DEVNULL,
            capture_output=True, timeout=30, check=False,
            env={**os.environ, 'COMPUTERNAME': 'WSLPE-TRANSPORT-TEST'},
        )
        self.assertNotEqual(old.returncode, 0)
        self.assertNotIn(b'WSLPE_OPERATOR_ERROR=', old.stdout)
        self.assertIn(b'command line is too long', old.stderr.lower())

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
        self.assertGreater(len(' '.join([call.args[1], *call.args[2]])), 8191)
        session.protocol.cleanup_command.assert_called_once()
        session.protocol.close_shell.assert_called_once()

    def test_loader_errors_also_emit_diagnostic_marker(self):
        session = self.session()
        session.protocol.get_command_output.side_effect = None
        session.protocol.get_command_output.return_value = (b'WSLPE_OPERATOR_POLICY=PASS\n', b'', 0)
        management.invoke(session, 'Verify')
        call = session.protocol.run_command.call_args
        script = base64.b64decode(call.args[2][-1]).decode('utf-16le')
        # Break only the compressed public source, before scriptblock execution.
        start = script.index("$b='") + len("$b='")
        end = script.index("'", start)
        broken = script[:start] + 'invalid-base64' + script[end:]
        arguments = [*call.args[2][:-1], base64.b64encode(broken.encode('utf-16le')).decode('ascii')]
        result = subprocess.run(
            [call.args[1], *arguments], stdin=subprocess.DEVNULL,
            capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith(b'WSLPE_OPERATOR_ERROR='))
        self.assertEqual(len(result.stdout.splitlines()), 1)


if __name__ == '__main__':
    unittest.main()
