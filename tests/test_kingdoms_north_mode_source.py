"""NORTH router policy and host-route source integration (offline, no VM changes)."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from goad.kingdoms_vmware_profile import ROOT

NORTH = ROOT / "ad/NORTH/providers/vmware/router"
ROUTES = ROOT / "scripts/course1/provisioning-routes.sh"
SSH = ROOT / "scripts/course1/router-ssh.sh"
PROVIDER_SOURCE = ROOT / "goad/provider/vagrant/vmware_nomad.py"


class KingdomsNorthModeSourceTests(unittest.TestCase):
    def test_north_nft_provisioning_exercise_modes_are_present(self):
        for state in ("provisioning", "exercise"):
            self.assertTrue((NORTH / "nftables" / (state + ".nft")).is_file())

    def test_native_router_bootstrap_matches_both_mode_policy_tables(self):
        bootstrap = (NORTH / "provision.sh").read_text()
        self.assertIn("table inet kingdoms_north", bootstrap)
        self.assertNotIn("table inet goad_nomad", bootstrap)
        for state in ("provisioning", "exercise"):
            policy = (NORTH / "nftables" / (state + ".nft")).read_text()
            self.assertIn("table inet kingdoms_north", policy)
        from goad.course1_vmware_candidate import render_candidate
        from tests.test_course1_network_plan import proposal
        staged = render_candidate(proposal())["router/provision.sh"]
        self.assertIn("table inet kingdoms_north", staged)

    def test_exercise_default_deny_with_only_parent_child_dc(self):
        data = (NORTH / "nftables/exercise.nft").read_text()
        self.assertIn("policy drop;", data)
        self.assertIn("ct state established,related", data)
        self.assertIn("ip saddr 10.41.10.11 ip daddr 10.41.20.10", data)
        self.assertIn("ip saddr 10.41.20.10 ip daddr 10.41.10.11", data)
        self.assertEqual(data.count("ip saddr "), 2)
        for forbidden in ("10.4.", "vmnet30", "essos", "10.41.99.254"):
            self.assertNotIn(forbidden, data.lower())

    def test_provisioning_is_temporary_and_distinct_from_exercise(self):
        data = (NORTH / "nftables/provisioning.nft").read_text()
        self.assertIn("table inet kingdoms_north", data)
        self.assertIn("policy accept;", data)
        self.assertNotIn("policy drop;", data)
        self.assertIn("table inet kingdoms_north",
                      (NORTH / "nftables/exercise.nft").read_text())

    def test_router_ssh_and_host_route_shell_syntax(self):
        for item in (ROUTES, SSH):
            with self.subTest(file=str(item)):
                result = subprocess.run(
                    ["bash", "-n", str(item)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_host_route_is_strictly_parent_via_north_router(self):
        source = ROUTES.read_text()
        self.assertIn("PARENT_NET=10.41.20.0/24", source)
        self.assertIn("NORTH_IF=vmnet11", source)
        self.assertIn("ROUTER_NORTH=10.41.10.1", source)
        self.assertIn("kingdoms-north-vmnet-hostaddrs", source)
        self.assertIn("refusing to overwrite foreign route", source)
        self.assertIn("refusing to remove foreign route", source)
        self.assertNotIn("10.4.", source)
        self.assertNotRegex(source, r"ip[ \t].*route.*(?:10\.4\.|vmnet(?:10|20|30|99))")

    def test_host_route_status_is_readonly(self):
        with tempfile.TemporaryDirectory(prefix="kingdoms-north-route-") as folder:
            fake = Path(folder) / "ip"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$*\" = '-4 route show exact 10.41.20.0/24' ]; then\n"
                "  echo '10.41.20.0/24 via 10.41.10.1 dev vmnet11'\n"
                "  exit 0\n"
                "fi\n"
                "echo 'unexpected ip mutation' >&2\n"
                "exit 17\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            result = subprocess.run(
                ["bash", str(ROUTES), "status"],
                env={**os.environ, "PATH": folder + ":" + os.environ["PATH"]},
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("10.41.20.0/24 via 10.41.10.1 dev vmnet11",
                          result.stdout)

    def test_router_ssh_refuses_unbound_instances_before_ssh(self):
        with tempfile.TemporaryDirectory(prefix="kingdoms-north-router-") as folder:
            result = subprocess.run(
                ["bash", str(SSH), "true"],
                env={**os.environ, "GOAD_PROVIDER_DIR": folder},
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("provider missing/unsafe", result.stderr)

    def test_provider_selects_profile_helpers_but_blocks_north_live_change(self):
        source = PROVIDER_SOURCE.read_text()
        self.assertIn("if self.lab_name == 'NORTH':", source)
        self.assertIn("'router-ssh.sh': 'course1/router-ssh.sh'", source)
        self.assertIn("'provisioning-routes.sh': 'course1/provisioning-routes.sh'",
                      source)
        self.assertIn("self.lab_name if self.lab_name == 'NORTH' else 'GOAD'", source)
        self.assertEqual(source.count("not binding.segmented_install_enabled"), 2)
        self.assertIn("if self.lab_name == 'GOAD':", source)
        self.assertIn("binding.segmented_install_enabled", source)
        # No route/policy call is executed by this test.

    def test_shared_mode_controller_north_profile_is_four_guest_and_scoped(self):
        import subprocess
        controller = ROOT / "scripts/lab-mode.sh"
        result = subprocess.run(
            ["bash", str(controller), "--describe-profile"],
            env={**os.environ, "KINGDOMS_VMWARE_LAB": "NORTH"},
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("windows=GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01", result.stdout)
        self.assertIn("domain_controllers=GOAD-DC01 GOAD-DC02", result.stdout)
        self.assertIn("members=GOAD-SRV02 GOAD-WS01", result.stdout)
        self.assertIn("/scripts/course1/provisioning-routes.sh", result.stdout)
        self.assertIn("/scripts/course1/router-ssh.sh", result.stdout)
        self.assertIn("/ad/NORTH/providers/vmware/router/nftables", result.stdout)
        self.assertIn("nftables_table=kingdoms_north", result.stdout)
        self.assertIn("deployment_authorized=false", result.stdout)
        self.assertNotIn("GOAD-DC03", result.stdout)
        self.assertNotIn("GOAD-SRV03", result.stdout)

    def test_shared_mode_controller_reference_profile_remains_six_guest(self):
        controller = ROOT / "scripts/lab-mode.sh"
        result = subprocess.run(
            ["bash", str(controller), "--describe-profile"],
            env={**os.environ, "KINGDOMS_VMWARE_LAB": "GOAD"},
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("windows=GOAD-DC01 GOAD-DC02 GOAD-DC03 GOAD-SRV02 GOAD-SRV03 GOAD-WS01", result.stdout)
        self.assertIn("nftables_table=goad_nomad", result.stdout)
        self.assertIn("/scripts/provisioning-routes.sh", result.stdout)
        self.assertIn("/scripts/router-ssh.sh", result.stdout)
        self.assertNotIn("/scripts/course1/router-ssh.sh", result.stdout)

    def test_shared_mode_controller_rejects_unknown_profile(self):
        proc = subprocess.run(
            ["bash", str(ROOT / "scripts/lab-mode.sh"), "--describe-profile"],
            env={**os.environ, "KINGDOMS_VMWARE_LAB": "ESSOS"},
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Unsupported Kingdoms VMware profile", proc.stderr)

    def test_north_mode_requires_explicit_provider_binding_before_operations(self):
        script = (ROOT / "scripts/lab-mode.sh").read_text()
        self.assertIn('NORTH requires explicit GOAD_PROVIDER_DIR; no auto-discovery', script)
        self.assertIn('NORTH provider is not bound to', script)
        self.assertIn('PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"', script)
        self.assertIn('python3 -m goad.course1_instance_binding --check-provider "${PROVIDER}"', script)
        # Exercise the real method without importing the VMware runtime:
        # a full import requires pywinrm, which is intentionally optional
        # for this source-only offline validation suite.
        import ast
        from types import SimpleNamespace
        provider_source = ROOT / "goad/provider/vagrant/vmware_nomad.py"
        tree = ast.parse(provider_source.read_text(encoding="utf-8"))
        provider_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "GoadNomadVmwareProvider"
        )
        method = next(
            node for node in provider_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "_provider_env"
        )
        namespace = {}
        exec(
            compile(ast.Module(body=[method], type_ignores=[]),
                    str(provider_source), "exec"),
            {"os": os}, namespace,
        )
        for lab in ("GOAD", "NORTH"):
            env = namespace["_provider_env"](
                SimpleNamespace(path="/tmp/mock-instance/provider", lab_name=lab)
            )
            self.assertEqual(env["KINGDOMS_VMWARE_LAB"], lab)
            self.assertEqual(env["GOAD_PROVIDER_DIR"], "/tmp/mock-instance/provider")

    def test_reference_scripts_and_policies_still_exist(self):
        self.assertTrue((ROOT / "scripts/provisioning-routes.sh").is_file())
        self.assertTrue((ROOT / "scripts/router-ssh.sh").is_file())
        for state in ("provisioning", "exercise"):
            self.assertTrue((
                ROOT / "ad/GOAD/providers/vmware/router/nftables" /
                (state + ".nft")
            ).is_file())


if __name__ == "__main__":
    unittest.main()
