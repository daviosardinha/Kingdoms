"""Kingdoms operator-only course selector and legacy lifecycle isolation tests.

Runs entirely in Python without importing the hypervisor/Ansible stack.
"""
import ast
import types
import unittest
from unittest.mock import patch
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
    def refresh_prompt(self):
        self.prompt = 'NORTH > '

    def onecmd(self, line):
        # Mirror cmd.Cmd's command/argument dispatch instead of treating
        # "resume --noninteractive" as an unknown legacy command. This keeps
        # the mock aligned with the real GoadNomad -> cmd.Cmd dispatch path.
        tokens = line.strip().split(maxsplit=1)
        command = tokens[0] if tokens else ""
        arg = tokens[1] if len(tokens) > 1 else ""
        if command in ("install", "resume"):
            selection = self._course_selection()
            if selection is not None and selection.slug == "windows-lpe":
                return getattr(self, "do_" + command)(arg)
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
    class FakeVmAdapter:
        def preflight(self):
            return types.SimpleNamespace(ready=True, checks=("PASS: mock-only preflight",))

        def vm_status(self):
            return types.SimpleNamespace(ready=True, checks=("INFO: mock-only status",))

        def create_guest(self, confirmed=False):
            return types.SimpleNamespace(
                ready=confirmed, checks=("PASS: mock-only guest creation",)
            )

    scope = {
        "WindowsLpeVmwareAdapter": FakeVmAdapter,
        "BaseGoad": LegacyConsole,
        "Log": StubLog,
        "COURSES": COURSES,
        "get_course": get_course,
        "catalog_lines": catalog_lines,
        "valid_prefix": lambda prefix: prefix == "172.28.231",
        "bootstrap_native_wslpe": lambda manager, prefix, confirmed=False: (
            manager.bootstrap_calls.append((prefix, confirmed)) or True
        ),
        "resume_existing_wslpe": lambda manager, confirmed=False: (
            manager.resume_calls.append(confirmed) or True
        ),
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
        self.assertEqual(get_course("windows-lpe").legacy_lab, "WSLPE")


class OperatorSelectionTests(unittest.TestCase):
    def setUp(self):
        StubLog.output = []
        self.console = OperatorConsole.__new__(OperatorConsole)
        self.console.legacy_calls = []
        self.active = {"lab": "GOAD", "instance": None}
        self.bootstrap_calls = []
        self.resume_calls = []
        self.console.lab_manager = types.SimpleNamespace(
            get_current_lab_name=lambda: self.active["lab"],
            get_current_instance=lambda: self.active["instance"],
            is_lab_exist=lambda lab: lab in {"GOAD", "WSLPE"},
            set_lab=lambda lab: self.active.__setitem__("lab", lab),
            bootstrap_calls=self.bootstrap_calls,
            resume_calls=self.resume_calls,
        )

    def test_windows_lpe_selection_allows_only_stage1_install(self):
        self.assertTrue(self.console._set_course_selection("windows-lpe"))
        self.assertEqual(self.console._selected_course, "windows-lpe")
        for command in (
            "destroy", "destroy_vm target", "reset", "snapshot",
            "start", "stop", "mode provisioning", "ws01", "set_lab GOAD",
            "load instance-1", "provision_lab", "!id", "create", "provide",
        ):
            self.assertFalse(self.console.onecmd(command), command)
        self.assertEqual(self.console.legacy_calls, [])

    def test_unavailable_course_status_is_not_north_status(self):
        self.console.do_select_course("windows-lpe")
        self.console.do_status()
        self.assertEqual(self.console.legacy_calls, [])
        self.assertTrue(any("course provisioning" in str(line).lower() for line in StubLog.output))

    def test_interactive_course_selection_never_exits_command_loop(self):
        self.assertFalse(self.console.do_select_course("windows-lpe"))
        self.assertEqual(self.console._selected_course, "windows-lpe")
        self.assertFalse(self.console.do_select_course("north"))
        self.assertEqual(self.console._selected_course, "north")

    def test_read_only_windows_lpe_backend_checks_keep_console_open(self):
        self.console.do_select_course("windows-lpe")
        self.assertFalse(self.console.do_course_preflight())
        self.assertFalse(self.console.do_course_vm_status())
        self.assertEqual(self.console.legacy_calls, [])
        self.assertTrue(any("mock-only preflight" in x[1] for x in StubLog.output))

    def test_old_direct_vm_command_is_retired_and_keeps_repl_open(self):
        self.console.do_select_course("windows-lpe")
        self.assertFalse(self.console.do_course_vm_create("CREATE windows-lpe"))
        self.assertEqual(self.console.legacy_calls, [])
        self.assertTrue(any(
            "retired" in msg.lower() for _level, msg in StubLog.output
        ))

    def test_windows_lpe_interactive_install_boots_via_native_stage1_only(self):
        self.console.do_select_course("windows-lpe")
        self.assertEqual(self.console.prompt, '\nKINGDOMS/windows-lpe > ')
        with patch("builtins.input", side_effect=["172.28.231", "CREATE WSLPE"]):
            self.assertFalse(self.console.onecmd("install"))
        self.assertEqual(self.console.legacy_calls, [])
        self.assertEqual(self.bootstrap_calls, [("172.28.231", True)])

    def test_windows_lpe_install_wrong_confirmation_fails_closed(self):
        self.console.do_select_course("windows-lpe")
        with patch("builtins.input", side_effect=["172.28.231", "yes"]):
            self.assertFalse(self.console.onecmd("install"))
        self.assertEqual(self.console.legacy_calls, [])
        self.assertEqual(self.bootstrap_calls, [])

    def test_windows_lpe_install_bad_network_fails_before_confirmation(self):
        self.console.do_select_course("windows-lpe")
        with patch("builtins.input", side_effect=["10.4.10", AssertionError("prompted")]):
            self.assertFalse(self.console.do_install(""))
        self.assertEqual(self.bootstrap_calls, [])

    def test_wslpe_resume_is_allowed_only_for_existing_selected_guest(self):
        self.console.do_select_course("windows-lpe")
        self.active["instance"] = types.SimpleNamespace(lab_name="WSLPE")
        with patch("builtins.input", side_effect=["RESUME WSLPE"]):
            self.assertFalse(self.console.onecmd("resume"))
        self.assertEqual(self.resume_calls, [True])
        self.assertEqual(self.bootstrap_calls, [])
        self.assertEqual(self.console.legacy_calls, [])

    def test_wslpe_resume_rejects_wrong_phrase_without_vm_action(self):
        self.console.do_select_course("windows-lpe")
        self.active["instance"] = types.SimpleNamespace(lab_name="WSLPE")
        with patch("builtins.input", side_effect=["yes"]):
            self.assertFalse(self.console.onecmd("resume"))
        self.assertEqual(self.resume_calls, [])

    def test_wslpe_resume_without_loaded_guest_fails_before_prompt(self):
        self.console.do_select_course("windows-lpe")
        with patch("builtins.input", side_effect=AssertionError("prompted")):
            self.assertFalse(self.console.onecmd("resume"))
        self.assertEqual(self.resume_calls, [])

    def test_wslpe_resume_rejects_extra_arguments(self):
        self.console.do_select_course("windows-lpe")
        self.active["instance"] = types.SimpleNamespace(lab_name="WSLPE")
        with patch("builtins.input", side_effect=AssertionError("prompted")):
            self.assertFalse(self.console.onecmd("resume --noninteractive"))
        self.assertEqual(self.resume_calls, [])
        self.assertEqual(self.console.legacy_calls, [])
        self.assertTrue(any(
            "Usage: resume" in message for level, message in StubLog.output
            if level == "error"
        ))

    def test_wslpe_install_extra_args_rejected_through_interactive_dispatch(self):
        self.console.do_select_course("windows-lpe")
        with patch("builtins.input", side_effect=AssertionError("prompted")):
            self.assertFalse(self.console.onecmd("install --noninteractive"))
        self.assertEqual(self.bootstrap_calls, [])
        self.assertEqual(self.console.legacy_calls, [])

    def test_wslpe_resume_without_explicit_course_is_blocked(self):
        self.active["lab"] = "WSLPE"
        self.active["instance"] = types.SimpleNamespace(lab_name="WSLPE")
        self.assertFalse(self.console.onecmd("resume"))
        self.assertEqual(self.resume_calls, [])

    def test_windows_lpe_install_loaded_instance_fails_without_prompts(self):
        self.console.do_select_course("windows-lpe")
        self.active["instance"] = object()
        with patch("builtins.input", side_effect=AssertionError("prompted")):
            self.assertFalse(self.console.do_install(""))
        self.assertEqual(self.bootstrap_calls, [])

    def test_windows_lpe_install_extra_args_refused_without_prompt(self):
        self.console.do_select_course("windows-lpe")
        with patch("builtins.input", side_effect=AssertionError("prompted")):
            self.assertFalse(self.console.do_install("--non-interactive"))
        self.assertEqual(self.bootstrap_calls, [])

    def test_windows_lpe_install_requires_explicit_course_selection(self):
        self.active["lab"] = "WSLPE"
        with patch("builtins.input", side_effect=AssertionError("prompted")):
            self.assertFalse(self.console.do_install(""))
        self.assertEqual(self.bootstrap_calls, [])

    def test_course_switching_and_legacy_console_compatibility(self):
        self.console.do_select_course("windows-lpe")
        self.assertTrue(self.console._set_course_selection("north"))
        self.assertEqual(self.console.onecmd("start"), "LEGACY")
        self.assertEqual(self.console.legacy_calls, ["start"])

    def test_course_selection_routes_through_native_kingdoms_lab_manager(self):
        self.assertTrue(self.console._set_course_selection("windows-lpe"))
        self.assertEqual(self.active["lab"], "WSLPE")
        self.assertTrue(self.console._set_course_selection("north"))
        self.assertEqual(self.active["lab"], "GOAD")

    def test_reject_north_switch_while_another_instance_is_loaded(self):
        self.active["lab"] = "WSLPE"
        self.active["instance"] = object()
        self.assertFalse(self.console._set_course_selection("north"))
        self.assertEqual(self.active["lab"], "WSLPE")
        self.assertIsNone(getattr(self.console, "_selected_course", None))

    def test_reject_windows_lpe_switch_while_north_instance_is_loaded(self):
        self.active["instance"] = object()
        self.assertFalse(self.console._set_course_selection("windows-lpe"))
        self.assertEqual(self.active["lab"], "GOAD")
        self.assertIsNone(getattr(self.console, "_selected_course", None))

    def test_reject_missing_wslpe_recipe(self):
        self.console.lab_manager.is_lab_exist = lambda lab: lab == "GOAD"
        self.assertFalse(self.console._set_course_selection("windows-lpe"))
        self.assertEqual(self.active["lab"], "GOAD")

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
            _set_course_selection=lambda slug: self.calls.append(("select", (slug,))) or True,
            _inspect_selected_windows_lpe=lambda action: self.calls.append(("inspect", (action,))) or True,
            _create_selected_windows_lpe_guest=lambda confirmed=False: self.calls.append(
                ("create", (confirmed,))
            ) or True,
        )

    @staticmethod
    def args(task, course, lab="GOAD", instance="existing"):
        return types.SimpleNamespace(
            task=task, course=course, lab=lab, instance=instance,
            run_playbook=None, ansible_only=None,
            confirm_vm_create=False,
        )

    def test_all_windows_lpe_mutating_cli_actions_are_blocked_before_instance_load(self):
        for task in ("install", "start", "stop", "destroy", "reset", "snapshot", "validate", "mode", "ws01"):
            self.assertEqual(dispatch_task(self.console, self.args(task, "windows-lpe")), 1)
        self.assertEqual(self.calls, [])

    def test_course_listing_and_unavailable_course_status_are_read_only(self):
        self.assertEqual(dispatch_task(self.console, self.args("courses", "windows-lpe")), 0)
        self.assertEqual(dispatch_task(self.console, self.args("status", "windows-lpe")), 0)
        self.assertEqual(self.calls, [("courses", ())])

    def test_windows_lpe_backend_cli_inspection_is_scoped_and_read_only(self):
        self.assertEqual(dispatch_task(self.console, self.args("course-preflight", "windows-lpe")), 0)
        self.assertEqual(dispatch_task(self.console, self.args("course-vm-status", "windows-lpe")), 0)
        self.assertEqual(
            self.calls,
            [
                ("select", ("windows-lpe",)),
                ("inspect", ("preflight",)),
                ("select", ("windows-lpe",)),
                ("inspect", ("status",)),
            ],
        )
        self.calls.clear()
        self.assertEqual(dispatch_task(self.console, self.args("course-preflight", "course-2")), 1)
        self.assertEqual(self.calls, [])

    def test_retired_cli_vm_creation_refused_with_or_without_confirmation(self):
        args = self.args("course-vm-create", "windows-lpe", instance=None)
        self.assertEqual(dispatch_task(self.console, args), 1)
        args.confirm_vm_create = True
        self.assertEqual(dispatch_task(self.console, args), 1)
        self.assertEqual(self.calls, [])

    def test_retired_cli_vm_creation_refused_for_other_course(self):
        args = self.args("course-vm-create", "course-2", instance=None)
        args.confirm_vm_create = True
        self.assertEqual(dispatch_task(self.console, args), 1)
        self.assertEqual(self.calls, [])

    def test_unrecognized_and_mismatched_cli_course_fail_closed(self):
        self.assertEqual(dispatch_task(self.console, self.args("install", "fake")), 1)
        self.assertEqual(dispatch_task(self.console, self.args("install", "north", lab="GOAD-Light")), 1)
        self.assertEqual(self.calls, [])

    def test_legacy_wslpe_lab_bypass_cannot_install(self):
        self.assertEqual(
            dispatch_task(self.console, self.args("install", None, lab="WSLPE", instance=None)),
            1,
        )
        self.assertEqual(self.calls, [])

    def test_legacy_wslpe_lab_bypass_cannot_reset_or_destroy(self):
        for task in ("destroy", "start", "stop", "reset", "snapshot"):
            self.assertEqual(
                dispatch_task(self.console, self.args(task, None, lab="WSLPE")),
                1,
            )
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
