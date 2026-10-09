"""Pure lifecycle dependency contracts, no VM/process/network actions."""
import unittest

from goad.course1_runtime_contract import (
    COURSE1, FULL, COURSE1_WINDOWS, FULL_WINDOWS, ROUTER,
    ProfileNotReady, examine_profile_manifest,
)


class Course1RuntimeContractTests(unittest.TestCase):
    def test_legacy_six_machine_roster_unchanged(self):
        self.assertEqual(len(FULL.windows), 6)
        self.assertEqual(FULL.windows, FULL_WINDOWS)
        self.assertIn("GOAD-DC03", FULL.windows)
        self.assertIn("GOAD-SRV03", FULL.windows)

    def test_reduced_four_machine_roster(self):
        self.assertEqual(COURSE1.windows, COURSE1_WINDOWS)
        self.assertEqual(len(COURSE1.windows), 4)
        self.assertNotIn("GOAD-DC03", COURSE1.windows)
        self.assertNotIn("GOAD-SRV03", COURSE1.windows)

    def test_transitive_start_order_and_root_time_dependency(self):
        self.assertEqual(COURSE1.requested_start(), COURSE1_WINDOWS)
        self.assertEqual(COURSE1.requested_start("GOAD-DC02"),
                         ("GOAD-DC01", "GOAD-DC02"))
        self.assertEqual(COURSE1.requested_start("GOAD-SRV02"),
                         ("GOAD-DC01", "GOAD-DC02", "GOAD-SRV02"))
        self.assertEqual(COURSE1.requested_start("GOAD-WS01"),
                         ("GOAD-DC01", "GOAD-DC02", "GOAD-WS01"))
        self.assertEqual(COURSE1.requested_start(ROUTER), ())

    def test_stop_members_before_domain_controllers(self):
        ordered = COURSE1.ordered_stop()
        self.assertEqual(ordered[:2], ("GOAD-WS01", "GOAD-SRV02"))
        self.assertEqual(ordered[-2:], ("GOAD-DC02", "GOAD-DC01"))

    def test_no_essos_machine_in_course1(self):
        with self.assertRaises(ProfileNotReady):
            COURSE1.requested_start("GOAD-SRV03")
        with self.assertRaises(ProfileNotReady):
            COURSE1.requested_start("GOAD-DC03")

    def test_preview_cannot_be_mistaken_for_installable_profile(self):
        with self.assertRaisesRegex(ProfileNotReady, "source preview"):
            examine_profile_manifest({
                "profile": COURSE1.name,
                "state": "PREVIEW_ONLY_NOT_INSTALLABLE",
                "windows_machines": list(COURSE1_WINDOWS),
            })

    def test_fake_approved_course1_marker_still_rejected(self):
        with self.assertRaisesRegex(ProfileNotReady, "activation"):
            examine_profile_manifest({
                "profile": COURSE1.name,
                "state": "ACTIVE_LEGACY",
                "windows_machines": list(COURSE1_WINDOWS),
            })

    def test_explicit_legacy_manifest_only(self):
        resolved = examine_profile_manifest({
            "profile": FULL.name,
            "state": "ACTIVE_LEGACY",
            "windows_machines": list(FULL_WINDOWS),
        })
        self.assertIs(resolved, FULL)
        with self.assertRaises(ProfileNotReady):
            examine_profile_manifest({
                "profile": FULL.name,
                "state": "ACTIVE_LEGACY",
                "windows_machines": list(COURSE1_WINDOWS),
            })
        with self.assertRaises(ProfileNotReady):
            examine_profile_manifest(None)


if __name__ == "__main__":
    unittest.main()
