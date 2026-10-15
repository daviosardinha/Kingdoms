"""Kingdoms operator course registry.

The catalogue is deliberately separate from legacy AD lab discovery. It
describes operator-managed course deployments, not learner-accessible APIs.
A course is not installable until its dedicated provider adapter is validated.
"""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Course:
    slug: str
    title: str
    state: str
    legacy_lab: Optional[str] = None
    standalone: bool = False

    @property
    def lifecycle_ready(self) -> bool:
        return self.state == "available"


COURSES: Tuple[Course, ...] = (
    Course(
        slug="north",
        title="The Fall of the North",
        state="available",
        legacy_lab="GOAD",  # Internal compatibility identifier, not course branding.
    ),
    Course(
        slug="course-2",
        title="Course 2 (title pending)",
        state="planned",
    ),
    Course(
        slug="windows-lpe",
        title="Windows Local Privilege Escalation (title pending)",
        state="development",
        standalone=True,
    ),
)

_ALIASES = {
    "1": "north",
    "fall-of-the-north": "north",
    "2": "course-2",
    "3": "windows-lpe",
}


def get_course(identifier: str) -> Optional[Course]:
    """Return a configured course, never a dynamically discovered lab path."""
    name = identifier.strip().lower().replace("_", "-")
    name = _ALIASES.get(name, name)
    return next((course for course in COURSES if course.slug == name), None)


def catalog_lines() -> Tuple[str, ...]:
    return tuple(
        f"{course.slug:<14} {course.title} [{course.state}]"
        for course in COURSES
    )
