"""Management-only handoff regressions. Mocked Windows is NOT live acceptance."""
import base64
import datetime
from contextlib import contextmanager, nullcontext
import errno
import gzip
import hashlib
import json
from pathlib import Path
import socket
import ssl
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
import xml.etree.ElementTree as ET

from kingdoms import wslpe41_operator_management as management


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / 'management.json'
        self.target = SimpleNamespace(vmx=self.directory / 'fresh.vmx', instance=self.directory)
        self.certificate = b'public-test-certificate'
        self.data = dict(
            Instance=management.nic.INSTANCE,
            Certificate=base64.b64encode(self.certificate).decode(),
            Thumbprint=hashlib.sha1(self.certificate).hexdigest().upper(),
            OperatorExists=False, NatAddress='192.168.213.249', Identity=r'WSLPE-WS01\vagrant',
        )
        self.receipt = dict(instance=management.nic.INSTANCE, vmx=str(self.target.vmx),
                            certificate=self.data['Certificate'],
                            sha256=hashlib.sha256(self.certificate).hexdigest(), nonce='a' * 32,
                            phase='preparing')

    def test_read_only_verify_never_creates_user_or_narrows_firewall(self):
        management.save_receipt(self.path, self.receipt)
        with (patch.object(management, 'exact_target', return_value=self.target),
              patch.object(management, 'operator_secret', return_value='prepared-secret'),
              patch.object(management, 'receipt_path', return_value=self.path),
              patch.object(management, 'auth_helper'),
              patch.object(management, 'prove_operator', return_value=self.data) as proof,
              patch.object(management, 'negative_probes') as negatives,
              patch.object(management, 'create_operator') as create,
              patch.object(management, 'bootstrap_session') as bootstrap,
              patch.object(management, 'invoke') as mutation):
            management.run(report=Mock())
        self.assertEqual(proof.call_args.kwargs['mode'], 'Verify')
        negatives.assert_called_once_with(self.data['NatAddress'])
        create.assert_not_called()
        bootstrap.assert_not_called()
        mutation.assert_not_called()

    def test_private_receipt_cannot_substitute_another_instance_or_certificate(self):
        management.save_receipt(self.path, self.receipt)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(management.read_receipt(self.path, self.target), self.receipt)
        for changes in ({'instance': 'd986ad-wslpe-vmware'}, {'vmx': '/other.vmx'},
                        {'sha256': '0' * 64}, {'nonce': 'not-a-nonce'}):
            management.save_receipt(self.path, {**self.receipt, **changes})
            with self.assertRaises(management.ManagementBlocked):
                management.read_receipt(self.path, self.target)
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            management.read_receipt(self.path, self.target)

    def test_windows_identity_and_certificate_must_be_complete_and_consistent(self):
        def parse(data):
            return management.parse_inspection((management.JSON_MARKER + json.dumps(data)).encode())
        self.assertEqual(parse(self.data), self.data)
        for changes in ({'Instance': 'NORTH'}, {'OperatorExists': 1},
                        {'Thumbprint': '0' * 40}, {'Certificate': 'invalid-base64'}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, management.ManagementBlocked)):
                parse({**self.data, **changes})
        with self.assertRaises(management.ManagementBlocked):
            management.parse_inspection(b'WSLPE_OPERATOR_JSON={}\nWSLPE_OPERATOR_JSON={}\n')

    def test_tls_rejection_happens_before_private_credential_session_creation(self):
        auth = Mock()
        auth.tls_audit_module.return_value.verify_pinned_tls.side_effect = ssl.SSLError('bad cert')
        with patch('winrm.Session') as session:
            with self.assertRaises(ssl.SSLError), management.operator_session(auth, b'bad-cert', 'private'):
                self.fail('must never yield an unverified session')
            session.assert_not_called()

    def test_tls_ntlm_session_uses_scoped_ca_hostname_and_no_environment_proxy(self):
        auth = Mock()
        auth.scoped_wslpe_resolution.return_value = nullcontext()
        transport = MagicMock()
        def session_factory(*args, **kwargs):
            self.assertEqual(args, ('https://WSLPE-WS01:5986/wsman',))
            self.assertEqual(kwargs['server_cert_validation'], 'validate')
            self.assertEqual(kwargs['transport'], 'ntlm')
            transport.build_session.return_value.verify = kwargs['ca_trust_path']
            self.assertTrue(Path(kwargs['ca_trust_path']).is_file())
            return SimpleNamespace(protocol=SimpleNamespace(transport=transport))
        with patch('winrm.Session', side_effect=session_factory):
            with management.operator_session(auth, self.certificate, 'private'):
                self.assertFalse(transport.build_session.return_value.trust_env)
        transport.close_session.assert_called_once()
        auth.scoped_wslpe_resolution.assert_called_once_with(management.ADDRESS)

    def test_no_false_pass_on_missing_or_nonzero_windows_marker(self):
        for output in ((b'WSLPE_OPERATOR_POLICY=PASS', b'', 1),
                       (b'', b'', 0), (b'WSLPE_OPERATOR_POLICY=PASS\n' * 2, b'', 0)):
            session = Mock()
            session.protocol.get_command_output.return_value = output
            with self.assertRaises(management.ManagementBlocked):
                management.invoke(session, 'Verify', nonce='a' * 32)

    def test_transport_fits_windows_command_limit_and_preserves_original_source(self):
        session = Mock()
        session.protocol.get_command_output.return_value = (b'WSLPE_OPERATOR_PREPARED=PASS\n', b'', 0)
        management.invoke(session, 'Prepare', nonce='a' * 32, install=True)
        call = session.protocol.run_command.call_args
        executable, arguments = call.args[1:]
        command_line = ' '.join([executable, *arguments])
        self.assertGreater(len(command_line), 8191)  # Original run_ps() cannot carry this.
        self.assertLess(len(command_line) + 1, 30_000)
        self.assertTrue(call.kwargs['skip_cmd_shell'])
        self.assertEqual(executable, 'powershell.exe')
        self.assertIn('-NoProfile', arguments)
        command = base64.b64decode(arguments[-1]).decode('utf-16le')
        encoded = command.split("$b='", 1)[1].split("'", 1)[0]
        self.assertEqual(gzip.decompress(base64.b64decode(encoded)), management.SCRIPT.read_bytes())
        session.run_ps.assert_not_called()

    def test_pywinrm_serializes_direct_process_option_and_separate_executable(self):
        import winrm
        session = winrm.Session('http://127.0.0.1:5985/wsman', auth=('unused', 'unused'), transport='ntlm')
        protocol = session.protocol
        reply = '<rsp:CommandResponse xmlns:rsp="http://schemas.microsoft.com/wbem/wsman/1/windows/shell"><rsp:CommandId>command</rsp:CommandId></rsp:CommandResponse>'
        with (patch.object(protocol, 'open_shell', return_value='shell'),
              patch.object(protocol, 'send_message', return_value=reply) as send,
              patch.object(protocol, 'get_command_output', return_value=(b'WSLPE_OPERATOR_POLICY=PASS\n', b'', 0)),
              patch.object(protocol, 'cleanup_command') as cleanup,
              patch.object(protocol, 'close_shell') as close):
            management.invoke(session, 'Verify', nonce='a' * 32)
        document = ET.fromstring(send.call_args.args[0])
        options = {node.attrib['Name']: node.text for node in document.iter()
                   if node.tag.endswith('}Option')}
        self.assertEqual(options['WINRS_SKIP_CMD_SHELL'], 'TRUE')
        command = next(node.text for node in document.iter() if node.tag.endswith('}Command'))
        arguments = next(node.text for node in document.iter() if node.tag.endswith('}Arguments'))
        self.assertEqual(command, 'powershell.exe')
        self.assertGreater(len(arguments), 8191)
        self.assertIn('-NonInteractive -EncodedCommand ', arguments)
        cleanup.assert_called_once_with('shell', 'command')
        close.assert_called_once_with('shell')

    def test_direct_transport_always_closes_shell_after_command_or_output_failure(self):
        for stage in ('run_command', 'get_command_output', 'cleanup_command'):
            with self.subTest(stage=stage):
                session = Mock()
                protocol = session.protocol
                protocol.open_shell.return_value = 'shell'
                protocol.run_command.return_value = 'command'
                protocol.get_command_output.return_value = (b'', b'', 0)
                getattr(protocol, stage).side_effect = RuntimeError('transport failure')
                with self.assertRaises(RuntimeError):
                    management.run_powershell(session, "Write-Output 'test'")
                protocol.close_shell.assert_called_once_with('shell')
                if stage == 'run_command':
                    protocol.cleanup_command.assert_not_called()
                else:
                    protocol.cleanup_command.assert_called_once_with('shell', 'command')
                protocol.run_command.assert_called_once()

    def test_oversized_direct_command_is_rejected_before_opening_a_shell(self):
        session = Mock()
        with self.assertRaisesRegex(management.ManagementBlocked, 'transport limit'):
            management.run_powershell(session, '#' * 12_000)
        session.protocol.open_shell.assert_not_called()

    def test_transport_error_is_actionable_without_exposing_raw_stderr(self):
        for stdout, stderr, expected in (
            (b'', b'The command line is too long.\r\nprivate-value', 'command length'),
            (b'', b'#< CLIXML\r\nParserError private-value', 'PowerShell parser'),
            (b'', b'private-value', 'exit code 1; stdout=0 bytes; stderr=13 bytes'),
            (b'\xef\xbb\xbfWSLPE_OPERATOR_ERROR=Wrong standalone guest\n', b'private-value', 'Wrong standalone guest'),
        ):
            session = Mock()
            session.protocol.get_command_output.return_value = (stdout, stderr, 1)
            with self.assertRaises(management.ManagementBlocked) as raised:
                management.invoke(session, 'Inspect')
            self.assertIn(expected, str(raised.exception))
            self.assertNotIn('private-value', str(raised.exception))

    def test_open_forbidden_socket_fails_and_route_failure_is_not_denial(self):
        for error in (None, OSError(errno.EADDRNOTAVAIL, 'no source'),
                      OSError(errno.ENETUNREACH, 'no route')):
            sock = MagicMock()
            sock.__enter__.return_value = sock
            sock.connect.side_effect = error
            with patch.object(management.socket, 'socket', return_value=sock):
                with self.assertRaises(management.ManagementBlocked):
                    management.deny_probe(management.ADDRESS, 5986, '10.4.10.254')
        for error in (TimeoutError(), ConnectionRefusedError(errno.ECONNREFUSED, 'closed')):
            sock = MagicMock()
            sock.__enter__.return_value = sock
            sock.connect.side_effect = error
            with patch.object(management.socket, 'socket', return_value=sock):
                management.deny_probe(management.ADDRESS, 5986, '10.4.10.254')
            sock.bind.assert_called_once_with(('10.4.10.254', 0))

    def test_negative_tests_only_contact_wslpe_never_north(self):
        interfaces = [{'ifname': interface, 'addr_info': [{'family': 'inet', 'local': address}]}
                      for interface, address in [('vmnet3', '172.28.232.254'),
                                                 ('vmnet4', management.SOURCE),
                                                 ('vmnet8', '192.168.213.1'),
                                                 ('vmnet10', '10.4.10.254')]]
        with (patch.object(management, 'command', return_value=json.dumps(interfaces)),
              patch.object(management, 'deny_probe') as probe):
            management.negative_probes('192.168.213.249')
        self.assertEqual(probe.call_count, 7)
        self.assertTrue(all(c.args[0] in {management.ADDRESS, management.LEARNER, '192.168.213.249'}
                            for c in probe.call_args_list))
        self.assertIn(((management.ADDRESS, 5986, '10.4.10.254'),), probe.call_args_list)
        with patch.object(management, 'command', return_value='[]'):
            with self.assertRaisesRegex(management.ManagementBlocked, 'source addresses unavailable'):
                management.negative_probes('192.168.213.249')

    def test_fresh_apply_console_precedes_creation_and_auth_precedes_hardening(self):
        events = []
        def invoke(session, mode, **kwargs):
            events.append(mode)
            return self.data if mode == 'Inspect' else None
        with (patch.object(management, 'exact_target', return_value=self.target),
              patch.object(management, 'operator_secret', return_value='private'),
              patch.object(management, 'receipt_path', return_value=self.path),
              patch.object(management, 'auth_helper'),
              patch.object(management, 'command', return_value='22 (guest) => 2222 (host)\n5985 (guest) => 55985 (host)\n5986 (guest) => 55986 (host)\n'),
              patch.object(management, 'bootstrap_session', side_effect=lambda port: nullcontext('bootstrap')),
              patch.object(management, 'operator_session', side_effect=lambda *a, **kw: nullcontext('operator')),
              patch.object(management, 'invoke', side_effect=invoke),
              patch.object(management, '_console', side_effect=lambda *a: events.append('console')),
              patch.object(management, 'create_operator', side_effect=lambda *a: events.append('create')),
              patch.object(management, 'prove_operator', side_effect=lambda *a, **kw: events.append('authenticate') or self.data),
              patch.object(management, 'negative_probes', side_effect=lambda *a: events.append('negatives'))):
            management.run(apply=True, report=Mock())
        self.assertLess(events.index('console'), events.index('create'))
        self.assertLess(events.index('create'), events.index('authenticate'))
        self.assertLess(events.index('authenticate'), events.index('Harden'))
        self.assertGreater(events.index('negatives'), events.index('Harden'))
        self.assertEqual(json.loads(self.path.read_text())['phase'], 'accepted')

    def test_existing_authenticated_operator_resumes_without_foundation_or_bootstrap(self):
        management.save_receipt(self.path, self.receipt)
        with (patch.object(management, 'exact_target', return_value=self.target),
              patch.object(management, 'operator_secret', return_value='private'),
              patch.object(management, 'receipt_path', return_value=self.path),
              patch.object(management, 'auth_helper'),
              patch.object(management, 'prove_operator', return_value=self.data),
              patch.object(management, '_finish') as finish,
              patch.object(management, 'create_operator') as create,
              patch.object(management, 'bootstrap_session') as bootstrap):
            management.run(apply=True, report=Mock())
        finish.assert_called_once()
        create.assert_not_called()
        bootstrap.assert_not_called()

    def test_failed_authentication_cannot_reach_final_restriction(self):
        with (patch.object(management, 'exact_target', return_value=self.target),
              patch.object(management, 'operator_session', side_effect=ssl.SSLError('TLS failure')),
              patch.object(management, 'invoke') as mutation,
              patch.object(management, 'save_receipt') as save):
            with self.assertRaises(ssl.SSLError):
                management._finish(self.target, Mock(), self.certificate, 'pw', self.receipt, Mock(), Mock())
        mutation.assert_not_called()
        save.assert_not_called()

    def test_creation_calls_only_existing_foundation_without_secrets_in_argv(self):
        with (patch('kingdoms.wslpe_license_maintenance._approved_inventory',
                    return_value=(self.directory / 'inventory', self.directory / 'defaults')),
              patch.object(management, 'learner_password', return_value='different-private-learner'),
              patch.object(management.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run):
            management.create_operator(self.target, 55985, 'private-operator-password')
        args = run.call_args.args[0]
        self.assertIn(str(management.ROOT / 'ansible/wslpe-operator-foundation.yml'), args)
        self.assertNotIn('private-operator-password', ' '.join(args))
        self.assertEqual(run.call_args.kwargs['env']['KINGDOMS_WSLPE_OPERATOR_PASSWORD'], 'private-operator-password')
        overrides = json.loads(args[-1])
        self.assertEqual(overrides['ansible_host'], '127.0.0.1')
        self.assertEqual(overrides['ansible_winrm_message_encryption'], 'always')


class LocalTLSIntegrationTests(unittest.TestCase):
    """Real local TLS handshakes; no Windows or VM/network mutation."""

    def handshake(self, *, dns_name='WSLPE-WS01', expired=False, wrong_pin=False):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.datetime.now(datetime.timezone.utc)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, dns_name)])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(days=2))
                .not_valid_after(now + datetime.timedelta(days=-1 if expired else 1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(dns_name)]), critical=False)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .sign(key, hashes.SHA256()))
        der = cert.public_bytes(serialization.Encoding.DER)
        with tempfile.TemporaryDirectory() as folder:
            certificate_path = Path(folder) / 'public.pem'
            key_path = Path(folder) / 'key.pem'
            certificate_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                                   serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
            key_path.chmod(0o600)
            server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server.load_cert_chain(certificate_path, key_path)
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                listener.listen(1)
                listener.settimeout(5)
                def serve():
                    try:
                        connection, _ = listener.accept()
                        with connection, server.wrap_socket(connection, server_side=True):
                            pass
                    except (OSError, ssl.SSLError):
                        pass  # Expected when client rejects expiry/name.
                worker = threading.Thread(target=serve)
                worker.start()
                audit = management.auth_helper().tls_audit_module()
                try:
                    with patch.object(audit, 'PORT', listener.getsockname()[1]):
                        return audit.verify_pinned_tls('127.0.0.1', der,
                            '0' * 40 if wrong_pin else hashlib.sha1(der).hexdigest().upper())
                finally:
                    worker.join(timeout=6)

    def test_real_pinned_tls_accepts_exact_hostname_san(self):
        self.assertIn(self.handshake()['tls_version'], ('TLSv1.2', 'TLSv1.3'))

    def test_real_pinned_tls_rejects_wrong_hostname_expiry_and_pin(self):
        for kwargs in ({'dns_name': 'OTHER-WS01'}, {'expired': True}, {'wrong_pin': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ssl.SSLError, ValueError)):
                self.handshake(**kwargs)


if __name__ == '__main__':
    unittest.main()
