# Kingdoms Course 1 — CASTELBLACK ↔ BRAAVOS MSSQL inspection

This is a **read-only runtime validation** to establish whether the existing
CASTELBLACK linked server can query BRAAVOS under its configured SQL login
mapping. It does not install a second instance and does not require a direct
Kali-to-ESSOS route, any VMware management access, or Vagrant credentials.

From the repo checkout **on Kali** (with access to 10.4.10.22:1433):

```bash
bash scripts/validate-course1-mssql-readonly.sh
```

The validator asks interactively for the existing `NORTH\jon.snow` password;
do not put it in Git, a shell command line, or an environment variable.
It uses Impacket MSSQL Windows Authentication to CASTELBLACK and executes the
fixed statements in `course1-linked-readonly.sql`. The remote SELECT is sent
over the existing SQL linked server from CASTELBLACK to BRAAVOS.

Expected proof markers:
- `KINGDOMS_LOCAL_PROOF_OK`: CASTELBLACK SQL query returned a row.
- `KINGDOMS_REMOTE_PROOF_OK`: BRAAVOS SQL SELECT returned a row via OPENQUERY.

Only result ROWS count. A printed SQL command containing the marker does not
count. The validator returns a nonzero status if the remote proof fails.

A private log is stored under `~/Kingdoms-evidence/course1-mssql-readonly/`.
Review it before sharing. The log contains SQL metadata (logins, linked-server
names, infrastructure), but not the entered password.

A successful result establishes linked-server functionality, **not** resource
capacity for two SQL instances and **not** cross-host lateral movement in the
planned single-host Course 1 replacement. Dual-instance capacity and stability
must be validated separately on a clone or resettable test instance.

This implementation intentionally does **not** start/stop VMs, change router
policies, open direct cross-forest access, alter SQL credentials or memberships,
modify Notion, or remove ESSOS from the production deployment.
