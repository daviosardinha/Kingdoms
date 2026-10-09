"""Guard against losing patched Kingdoms improvements in derived labs."""
import json
import tempfile
import unittest
from pathlib import Path

from goad.kingdoms_foundation import (
    FOUNDATION_ID, KINGDOMS_REFERENCE_RECIPE, PROTECTIONS, PROJECT_ROOT,
    KingdomsFoundationError, reference_recipe, validate_foundation,
)
from goad.course1_source_gate import _generator_render
from goad.course1_vmware_candidate import render_candidate
from tests.test_course1_network_plan import proposal


class KingdomsFoundationTests(unittest.TestCase):
    def test_existing_patched_kingdoms_base_is_valid(self):
        report = validate_foundation()
        self.assertEqual(report["foundation"], FOUNDATION_ID)
        self.assertEqual(report["authority"], "kingdoms-patched-repository")
        self.assertFalse(report["upstream_goad_configuration_allowed"])
        self.assertFalse(report["course_install_authorized"])
        self.assertEqual(report["verified_files"], len(PROTECTIONS))
        self.assertEqual(
            report["verified_protections"],
            sum(len(v) for v in PROTECTIONS.values()),
        )

    def test_reference_recipe_is_internal_kingdoms_patched_copy(self):
        self.assertEqual(KINGDOMS_REFERENCE_RECIPE.as_posix(), "ad/GOAD")
        self.assertEqual(reference_recipe(), PROJECT_ROOT / "ad/GOAD")
        # The legacy folder name is retained to keep the existing reference
        # installation working, not to select or download upstream GOAD.
        script = (PROJECT_ROOT / "scripts/course1/generate-profile.py").read_text()
        self.assertIn("SOURCE = reference_recipe(ROOT)", script)
        self.assertIn("validate_foundation(ROOT)", script)
        self.assertNotIn("SOURCE = ROOT / \"ad\" / \"GOAD\"", script)

    def test_removing_any_patched_protection_refuses_course_derivation(self):
        sources = {path: (PROJECT_ROOT / path).read_text(encoding="utf-8")
                   for path in PROTECTIONS}
        for path, rules in PROTECTIONS.items():
            for feature, marker in rules:
                with self.subTest(path=path, feature=feature):
                    self.assertIn(marker, sources[path])
                    altered = sources[path].replace(marker, "REMOVED_" + feature, 1)
                    self.assertNotEqual(altered, sources[path])

                    def modified_reader(key):
                        return altered if key == path else sources[key]

                    with self.assertRaisesRegex(KingdomsFoundationError, feature):
                        validate_foundation(reader=modified_reader)

    def test_course_artifacts_bind_to_the_kingdoms_foundation(self):
        preview = _generator_render()
        manifest = json.loads(preview["manifest.json"])
        self.assertEqual(manifest["kingdoms_foundation"], FOUNDATION_ID)
        candidate = render_candidate(proposal())
        actual = json.loads(candidate["manifest.json"])
        self.assertEqual(actual["kingdoms_foundation"], FOUNDATION_ID)
        self.assertFalse(actual["deployment_authorized"])

    def test_future_course_requires_explicit_foundation_identity(self):
        from goad.course_catalog import course_manifest, CourseCatalogError
        from unittest.mock import patch
        from goad.goadpath import GoadPath

        with tempfile.TemporaryDirectory(prefix="kingdoms-base-") as d:
            folder = Path(d) / "COURSE2"
            (folder / "providers/vmware").mkdir(parents=True)
            manifest = {
                "lab": "COURSE2", "title": "Future Course",
                "runtime_profile": "future-course",
                "state": "PREVIEW_ONLY_NOT_INSTALLABLE",
                "providers": {"vmware": "preview"},
            }
            with patch.object(GoadPath, "get_lab_path",
                              return_value=str(folder)):
                (folder / "course.json").write_text(json.dumps(manifest))
                with self.assertRaisesRegex(CourseCatalogError, "patched Kingdoms"):
                    course_manifest("COURSE2")
                manifest["kingdoms_foundation"] = FOUNDATION_ID
                (folder / "course.json").write_text(json.dumps(manifest))
                self.assertEqual(
                    course_manifest("COURSE2")["kingdoms_foundation"], FOUNDATION_ID
                )


if __name__ == "__main__":
    unittest.main()
