"""NORTH runtime source guard accepts tracked independent worktrees, not random folders.

Run without VMware or Windows guests. No real host changes.
"""
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate-north-runtime.sh"


def git(*argv):
    return subprocess.run(("git", *map(str, argv)), check=True,
                          capture_output=True, text=True)


def guard_snippet():
    text = VALIDATOR.read_text()
    first = text.index("# A normal checkout has a .git directory")
    last = text.index("\nfor cmd in ", first)
    snippet = text[first:last]
    assert 'rev-parse --show-toplevel' in snippet
    assert 'ls-files --error-unmatch -- scripts/validate-north-runtime.sh' in snippet
    assert '[[ -d "$ROOT/.git" || -f "$ROOT/.git" ]]' in snippet
    return snippet


def check_guard(checkout):
    script = (
        "set -Eeuo pipefail\n"
        + f"ROOT={shlex.quote(str(checkout))}\n"
        + "fail() { echo \"[BLOCKED] $*\" >&2; exit 90; }\n"
        + guard_snippet()
        + "\nprintf 'GUARD_PASS\\n'"
    )
    return subprocess.run(("bash", "-c", script), capture_output=True, text=True)


def make_repo(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    (main / "scripts").mkdir()
    shutil.copyfile(VALIDATOR, main / "scripts" / "validate-north-runtime.sh")
    git("-C", main, "init", "-q")
    git("-C", main, "config", "user.email", "test@example.invalid")
    git("-C", main, "config", "user.name", "NORTH test")
    git("-C", main, "add", "scripts/validate-north-runtime.sh")
    git("-C", main, "commit", "-qm", "Synthetic tracked NORTH source")
    return main


def test_normal_clone_and_real_linked_worktree_both_pass(tmp_path):
    main = make_repo(tmp_path)
    assert (main / ".git").is_dir()
    a = check_guard(main)
    assert a.returncode == 0, a.stderr
    assert "GUARD_PASS" in a.stdout

    linked = tmp_path / "release-gate"
    git("-C", main, "worktree", "add", "-qb", "north-release-test", linked)
    assert (linked / ".git").is_file()
    b = check_guard(linked)
    assert b.returncode == 0, b.stderr
    assert "GUARD_PASS" in b.stdout


def test_fake_git_directory_and_untracked_validator_fail_closed(tmp_path):
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / ".git").mkdir()
    assert check_guard(fake).returncode != 0

    untracked = tmp_path / "untracked"
    untracked.mkdir()
    git("-C", untracked, "init", "-q")
    assert check_guard(untracked).returncode != 0


def test_validator_shell_syntax():
    subprocess.run(("bash", "-n", str(VALIDATOR)), check=True)
