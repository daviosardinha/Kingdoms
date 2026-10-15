"""Kingdoms operator-only course selector and legacy lifecycle isolation tests.

Runs entirely in Python without importing the hypervisor/Ansible stack.
"""
import ast
import types
import unittest
from pathlib import Path

from kingdoms.course_registry import COURSES, get_course, catalog_lines

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "goad_nomad.py").read_text(encoding="utf-8")


class StubLog:
    output = []

    @classmethod
    def info(cls, message):
        cls.output.append(("info", message))

    @classmethod
    def warning(cls, message):
        cls.output.append(("warning", message))

    @classmethod
    def error(cls, message):
        cls.output.append(("error", message))


class LegacyConsole:
    def onecmd(self, line):
        self.legacy_calls.append(line)
        return "LEGACY"

    def do_status(self, arg=""):
        self.legacy_calls.append("status")

    def do_help(self, arg=""):
        self.legacy_calls.append("help")


def load_unit(name):
    tree = ast.parse(SOURCE)
    node = next(
        x for x in tree.body
        if isinstance(x, (ast.ClassDef, ast.FunctionDef)) and x.name == name
    )
    scope = {
        "BaseGoad": LegacyConsole,
        "Log": StubLog,
        "COURSES": COURSES,
        "get_course": get_course,
        "catalog_lines": catalog_lines,
        "print_menu_title": lambda *args: None,
        "print_menu_entry": lambda *args: None,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(ROOT / "goad_nomad.py"), "exec"), scope)
    return scope[name]


OperatorConsole = load_unit("GoadNomad")
dispatch_task = load_unit("_dispatch_task")


class CourseRegistryTests(unittest.TestCase):
    def test_catalog_is_unique_and_non_deployable_courses_fail_closed(self):
        self.assertEqual([c.slug for c in COURSES], ["north", "course-2", "windows-lpe"])
        self.assertEqual(len({c.slug for c in COURSES}), len(COURSES))
        self.assertEqual(
            [(c.slug, c.lifecycle_ready) for c in COURSES],
            [("north", True), ("course-2", False), ("windows-lpe", False)],
        )
        self.assertEqual(get_course("fall-of-the-north").slug, "north")
        self.assertEqual(get_course("3").slug, "windows-lpe")
        self.assertIsNone(get_course("../outside"))
        self.assertIsNone(get_course("nonexistent"))

    def test_registry_is_operator_owned_not_learner_api(self):
        self.assertTrue(all(c.title for c in COURSES))
        self.assertTrue(all("[" in line and "]" in line for line in catalog_lines()))
        self.assertTrue(get_course("windows-lpe").standalone)
        self.assertEqual(get_course("north").legacy_lab, "GOAD")


class OperatorSelectionTests(unittest.TestCase):
    def setUp(self):
        StubLog.output = []
        self.console = OperatorConsole.__new__(OperatorConsole)
        self.console.legacy_calls = []
        self.console.lab_manager = types.SimpleNamespace(
            get_current_lab_name=lambda: "GOAD",
        )

    def test_windows_lpe_is_selectable_for_inspection_only(self):
        self.assertTrue(self.console._set_course_selection("windows-lpe"))
        self.assertEqual(self.console._selected_course, "windows-lpe")
        for command in (
            "install", "destroy", "destroy_vm target", "reset", "snapshot",
            "start", "stop", "mode provisioning", "ws01", "set_lab GOAD",
            "load instance-1", "provision_lab", "!id", "create", "provide",
        ):
            self.assertFalse(self.console.onecmd(command), command)
        self.assertEqual(self.console.legacy_calls, [])

    def test_unavailable_course_status_is_not_north_status(self):
        self.console.do_select_course("windows-lpe")
        self.console.do_status()
        self.assertEqual(self.console.legacy_calls, [])
        self.assertTrue(any("adapter pending" in str(line).lower() for line in StubLog.output))

    def test_interactive_course_selection_never_exits_command_loop(self):
        self.assertFalse(self.console.do_select_course("windows-lpe"))
        self.assertEqual(self.console._selected_course, "windows-lpe")
        self.assertFalse(self.console.do_select_course("north"))
        self.assertEqual(self.console._selected_course, "north")

    def test_course_switching_and_legacy_console_compatibility(self):
        self.console.do_select_course("windows-lpe")
        self.assertTrue(self.console._set_course_selection("north"))
        self.assertEqual(self.console.onecmd("start"), "LEGACY")
        self.assertEqual(self.console.legacy_calls, ["start"])

    def test_reject_north_selection_if_other_lab_is_configured(self):
        self.console.lab_manager.get_current_lab_name = lambda: "GOAD-Light"
        self.assertFalse(self.console._set_course_selection("north"))
        self.assertIsNone(getattr(self.console, "_selected_course", None))

    def test_unknown_selection_keeps_previous_guard(self):
        self.console.do_select_course("windows-lpe")
        self.assertFalse(self.console._set_course_selection("invalid-course"))
        self.assertEqual(self.console._selected_course, "windows-lpe")

    def test_no_course_selected_retains_legacy_command_dispatch(self):
        self.assertEqual(self.console.onecmd("install"), "LEGACY")
        self.assertEqual(self.console.legacy_calls, ["install"])


class NonInteractiveCourseGuardTests(unittest.TestCase):
    def setUp(self):
        StubLog.output = []
        self.calls = []
        self.console = types.SimpleNamespace(
            do_load=lambda *args: self.calls.append(("load", args)),
            do_install=lambda *args: self.calls.append(("install", args)) or False,
            do_courses=lambda *args: self.calls.append(("courses", args)),
        )

    @staticmethod
    def args(task, course, lab="GOAD", instance="existing"):
        return types.SimpleNamespace(
            task=task, course=course, lab=lab, instance=instance,
            run_playbook=None, ansible_only=None,
        )

    def test_all_windows_lpe_mutating_cli_actions_are_blocked_before_instance_load(self):
        for task in ("install", "start", "stop", "destroy", "reset", "snapshot", "validate", "mode", "ws01"):
            self.assertEqual(dispatch_task(self.console, self.args(task, "windows-lpe")), 1)
        self.assertEqual(self.calls, [])

    def test_course_listing_and_unavailable_course_status_are_read_only(self):
        self.assertEqual(dispatch_task(self.console, self.args("courses", "windows-lpe")), 0)
        self.assertEqual(dispatch_task(self.console, self.args("status", "windows-lpe")), 0)
        self.assertEqual(self.calls, [("courses", ())])

    def test_unrecognized_and_mismatched_cli_course_fail_closed(self):
        self.assertEqual(dispatch_task(self.console, self.args("install", "fake")), 1)
        self.assertEqual(dispatch_task(self.console, self.args("install", "north", lab="GOAD-Light")), 1)
        self.assertEqual(self.calls, [])

    def test_legacy_install_dispatch_is_unchanged_without_course_argument(self):
        self.assertEqual(
            dispatch_task(self.console, self.args("install", None, instance=None)), 1
        )
        self.assertEqual(self.calls, [("install", ("--non-interactive",))])

    def test_main_applies_explicit_course_before_repl(self):
        self.assertIn(
            "args.course is not None and not goad._set_course_selection(args.course)",
            SOURCE,
        )
        self.assertIn("parser.add_argument('-c', '--course'", SOURCE)
        self.assertIn("KINGDOMS | OPERATOR CONSOLE", SOURCE)


if __name__ == "__main__":
    unittest.main()
