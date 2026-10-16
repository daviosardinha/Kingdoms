"""Fail-closed qualification checkpoint parser for standalone WSLPE.

A prior 0600 report can identify the first failed technique, but it does
not prove current Windows state. The invoking runner MUST revalidate
every skipped technique as vulnerable on the exact standalone guest,
without applying or resetting any skipped technique.
"""
from __future__ import annotations
from pathlib import Path
import json
import os
import re
import stat

def resume_position(records: object, catalog: tuple[str, ...],
                    flow: tuple[tuple[str, str | None], ...]) -> int:
    if not isinstance(records, list) or not records:
        raise ValueError("Qualification checkpoint is empty")
    if len(catalog) != 20 or len(set(catalog)) != 20 or len(flow) != 6:
        raise ValueError("Unexpected Windows LPE catalog or qualification flow")
    if len(records) > len(catalog)*len(flow):
        raise ValueError("Qualification checkpoint has too many entries")
    failure = None
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != {
            "technique", "action", "state", "exit_code"
        }:
            raise ValueError("Untrusted qualification checkpoint schema")
        technique_idx, flow_idx = divmod(index, len(flow))
        action, state = flow[flow_idx]
        if (record["technique"] != catalog[technique_idx]
                or record["action"] != action or record["state"] != state
                or type(record["exit_code"]) is not int):
            raise ValueError("Qualification checkpoint does not follow exact scenario order")
        if record["exit_code"] != 0:
            if index != len(records) - 1 or failure is not None:
                raise ValueError("Checkpoint contains a failure before the final step")
            failure = (technique_idx, flow_idx)
    if failure is None:
        raise ValueError("Checkpoint has no failed step; cannot resume")
    technique_idx, flow_idx = failure
    if flow_idx != 0:
        raise ValueError("Failed scenario has partial apply/validate/reset cycle: manual review required")
    if len(records) != technique_idx * len(flow) + 1:
        raise ValueError("Cannot trust incomplete previous scenario cycles")
    return technique_idx


def private_records(path: Path, report_dir: Path) -> list[dict]:
    """Validate the owner-only existing checkpoint before reading its rows."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("Checkpoint is not a regular file")
    if (not re.fullmatch(r"wslpe-qualification-\d{8}T\d{6}Z\.json", path.name)
            or path.parent.resolve(strict=True) != report_dir.resolve(strict=True)
            or path.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.stat().st_mode) != 0o600
            or path.stat().st_size > 80_000):
        raise ValueError("Checkpoint is not the approved private WSLPE report")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Checkpoint must contain an ordered list of scenario operations")
    return data


def load_private_checkpoint(path: Path, report_dir: Path,
                            catalog: tuple[str, ...],
                            flow: tuple[tuple[str, str | None], ...]) -> int:
    """Read and validate a complete-from-technique-1 qualification report."""
    return resume_position(private_records(path, report_dir), catalog, flow)


def load_chained_private_checkpoint(prefix: Path, continuation: Path,
                                    report_dir: Path, catalog: tuple[str, ...],
                                    flow: tuple[tuple[str, str | None], ...]) -> int:
    """Strictly validate two immutable partial reports, without writing a third.

    The first report ends at a failed APPLY. The next report starts exactly
    at that technique and ends at a later failed APPLY. No failed reset or
    reordered/missing successful scenario cycles is acceptable.
    """
    if prefix == continuation or prefix.resolve() == continuation.resolve():
        raise ValueError("Chained WSLPE checkpoints must be distinct")
    prefix_rows = private_records(prefix, report_dir)
    first = resume_position(prefix_rows, catalog, flow)
    remainder = private_records(continuation, report_dir)
    if not remainder or len(remainder) <= len(flow):
        raise ValueError("Wslpe chained report must contain successful new technique cycles")
    if len(prefix_rows) - 1 != first * len(flow):
        raise ValueError("Wslpe original report is not an exact failed-apply prefix")
    position = resume_position(prefix_rows[:-1] + remainder, catalog, flow)
    if position <= first:
        raise ValueError("Wslpe chained report does not advance the qualification")
    return position
