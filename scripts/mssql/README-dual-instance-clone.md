# Kingdoms Course 1: dual MSSQL validation on disposable CASTELBLACK clone

**EXPERIMENTAL ONLY. DO NOT EXECUTE ON ORIGINAL GOAD-SRV02.**

Purpose: test whether a second named SQL Server 2019 Express instance on the 6 GB CASTELBLACK profile can preserve linked-server SQL privilege escalation without requiring ESSOS or another Windows VM.

1. In VMware Workstation, stop original GOAD-SRV02 when no learner or Phase 03 session depends on it. Take a snapshot and create a **full clone** named KINGDOMS-SQL-CLONE. Verify available physical RAM and disk space before starting the extra 6 GB VM.
2. BEFORE FIRST START, open the clone VM Settings and **disconnect every network adapter**, including NAT and vmnet10. Disable Connect at power on. Do not let this duplicate domain-joined identity contact any domain controller. The clone has the same hostname and IP as the original.
3. Once cloned, the original may be restarted as needed. Never connect clone to vmnet10, vmnet20, vmnet30, or to a shared provisioning network.
4. Boot the isolated clone using VMware Console, log in as local CASTELBLACK\vagrant. Copy prove-course1-dual-instance-clone.ps1 into the clone using VMware Tools copy/paste or a removable device without enabling NICs.
5. Open an elevated PowerShell in the clone. From the directory containing the script, run:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\prove-course1-dual-instance-clone.ps1 -CloneConfirmed

6. The script fails safely if any network adapter is Up. It installs a new KINGDOMS2 SQL Server 2019 Express named instance (unless already present), configures TCP/1444, creates randomly passworded clone-only SQL test logins, maps source COURSE1_LOW to remote COURSE1_LINK_ADMIN, and verifies source sysadmin=0 versus linked sysadmin=1 using OPENQUERY.
7. If SQL setup returns 3010, reboot the isolated clone and rerun. After initial PASS, reboot the isolated clone and rerun again to test persistence. Keep all NICs disconnected throughout.
8. Capture [PASS], [PROOF], and [RESOURCE] output; review output to ensure no credential material appears before sharing. Delete the disposable clone after validation.

Scope caveats: This is a disposable SQL architecture experiment, not a released Kingdoms Course 1 deployment. It has not been executed on Windows by GitHub CI. Current baseline uses SQLNCLI because it was validated on existing CASTELBLACK; provider modernization to MSOLEDBSQL is separate. A local dual-instance privilege boundary is not cross-host lateral movement. The source instance in this isolated clone runs an already installed domain service account; if it will not start without DC connectivity, STOP and report rather than reconnecting the clone.

No changes to Notion, reference lab, or cross-forest routing are made by these files.
