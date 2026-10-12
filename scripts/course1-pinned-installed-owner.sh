#!/usr/bin/env bash
# Pinned offline recheck for an in-progress NORTH recovery acceptance.
# Parent MUST have passed the strict online installed-source gate before lifecycle changes.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

blocked() {
  printf '[BLOCKED] NORTH pinned owner verification: %s\n' "$*" >&2
  exit 2
}
if [[ $# != 2 || "$1" != /* || ! "$2" =~ ^[0-9a-f]{40}$ ]]; then
  echo 'Usage: bash scripts/course1-pinned-installed-owner.sh <absolute-provider-dir> <40-hex-attested-HEAD>' >&2
  exit 2
fi
PROVIDER="$1"
PIN="$2"
[[ -d "$PROVIDER" && ! -L "$PROVIDER" ]] || blocked 'installed provider not a regular directory'
for cmd in git sudo; do
  command -v "$cmd" >/dev/null || blocked "missing $cmd"
done

[[ "$(git rev-parse --show-toplevel 2>/dev/null)" == "$ROOT" ]] ||
  blocked 'checkout root changed'
[[ "$(git symbolic-ref --quiet --short HEAD 2>/dev/null)" == 'rebuild/course1-from-kingdoms' ]] ||
  blocked 'wrong or detached branch'
[[ "$(git rev-parse --verify HEAD 2>/dev/null)" == "$PIN" ]] ||
  blocked 'local commit changed after initial online attestation'
[[ "$(git rev-parse --verify '@{upstream}' 2>/dev/null)" == "$PIN" ]] ||
  blocked 'locally tracked upstream differs from the attested commit'
[[ -z "$(git status --porcelain=v1 --untracked-files=normal)" ]] ||
  blocked 'worktree or index changed after initial online attestation'

sudo -n bash scripts/setup-vmware-networks.sh --north verify --provider-dir "$PROVIDER" ||
  blocked 'installed vmnet ownership no longer matches'
echo '[PASS] NORTH source and installed VMnet ownership verified (read-only)'
echo 'NORTH_PINNED_LOCAL_SOURCE_AND_OWNER=PASS'
