"""Source-level regression checks for the opt-in NORTH 20-topic validator."""
import importlib.util
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/validate-north-climb-the-keep.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("north_climb_validator", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_twenty_notion_topics_are_mapped_once():
    validator = load_validator()
    assert len(validator.TECHNIQUES) == 20
    assert [int(row[0]) for row in validator.TECHNIQUES] == list(range(1, 21))
    assert len(set(row[1] for row in validator.TECHNIQUES)) == 20
    assert validator.EXPECTED == {name for _, name, _ in validator.TECHNIQUES}


def test_source_gate_covers_every_role_without_claiming_execution():
    validator = load_validator()
    records = validator.source_audit()
    assert len(records) == 20
    assert all(row["source"] == "PASS" for row in records), records
    assert all(row["configuration"] == "NOT_RUN" for row in records)
    assert all(row["interactive_system"] == "NOT_RUN" for row in records)


def test_source_mode_requires_no_guest_access(tmp_path, monkeypatch):
    validator = load_validator()
    monkeypatch.setattr(validator, "REPORT_DIR", tmp_path)
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Source validation must not invoke any guest command")
    monkeypatch.setattr(validator, "invoke", fail_if_called)
    assert validator.main(["--mode", "source"]) == 0
    files = list(tmp_path.glob("configuration-*.json"))
    assert len(files) == 1
    import json
    data = json.loads(files[0].read_text())
    assert data["mode"] == "source"
    assert len(data["topics"]) == 20


def test_configuration_mode_refuses_without_acknowledgement():
    result = subprocess.run(
        ["python3", str(SOURCE), "--mode", "configuration"],
        cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "--acknowledge-temporary-guest-changes" in result.stderr


def test_configuration_mode_cannot_target_another_lab(tmp_path):
    validator = load_validator()
    records = validator.source_audit()
    try:
        validator.configuration_audit(records, tmp_path / "wslpe")
    except ValueError as error:
        assert "approved disposable NORTH workspace" in str(error)
    else:
        raise AssertionError("Non-NORTH provider was accepted")
