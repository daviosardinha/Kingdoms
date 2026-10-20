"""Static coherent runtime artifact rendering for the existing Kingdoms engine."""
import unittest
from pathlib import Path

from goad.course1_artifact_render import (
    MAC_PATTERN, SOURCE_FILES, render_course1_artifacts,
)
from goad.kingdoms_topology import MANIFEST_PATH, load_course1_topology


class Course1RenderTests(unittest.TestCase):
    def test_default_is_byte_identical_to_kingdoms_derived_course1_templates(self):
        originals = MANIFEST_PATH.parent
        generated = render_course1_artifacts()
        self.assertEqual(set(generated), set(SOURCE_FILES))
        for path, body in generated.items():
            with self.subTest(path=path):
                self.assertEqual(body, (originals / path).read_text(encoding="utf-8"))

    def test_alternate_cidr_rendered_consistently_across_all_five_files(self):
        vmnets = {"north": 11, "sevenkingdoms": 21, "management": 98}
        generated = render_course1_artifacts("10.5.0.0/16", vmnets)
        layout = load_course1_topology("10.5.0.0/16", vmnets)
        vagrant = generated["providers/vmware/Vagrantfile"]
        router = generated["providers/vmware/router/provision.sh"]
        policy = generated["providers/vmware/router/nftables/exercise.nft"]
        for machine, host in layout["windows"].items():
            self.assertIn(f':name => "{machine}"', vagrant)
            self.assertIn(f':ip => "{host["address"]}"', vagrant)
        for segment in layout["segments"].values():
            self.assertIn(f'"{segment["gateway"]}"', router)
            self.assertIn(segment["vmnet"], vagrant)
        self.assertIn("10.5.10.11", policy)
        self.assertIn("10.5.20.10", policy)
        self.assertNotIn("10.4.10.", "\n".join(generated.values()))
        self.assertNotIn("vmnet30", "\n".join(generated.values()))

    def test_all_seven_default_macs_are_replaced_and_router_matches_vagrant(self):
        alt = render_course1_artifacts(
            "10.5.0.0/16", {"north": 11, "sevenkingdoms": 21, "management": 98}
        )
        old = set(MAC_PATTERN.findall(
            render_course1_artifacts()["providers/vmware/Vagrantfile"]))
        now = set(MAC_PATTERN.findall(alt["providers/vmware/Vagrantfile"]))
        router = set(MAC_PATTERN.findall(alt["providers/vmware/router/provision.sh"]))
        self.assertEqual(len(now), 7)
        self.assertTrue(now.isdisjoint(old))
        self.assertEqual(len(router), 3)
        self.assertTrue(router.issubset(now))

    def test_vmnet_change_alone_cannot_reuse_original_macs(self):
        changed = render_course1_artifacts(
            vmnets={"north": 11, "sevenkingdoms": 21, "management": 98}
        )
        old = set(MAC_PATTERN.findall(
            render_course1_artifacts()["providers/vmware/Vagrantfile"]))
        new = set(MAC_PATTERN.findall(changed["providers/vmware/Vagrantfile"]))
        self.assertTrue(old.isdisjoint(new))
        self.assertIn("10.4.10.11", changed["providers/vmware/Vagrantfile"])
        self.assertIn("vmnet11", changed["providers/vmware/Vagrantfile"])

    def test_renderer_does_not_write_any_runtime_or_host_files(self):
        path = Path(__file__).resolve().parents[1] / "goad/course1_artifact_render.py"
        source = path.read_text()
        for prohibited in (
            "subprocess.run(", "os.system(", ".write_text(",
            "vmware-networks", "vagrant up", "ip route replace"
        ):
            self.assertNotIn(prohibited, source)

    def test_foreign_subnet_without_independent_vmnets_fails(self):
        with self.assertRaisesRegex(ValueError, "explicit independent"):
            render_course1_artifacts("10.5.0.0/16")
        with self.assertRaisesRegex(ValueError, "may not reuse default"):
            render_course1_artifacts(
                "10.5.0.0/16", {"north": 10, "sevenkingdoms": 21, "management": 98}
            )


if __name__ == "__main__":
    unittest.main()
