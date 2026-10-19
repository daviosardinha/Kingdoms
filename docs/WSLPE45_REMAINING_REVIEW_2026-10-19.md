# Remaining selected deployment review

Reviewed source at a3cbd7d after the supplied #27 runtime failure.
This is a source/dependency review, not Windows deployment acceptance.

| Selected scenarios | Reviewed implementation | Result |
|---|---|---|
| #27 | WslpeComRegistration | Fix native stderr handling without weakening exit or configuration checks |
| #28 | WslpeRegistryTrust | .NET registry/task APIs; no RegAsm call; collision refusal retained |
| #29 | WslpeBoundary / KingdomBoundaryService | Fix unsupported pipe timeout property; native denial/idle regression added |
| #30 | WslpeJea plus existing-state runner path | Validation only; existing console activation and fresh learner Status gate retained |
| #31–33 | WslpeLsaRights | Direct LSA API status checks; new logon remains required for learner token testing |
| #34 | WslpeBoundary | Exact owned junction unlink remains reset-only; deployment does not reset |
| #35 | traversal.yml / KingdomTraversalService | Canonical source-copy paths and protected-library preservation retained |
| #37 | WslpeWmiConsumer / Kingdom45WmiWake | WMI API errors remain fatal; namespace ACLs unchanged |
| #39 | WslpeBoundary HTTP mode | Fixed loopback endpoint; actual guest binding remains a runtime gate |
| #41–42 | WslpeServiceConsumer / environment child | Dedicated SCM objects, source references and native exit checks reviewed |
| #43–45 | WslpeBoundary plugin/race/restore modes | Source compilation expanded; configuration and learner proof remain distinct |

The remaining native shell calls are scoped sc.exe operations and the #34
reset-only cmd.exe unlink. Their nonzero-exit checks remain mandatory.
No remaining selected module invokes RegAsm. These checks do not establish
absence of other Windows runtime or lifecycle defects.

CI now compiles seven standalone CSharp sources plus five embedded LSA/
registry sources under .NET Framework, parses selected PowerShell under
native PS5.1, and runs the existing Python/Ansible scope and failure contracts.
The pipe test sends STATUS (denied), tests idle timeout and never sends PROOF.
Native stderr tests use a stub executable, never real COM registration.

No excluded #25/#36/#38/#40 implementation, original20/NORTH role, shared
ownership library, JEA implementation or VMware/network configuration changes.
