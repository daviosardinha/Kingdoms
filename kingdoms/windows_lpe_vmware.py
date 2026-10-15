"""Read-only VMware backend preflight for the standalone Windows LPE course.

This module is operator-only. It intentionally has no install, destroy, start,
stop, or reset method. Those actions require a separately validated lifecycle
adapter and local Windows learner provisioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Callable, List, Optional, Tuple


STANDALONE_PROJECT = Path("courses/windows-lpe/standalone")
EXPECTED_BOX = "mayfly/windows10"
EXPECTED_VERSION = "2024.01.06"
EXPECTED_VM = "kingdoms-lpe-ws01"


@dataclass(frozen=True)
class PreflightResult:
    ready: bool
    checks: Tuple[str, ...]


class WindowsLpeVmwareAdapter:
    """Isolated, read-only checks for the operator's dedicated Vagrant project."""

    def __init__(
        self,
        root: Optional[Path] = None,
        runner: Optional[Callable] = None,
        which: Optional[Callable] = None,
    ):
        self.root = Path(root or Path(__file__).resolve().parents[1]).resolve()
        self.project = self.root / STANDALONE_PROJECT
        self._runner = runner or subprocess.run
        self._which = which or shutil.which

    def _run(self, args: List[str], timeout: int = 45) -> Tuple[bool, str]:
        """Run only a fixed, whitelisted read-only command in this project."""
        allowed = {
            ("ruby", "-c", str(self.project / "Vagrantfile")),
            ("vagrant", "validate"),
            ("vagrant", "plugin", "list"),
            ("vagrant", "box", "list"),
            ("vagrant", "status"),
        }
        if tuple(args) not in allowed:
            raise ValueError("Non-inspection command refused by Windows LPE preflight")
        try:
            process = self._runner(
                args,
                cwd=str(self.project),
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"{args[0]} inspection unavailable: {type(exc).__name__}"

        output = (process.stdout or "") + "\n" + (process.stderr or "")
        return process.returncode == 0, output.strip()

    def _validate_project(self) -> Tuple[bool, str]:
        """Fail before Vagrant runs unless the dedicated project is identified."""
        file = self.project / "Vagrantfile"
        if not file.is_file():
            return False, "Standalone Vagrantfile missing"
        if self.project.resolve() == self.root.resolve():
            return False, "Standalone project resolves to repository root"
        if not self.project.resolve().is_relative_to(self.root.resolve()):
            return False, "Standalone project escapes the Kingdoms checkout"
        try:
            source = file.read_text(encoding="utf-8")
        except OSError:
            return False, "Standalone Vagrantfile cannot be read"

        required = (
            f'config.vm.define "{EXPECTED_VM}"',
            f'guest.vm.box = "{EXPECTED_BOX}"',
            f'guest.vm.box_version = "{EXPECTED_VERSION}"',
            'vmware.vmx["ethernet0.connectionType"] = "nat"',
            'vmware.vmx["ethernet1.present"] = "FALSE"',
            'vmware.vmx["ethernet2.present"] = "FALSE"',
        )
        prohibited = (
            "vmnet10", "vmnet20", "vmnet30", "vmnet99",
            "win_domain_membership", "guest.vm.provision",
            "config.vm.provision",
        )
        if any(marker not in source for marker in required):
            return False, "Pinned Windows image or standalone network contract missing"
        if any(marker in source for marker in prohibited):
            return False, "Domain/segmented lab provisioning found in standalone VM"
        return True, "Dedicated VM definition matches the standalone source contract"

    def preflight(self) -> PreflightResult:
        """Prove tool and Vagrantfile readiness, not guest/exploit readiness."""
        ok, detail = self._validate_project()
        checks = [f"{'PASS' if ok else 'FAIL'}: {detail}"]
        if not ok:
            return PreflightResult(False, tuple(checks))

        required_bins = ("vagrant", "ruby")
        missing = [name for name in required_bins if not self._which(name)]
        if missing:
            checks.append("FAIL: missing operator tools: " + ", ".join(missing))
            return PreflightResult(False, tuple(checks))

        success, out = self._run(["ruby", "-c", str(self.project / "Vagrantfile")])
        syntax = success and "Syntax OK" in out
        checks.append(f"{'PASS' if syntax else 'FAIL'}: Vagrantfile Ruby syntax")
        if not syntax:
            return PreflightResult(False, tuple(checks))

        success, out = self._run(["vagrant", "plugin", "list"])
        plugin = success and "vagrant-vmware-desktop" in out
        checks.append(f"{'PASS' if plugin else 'FAIL'}: VMware Desktop Vagrant plugin")
        if not plugin:
            return PreflightResult(False, tuple(checks))

        success, out = self._run(["vagrant", "box", "list"])
        box_present = success and any(
            EXPECTED_BOX in line and "vmware_desktop" in line
            and EXPECTED_VERSION in line
            for line in out.splitlines()
        )
        checks.append(f"{'PASS' if box_present else 'FAIL'}: pinned Windows 10 VMware box")
        if not box_present:
            return PreflightResult(False, tuple(checks))

        success, out = self._run(["vagrant", "validate"], timeout=90)
        checks.append(
            f"{'PASS' if success else 'FAIL'}: dedicated Vagrant project validation"
        )
        if not success:
            return PreflightResult(False, tuple(checks))
        checks.append("INFO: No guest boot or provisioning performed")
        return PreflightResult(True, tuple(checks))

    def vm_status(self) -> PreflightResult:
        """Inspect only the independent Windows LPE project status."""
        ok, message = self._validate_project()
        if not ok:
            return PreflightResult(False, (f"FAIL: {message}",))
        if not self._which("vagrant"):
            return PreflightResult(False, ("FAIL: Vagrant unavailable",))
        success, output = self._run(["vagrant", "status"], timeout=60)
        if not success:
            return PreflightResult(False, ("FAIL: Standalone Vagrant status unavailable",))
        return PreflightResult(
            True, ("INFO: Isolated Windows LPE Vagrant status:", output)
        )
