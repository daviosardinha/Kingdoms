# NORTH native WinRS release gate — private Windows CI runner

## Status and why this exists

NORTH VMware release candidate `96a1d61a397870ca938e041569c491fdc0aa83c2` passed a real five-VM cold start and `NORTH_RUNTIME_ACCEPTANCE=PASS` on 2026-10-28. The public GitHub Actions workflow's Linux source tests and native Windows parser/encoded-command fixtures passed, but its native WinRS *integration* test could not obtain a shell on GitHub-hosted Windows.

- `windows-latest` and `windows-2022`: the preexisting localhost:5986 listener certificate was expired (WSMan 12175).
- Replacing the certificate on the hosted disposable runner resolved expiry, but a real `Session.Create` then timed out (WSMan 2150858793).
- Neither failure happened on the validated NORTH environment. Neither can be interpreted as a passing native WinRS integration test.

For that reason, a dedicated **private, disposable Windows runner** is required. This must **never** be registered against the public `daviosardinha/Kingdoms` repository or run on the VMware host, NORTH, PURPLE, KINGDOMS, or WSLPE guests. See GitHub's public-repository self-hosted runner security warnings.

## Repository separation

- Public `daviosardinha/Kingdoms`: runs Linux `source-gates` and Windows EPR/CLIXML/parser/loader tests on GitHub-hosted runners. The native WinRS job is intentionally absent. Public CI success **does not** certify native WinRS transport.
- Private `daviosardinha/Kingdoms-WinRS-CI` (to be created by the repository owner): holds a copy of `ci/private-winrs-runner/north-winrs-private.yml` at `.github/workflows/north-winrs-private.yml` on its default branch. This template is *not* an executable public workflow.
- Private CI runner: isolated **non-domain-joined**, disposable Windows Server 2022 or Windows 11 VM named `NK-WINRS-CI`. It should have no route to any training lab, no reusable secrets, and no production credentials. Assign it only to the PRIVATE CI repository with runner label `kingdoms-winrs-ci`. Use one-shot ephemeral runner registration and reimage from a trusted base image after each job.

The private workflow is **manual** (`workflow_dispatch`) and pins the public repo checkout to an immutable reviewed Git commit. It does not accept arbitrary caller-supplied SHA or pull-request branch. No privileged private runner should execute unreviewed PR code.

## Prepare the disposable Windows VM

Using an elevated Windows PowerShell 5.1 prompt on the dedicated CI guest **only**:

1. Give the guest the hostname `NK-WINRS-CI` and reboot if renaming was needed. Keep it in a separate local workgroup, not an AD domain.
2. Configure the local WinRM service and a valid `localhost` HTTPS certificate/listener using `ci/private-winrs-runner/prepare-disposable-winrm.ps1 -ConfirmDisposableRunner`. This script refuses to run on any training guest, a domain-joined machine, or a different hostname. It affects **only that Windows CI VM**.
3. In GitHub, create the *private* `daviosardinha/Kingdoms-WinRS-CI` repository. In **Settings → Actions → Runners**, select **New self-hosted runner → Windows x64** and follow GitHub's registration instructions on the CI VM. Add `--labels kingdoms-winrs-ci --ephemeral` to the configuration command. Do not commit the registration token or pass it into any ChatGPT conversation.
4. Run the runner in that dedicated guest with the local administrator context required by the test fixture. It provisions and removes an ephemeral local test user and temporarily changes `LocalAccountTokenFilterPolicy`. Reimage the disposable guest after the run.
5. Copy the template YAML into the PRIVATE repository's default branch. In the private repo **Actions** tab, manually dispatch **NORTH native WinRS - private Windows integration**.

**GitHub Apps cannot register or provision your Windows VM from this chat.** Do not confuse adding this template to the public repository with provisioning a runner. No dedicated runner or private repo is claimed to exist yet.

## Source revision and release policy

The template currently pins source SHA `fdfcb64871f481f467f130ae8b744dfbeba3f1ac`, which contains the controlled private-CI eligibility gate. The cold-start-validated ancestor is `96a1d61a397870ca938e041569c491fdc0aa83c2`. The template's checked-out revision is explicitly verified with `git rev-parse HEAD`.

For each *new* candidate, review the diff, update **both** copies of the pin in the private workflow (checkout ref and explicit SHA assertion), then dispatch it manually. The private runner proof only applies to that exact pinned revision. It does not automatically validate later edits or the runtime of any NORTH instance.

Merge requirements for NORTH integration:

- Public Linux source and Windows parser suites pass at the candidate head.
- The private Windows native WinRS integration fixture reports `NORTH_PARENT_WINRS_WINDOWS_TESTS=... PASS` at the approved exact commit. TLS/certificate validity, authenticated shell creation, failed-password rejection, and nonzero-exit checks all remain mandatory.
- PR compatibility with current `main`, especially PURPLE additions, is reviewed and all required check contexts succeed.
- NORTH runtime acceptance and one cold-start observation are linked to the actual release revision. If code affecting runtime semantics changed since the observed commit, requalify appropriately; do not call that old evidence a new cold-start PASS.
- Never downgrade HTTPS/TLS, bypass authentication, loosen the root-PDC proof or register a public repository runner simply to turn CI green.

If the private runner cannot be provisioned or native WinRS still times out, **release remains blocked**, even though existing NORTH VMs are operational.
