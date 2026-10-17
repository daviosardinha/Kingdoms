"""Per-WSLPE-instance source-secret overrides for five credential-hunting fixtures.

Only WSLPE uses this overlay; the NORTH shared role is never changed.
Source default passwords are intentionally NOT copied into the overlay.
No Windows/VMware/Ansible side effects occur on secret preparation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

import yaml

from kingdoms.wslpe_operator_credentials import (
    exact_instance_id, _private_dir, _private_file,
)
from kingdoms.wslpe_learner_credentials import _strong_password

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "ansible/roles/windows_lpe/defaults/main.yml"
BASE = Path.home() / ".local/state/kingdoms-wslpe-fixtures"

FIXTURES = {
    "windows_lpe_unattend_credentials": "kingdom.deploy",
    "windows_lpe_powershell_history_credentials": "kingdom.pshistory",
    "windows_lpe_hardcoded_application_credentials": "kingdom.appsvc",
    "windows_lpe_stored_runas_credentials": "kingdom.runas",
    "windows_lpe_stored_winlogon_credentials": "kingdom.autologon",
}

def _template() -> dict:
    source = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    result = {}
    for key, username in FIXTURES.items():
        entry = source.get(key)
        if (not isinstance(entry, dict) or entry.get("user_name") != username
                or not isinstance(entry.get("password"), str)
                or len(entry["password"]) < 8):
            raise ValueError("Frozen LPE fixture source mapping changed")
        result[key] = dict(entry)
    return result

def _valid(data: dict, instance_id: str, source: dict) -> None:
    if (not isinstance(data, dict)
            or set(data) != set(FIXTURES) | {"wslpe_fixture_private", "wslpe_fixture_instance_id"}
            or data["wslpe_fixture_private"] is not True
            or data["wslpe_fixture_instance_id"] != instance_id):
        raise ValueError("Invalid WSLPE-only private fixture overlay")
    seen = set()
    for key in FIXTURES:
        expected = source[key]
        actual = data.get(key)
        if (not isinstance(actual, dict) or set(actual) != set(expected)
                or {k: v for k, v in actual.items() if k != "password"}
                    != {k: v for k, v in expected.items() if k != "password"}):
            raise ValueError("Fixture overlay diverged from frozen scenario contract")
        password = actual["password"]
        if (not isinstance(password, str) or len(password) < 24
                or password == expected["password"] or password in seen
                or any(x in password for x in "\r\n\x00")):
            raise ValueError("Fixture password is missing, reused or source-predictable")
        seen.add(password)

def fixture_vars_file(instance_id: str, *, prepare: bool = False,
                      store: Path = BASE) -> Path:
    ident = exact_instance_id(instance_id)
    source = _template()
    if store.is_symlink() or (not store.exists() and not prepare):
        raise ValueError("Private WSLPE fixture store unavailable or unsafe")
    if prepare:
        store.parent.mkdir(parents=True, exist_ok=True)
    _private_dir(store, create=prepare)
    folder = store / ident
    if not folder.exists() and not prepare:
        raise ValueError("No prepared fixture credentials for exact WSLPE instance")
    _private_dir(folder, create=prepare)
    path = folder / "overlay.json"
    if path.is_symlink():
        raise ValueError("Fixture overlay cannot be a symlink")
    if path.exists():
        _private_file(path)
        _valid(json.loads(path.read_text(encoding="utf-8")), ident, source)
        return path
    if not prepare:
        raise ValueError("Fixture overlay does not exist")
    # Deep-copy each fixture mapping: changing the password must not mutate
    # the canonical default mapping used to reject source-visible secrets.
    document = {key: dict(value) for key, value in source.items()}
    for key in FIXTURES:
        document[key]["password"] = _strong_password()
    document["wslpe_fixture_private"] = True
    document["wslpe_fixture_instance_id"] = ident
    _valid(document, ident, source)
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    _private_file(path)
    return path
