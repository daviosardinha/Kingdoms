-- Kingdoms Course 1 read-only SQL inspection. One query per line for Impacket -file.
-- LOCAL PROOF, anchored by scripts/validate-course1-mssql-readonly.sh.
SELECT 'KINGDOMS_LOCAL_PROOF_OK' AS Probe, @@SERVERNAME AS ServerName, @@SERVICENAME AS InstanceName, SYSTEM_USER AS LoginContext, IS_SRVROLEMEMBER('sysadmin') AS IsSysadmin, CAST(SERVERPROPERTY('ProductVersion') AS varchar(30)) AS ProductVersion;
-- Registered instances and linked server data sources.
SELECT name, provider, data_source, is_linked, is_data_access_enabled, is_rpc_out_enabled FROM sys.servers ORDER BY name;
-- Security mapping metadata ONLY: remote login names, never passwords.
SELECT s.name AS LinkedServer, COALESCE(p.name, '<ALL LOCAL LOGINS>') AS LocalLogin, l.uses_self_credential, l.remote_name FROM sys.linked_logins AS l JOIN sys.servers AS s ON s.server_id = l.server_id LEFT JOIN sys.server_principals AS p ON p.principal_id = l.local_principal_id WHERE s.is_linked = 1 ORDER BY s.name, p.name;
-- Current engine memory configuration.
SELECT name, value_in_use FROM sys.configurations WHERE name IN ('min server memory (MB)', 'max server memory (MB)') ORDER BY name;
-- Read-only enumeration of installed OLE DB provider names.
EXEC master.dbo.sp_enum_oledb_providers;
-- REMOTE PROOF: connects from SQL Server CASTELBLACK using its configured link.
-- Never try to connect directly from Kali to the ESSOS network.
SELECT 'KINGDOMS_REMOTE_PROOF_OK' AS Probe, RemoteServer, RemoteLogin, RemoteSysadmin FROM OPENQUERY([BRAAVOS], 'SELECT @@SERVERNAME AS RemoteServer, SYSTEM_USER AS RemoteLogin, IS_SRVROLEMEMBER(''sysadmin'') AS RemoteSysadmin');
