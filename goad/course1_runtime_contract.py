"""Kingdoms per-instance Windows machine rosters and dependency planning.

This is an *inert contract* for upcoming VMware lifecycle work. It performs
zero filesystem/VM calls and deliberately DOES NOT enable reduced installation.
The validated six-machine GOAD lifecycle remains authoritative until all
production lifecycle entry points are adapted and accepted.
"""
from dataclasses import dataclass
from typing import Mapping

FULL_WINDOWS = (
    "GOAD-DC01", "GOAD-DC02", "GOAD-DC03",
    "GOAD-SRV02", "GOAD-SRV03", "GOAD-WS01",
)
COURSE1_WINDOWS = (
    "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01",
)
ROUTER = "GOAD-ROUTER"


class ProfileNotReady(ValueError):
    """Invalid or unapproved runtime profile: refuse before VM actions."""


@dataclass(frozen=True)
class RuntimeRoster:
    name: str
    windows: tuple[str, ...]
    start_order: tuple[str, ...]
    dependencies: Mapping[str, tuple[str, ...]]
    management_hosts: Mapping[str, str]

    def __post_init__(self) -> None:
        expected = set(self.windows)
        if not self.windows or len(expected) != len(self.windows):
            raise ValueError("empty or duplicate Windows roster")
        if set(self.start_order) != expected:
            raise ValueError("start order must contain exactly the Windows roster")
        if len(self.start_order) != len(expected):
            raise ValueError("duplicate start order")
        if set(self.dependencies) != expected:
            raise ValueError("each Windows machine needs an explicit dependency definition")
        if set(self.management_hosts) != expected:
            raise ValueError("management endpoints must exactly match the Windows roster")
        for machine, deps in self.dependencies.items():
            if machine in deps or not set(deps).issubset(expected):
                raise ValueError("invalid dependency for " + machine)
            if any(self.start_order.index(dep) >= self.start_order.index(machine) for dep in deps):
                raise ValueError("dependency order is not topological for " + machine)

    def requested_start(self, machine: str | None = None) -> tuple[str, ...]:
        """Return transitive prerequisite closure, in safe guest start order."""
        if machine is None:
            return self.start_order
        if machine == ROUTER:
            return ()
        if machine not in self.windows:
            raise ProfileNotReady("machine is outside selected instance roster: " + machine)
        closure: set[str] = set()

        def require(node: str) -> None:
            if node in closure:
                return
            closure.add(node)
            for dep in self.dependencies[node]:
                require(dep)

        require(machine)
        return tuple(name for name in self.start_order if name in closure)

    def ordered_stop(self) -> tuple[str, ...]:
        """Stop children/members before domain controllers; router last separately."""
        return tuple(reversed(self.start_order))


FULL = RuntimeRoster(
    name="full-goad",
    windows=FULL_WINDOWS,
    start_order=FULL_WINDOWS,
    dependencies={
        "GOAD-DC01": (),
        "GOAD-DC02": ("GOAD-DC01",),
        "GOAD-DC03": (),
        "GOAD-SRV02": ("GOAD-DC01", "GOAD-DC02"),
        "GOAD-SRV03": ("GOAD-DC03",),
        "GOAD-WS01": ("GOAD-DC01", "GOAD-DC02"),
    },
    management_hosts={
        "GOAD-DC01": "10.4.20.10",
        "GOAD-DC02": "10.4.10.11",
        "GOAD-DC03": "10.4.30.12",
        "GOAD-SRV02": "10.4.10.22",
        "GOAD-SRV03": "10.4.30.23",
        "GOAD-WS01": "10.4.10.31",
    },
)
COURSE1 = RuntimeRoster(
    name="course1-fall-of-the-north",
    windows=COURSE1_WINDOWS,
    start_order=COURSE1_WINDOWS,
    dependencies={
        "GOAD-DC01": (),
        "GOAD-DC02": ("GOAD-DC01",),
        "GOAD-SRV02": ("GOAD-DC01", "GOAD-DC02"),
        "GOAD-WS01": ("GOAD-DC01", "GOAD-DC02"),
    },
    management_hosts={
        "GOAD-DC01": "10.4.20.10",
        "GOAD-DC02": "10.4.10.11",
        "GOAD-SRV02": "10.4.10.22",
        "GOAD-WS01": "10.4.10.31",
    },
)


def examine_profile_manifest(manifest: object) -> RuntimeRoster:
    """Fail closed on preview manifests or arbitrary course profiles.

    This intentionally recognizes *legacy only* as operational. Course 1
    manifests remain blocked until installation/startup/reset, router policy,
    and SQL dual-instance provisioning all use this contract.
    """
    if not isinstance(manifest, dict):
        raise ProfileNotReady("instance profile must be a JSON object")
    if manifest.get("state") == "PREVIEW_ONLY_NOT_INSTALLABLE":
        raise ProfileNotReady("Course 1 source preview is not an installable runtime")
    if manifest.get("profile") == COURSE1.name:
        raise ProfileNotReady("Course 1 runtime activation has not passed release gates")
    if manifest.get("profile") == FULL.name and manifest.get("state") == "ACTIVE_LEGACY":
        if manifest.get("windows_machines") != list(FULL_WINDOWS):
            raise ProfileNotReady("legacy profile machine roster mismatch")
        return FULL
    raise ProfileNotReady("unknown or unapproved per-instance profile manifest")
