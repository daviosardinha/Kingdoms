"""Offline-only isolated three-network Course 1 VMware/router artifact regression."""
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from goad import course1_vmware_candidate as candidate
from goad.course1_network_plan import REFERENCE_ROUTER, REFERENCE_VAGRANT
from goad.course1_runtime_contract import ProfileNotReady

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / "docs/course1-network-candidate.example.json"


def load_plan():
    return json.loads(PROPOSAL.read_text(encoding="utf-8"))


class VmwareCandidateTests(unittest.TestCase):
    def render(self):
        return candidate.render_candidate(load_plan())

    def test_renders_four_windows_one_router_without_essos(self):
        artifacts = self.render()
        recipe = artifacts["providers/vmware/Vagrantfile"]
        vagrant = artifacts["instance-preview/Vagrantfile"]
        self.assertEqual(recipe.count(':name => "GOAD-'), 5)
        self.assertEqual(vagrant.count(':name => "GOAD-'), 5)
        for forbidden in ("GOAD-DC03", "GOAD-SRV03", "ESSOS", "vmnet30", "10.4."):
            self.assertNotIn(forbidden, recipe)
            self.assertNotIn(forbidden, vagrant)
            self.assertNotIn(forbidden, artifacts["router/provision.sh"])

    def test_all_four_guest_addresses_follow_candidate(self):
        vagrant = self.render()["instance-preview/Vagrantfile"]
        for expected in ("10.41.20.10", "10.41.10.11",
                         "10.41.10.22", "10.41.10.31"):
            self.assertIn(f':ip => "{expected}"', vagrant)
        self.assertEqual(vagrant.count(':lab_gateway => "10.41.10.1"'), 3)
        self.assertIn(':lab_gateway => "10.41.20.1"', vagrant)
        self.assertEqual(vagrant.count('vmnet11'), 4)  # 3 NORTH + router
        self.assertEqual(vagrant.count('vmnet12'), 2)
        self.assertEqual(vagrant.count('vmnet13'), 1)

    def test_router_has_exactly_three_explicit_nics_and_no_essos(self):
        data = self.render()["providers/vmware/Vagrantfile"]
        router = data.split(':name => "GOAD-ROUTER"', 1)[1]
        self.assertIn('"ethernet3.pcislotnumber" => "1184"', router)
        self.assertNotIn('"ethernet4.pcislotnumber"', router)
        self.assertIn(':slot => 1, :vnet => "vmnet11"', router)
        self.assertIn(':slot => 2, :vnet => "vmnet12"', router)
        self.assertIn(':slot => 3, :vnet => "vmnet13"', router)
        self.assertNotIn(':slot => 4', router)
        self.assertIn('"../router/provision.sh"', router)

    def test_router_script_binds_these_gateway_identities(self):
        content = self.render()["router/provision.sh"]
        for ip in ("10.41.10.1", "10.41.20.1", "10.41.99.1"):
            self.assertIn(ip, content)
        for mac in ("00:50:56:3b:10:01", "00:50:56:3b:20:01",
                    "00:50:56:3b:99:01"):
            self.assertIn(mac, content)
        self.assertEqual(content.count('configure_lab_interface "'), 3)
        self.assertIn("kingdoms-course1-router", content)
        self.assertNotIn("goad-router", content)

    def test_router_status_lines_handle_padded_zone_labels(self):
        content = self.render()["router/provision.sh"]
        expected = {
            "NORTH": "10.41.10.1",
            "SEVENKINGDOMS": "10.41.20.1",
            "MANAGEMENT": "10.41.99.1",
        }
        status_lines = [line for line in content.splitlines()
                        if line.startswith("printf ") and '/24"' in line]
        self.assertEqual(len(status_lines), 3)
        for zone, gateway in expected.items():
            matches = [line for line in status_lines
                       if f"    {zone} " in line]
            with self.subTest(zone=zone):
                self.assertEqual(len(matches), 1)
                self.assertTrue(matches[0].endswith(f'{gateway}/24"'))

    def test_router_default_forward_is_deny(self):
        content = self.render()["router/provision.sh"]
        self.assertIn("type filter hook forward priority 0;\n        policy drop;", content)
        self.assertEqual(content.count("policy drop;"), 1)
        self.assertIn("NONDEPLOYABLE", content)
        self.assertNotIn("provisioning allow-forward policy", content)

    def test_existing_legacy_router_and_vagrant_source_unchanged(self):
        originals = (REFERENCE_ROUTER.read_bytes(), REFERENCE_VAGRANT.read_bytes())
        self.render()
        self.assertEqual(originals,
                         (REFERENCE_ROUTER.read_bytes(), REFERENCE_VAGRANT.read_bytes()))

    def test_manifest_explicitly_disallows_installation(self):
        artifacts = self.render()
        self.assertEqual(set(artifacts),
                         {"providers/vmware/Vagrantfile", "instance-preview/Vagrantfile",
                          "router/provision.sh", "manifest.json",
                          "data/config.json", "data/inventory",
                          "data/inventory_disable_vagrant", "providers/vmware/inventory",
                          "vagrant/Install-WMF3Hotfix.ps1",
                          "vagrant/ConfigureRemotingForAnsible.ps1",
                          "vagrant/fix_ip.ps1"})
        manifest = json.loads(artifacts["manifest.json"])
        self.assertEqual(manifest["state"], "PREVIEW_ONLY_NOT_INSTALLABLE")
        self.assertEqual(manifest["zones"], ["NORTH", "SEVENKINGDOMS", "MANAGEMENT"])
        self.assertFalse(manifest["deployment_authorized"])
        self.assertIn("data/config.json", artifacts)
        self.assertNotIn("10.4.10.11", artifacts["providers/vmware/inventory"])

    def test_translated_inventory_addresses_and_gateway(self):
        artifacts = self.render()
        for name in ("data/inventory_disable_vagrant", "providers/vmware/inventory"):
            with self.subTest(filename=name):
                content = artifacts[name]
                for host, ip in (("dc01", "10.41.20.10"),
                                 ("dc02", "10.41.10.11"),
                                 ("srv02", "10.41.10.22"),
                                 ("ws01", "10.41.10.31")):
                    self.assertIn(f"{host} ansible_host={ip}", content)
                self.assertNotIn("10.4.", content)
                self.assertNotIn("vmnet10", content)
        provider = artifacts["providers/vmware/inventory"]
        self.assertIn("lab_gateway=10.41.10.1", provider)
        self.assertIn("vmnet11", provider)
        self.assertIn("vmnet12", provider)

    def test_course1_ad_config_still_has_only_two_domains(self):
        config = json.loads(self.render()["data/config.json"])
        self.assertEqual(set(config["lab"]["domains"]),
                         {"sevenkingdoms.local", "north.sevenkingdoms.local"})
        self.assertEqual(set(config["lab"]["hosts"]), {"dc01", "dc02", "srv02", "ws01"})

    def test_missing_host_in_inventory_fails_closed(self):
        from goad.course1_inventory_candidate import render_candidate_inventories
        from goad.course1_source_gate import _generator_render
        source = _generator_render()
        source["providers/vmware/inventory"] = source[
            "providers/vmware/inventory"
        ].replace("ws01 ansible_host=", "unknown ansible_host=")
        with self.assertRaises(ProfileNotReady):
            render_candidate_inventories(source, load_plan())

    def test_wrong_source_management_ip_fails_closed(self):
        from goad.course1_inventory_candidate import render_candidate_inventories
        from goad.course1_source_gate import _generator_render
        source = _generator_render()
        source["data/inventory_disable_vagrant"] = source[
            "data/inventory_disable_vagrant"
        ].replace("10.4.20.10", "10.4.20.200")
        with self.assertRaises(ProfileNotReady):
            render_candidate_inventories(source, load_plan())

    def test_private_windows_provisioner_paths_resolve_inside_bundle(self):
        artifacts = self.render()
        outer = artifacts["instance-preview/Vagrantfile"]
        expected = (
            "Install-WMF3Hotfix.ps1",
            "ConfigureRemotingForAnsible.ps1",
            "fix_ip.ps1",
        )
        self.assertNotIn("../../../vagrant/", outer)
        for name in expected:
            with self.subTest(name=name):
                self.assertIn(f'../vagrant/{name}', outer)
                self.assertIn("vagrant/" + name, artifacts)
        manifest = json.loads(artifacts["manifest.json"])
        self.assertEqual(set(manifest["generated_files"]),
                         set(artifacts) - {"manifest.json"})

    def test_windows_route_targets_isolated_parent_and_north(self):
        powershell = self.render()["vagrant/fix_ip.ps1"]
        self.assertIn("10.41.0.0/16", powershell)
        self.assertIn("route.exe -p ADD 10.41.0.0", powershell)
        self.assertIn('route.exe PRINT 10.41.0.0', powershell)
        self.assertNotIn("10.4.0.0", powershell)

    def test_canonical_windows_provisioner_is_unchanged(self):
        reference = ROOT / "vagrant/fix_ip.ps1"
        before = reference.read_bytes()
        self.render()
        self.assertEqual(before, reference.read_bytes())
        self.assertIn(b"10.4.0.0", before)

    def test_candidate_mutated_into_reference_ip_is_rejected(self):
        plan = load_plan()
        plan["machines"]["GOAD-WS01"]["ip"] = "10.4.10.31"
        with self.assertRaises(ProfileNotReady):
            candidate.render_candidate(plan)

    def test_reference_vmnet_reuse_is_rejected(self):
        plan = load_plan()
        plan["zones"]["NORTH"]["vmnet"] = "vmnet10"
        with self.assertRaises(ProfileNotReady):
            candidate.render_candidate(plan)

    def test_extra_essos_zone_is_rejected(self):
        plan = load_plan()
        plan["zones"]["ESSOS_TRANSITION"] = {
            "vmnet": "vmnet43", "subnet": "10.41.30.0/24",
            "gateway": "10.41.30.1"
        }
        with self.assertRaises(ProfileNotReady):
            candidate.render_candidate(plan)

    def test_source_output_path_must_be_private_and_outside_git(self):
        with self.assertRaises(ProfileNotReady):
            candidate._output_dir(ROOT / "workspace/course1-test")
        with self.assertRaises(ProfileNotReady):
            candidate._output_dir(ROOT / "docs/course1-output")
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / "workspace" / "course1-test"
            with self.assertRaises(ProfileNotReady):
                candidate._output_dir(directory)

    def test_cli_can_only_generate_noninstallable_files(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "rendered"
            cmd = [sys.executable, "-m", "goad.course1_vmware_candidate",
                   "--proposal", str(PROPOSAL), "--output", str(out)]
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[BLOCKED]", result.stdout)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o700)
            for path in out.rglob("*"):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode),
                                 0o700 if path.is_dir() else 0o600)
            self.assertEqual(len([p for p in out.rglob("*") if p.is_file()]), 11)
            self.assertFalse(json.loads(
                (out / "manifest.json").read_text())["deployment_authorized"])
            second = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("refuses overwrite", second.stderr)

    def test_vagrantfile_has_first_statement_activation_guard(self):
        vagrant = self.render()["instance-preview/Vagrantfile"]
        first_line = vagrant.splitlines()[0]
        self.assertEqual(
            first_line,
            "raise 'KINGDOMS_COURSE1_PREVIEW_NOT_INSTALLABLE: deployment blocked'",
        )
        self.assertIn("config.vm.define box[:name]", vagrant)
        self.assertIn("GOAD-ROUTER", vagrant)

    @unittest.skipUnless(shutil.which("ruby"), "ruby not installed")
    def test_generated_ruby_instance_syntax(self):
        text = self.render()["instance-preview/Vagrantfile"]
        r = subprocess.run(["ruby", "-c"], input=text, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Syntax OK", r.stdout)

    def test_generated_router_bash_syntax(self):
        text = self.render()["router/provision.sh"]
        result = subprocess.run(["bash", "-n"], input=text,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_candidate_only_module_never_executes_hypervisor_commands(self):
        source = Path(candidate.__file__).read_text(encoding="utf-8")
        for token in ("subprocess", "vmrun", "vagrant up",
                      "ansible-playbook", "os.system", "systemctl restart"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
