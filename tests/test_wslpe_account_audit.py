"""Read-only WSLPE local-account audit tests; no guest or hypervisor contact."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/wslpe-account-audit.py"
SPEC=importlib.util.spec_from_file_location("wslpe_account_audit", SCRIPT)
assert SPEC and SPEC.loader
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

def evidence(**changes):
    rows=[{"name":x,"exists":True,"enabled":True,"admin":x not in ("lpe.trainee",)}
          for x in MOD.ACCOUNTS]
    for name, parts in changes.items():
        for row in rows:
            if row["name"]==name:
                row.update(parts)
    return ("WSLPE_ACCOUNT_AUDIT_JSON="+json.dumps(
        {"machine":"WSLPE-WS01","domain_joined":False,"accounts":rows})+"\n").encode()

class AccountAuditTests(unittest.TestCase):
    def test_expected_accounts_and_learner_nonadmin(self):
        items=MOD.parse_result(evidence())
        self.assertEqual(len(items),8)
        self.assertTrue(items["vagrant"]["admin"])
        self.assertFalse(items["lpe.trainee"]["admin"])

    def test_fails_closed_on_privileged_or_missing_learner(self):
        for change in ({"admin":True},{"exists":False,"enabled":False,"admin":False},
                       {"enabled":False}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                MOD.parse_result(evidence(**{"lpe.trainee":change}))

    def test_fails_closed_on_missing_duplicate_and_out_of_scope_identity(self):
        s=json.loads(evidence().decode().partition("=")[2])
        for mode in ("missing", "duplicate", "north", "extra"):
            bad=json.loads(json.dumps(s))
            if mode=="missing":
                bad["accounts"].pop()
            if mode=="duplicate":
                bad["accounts"][0]["name"]="lpe.trainee"
            if mode=="north":
                bad["machine"]="NORTH"
            if mode=="extra":
                bad["accounts"][0]["name"]="Administrator"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                MOD.parse_result(("WSLPE_ACCOUNT_AUDIT_JSON="+json.dumps(bad)).encode())
        with self.assertRaises(ValueError):
            MOD.parse_result(evidence()+evidence())

    def test_pinned_transport_no_credentials_leak_and_no_proxies(self):
        transport=MagicMock()
        http=transport.build_session.return_value
        def make_session(endpoint,*args,**kwargs):
            self.assertEqual(endpoint,"https://WSLPE-WS01:5986/wsman")
            self.assertEqual(kwargs["server_cert_validation"],"validate")
            self.assertEqual(kwargs["transport"],"ntlm")
            self.assertIsNone(kwargs["proxy"])
            http.verify=kwargs["ca_trust_path"]
            return SimpleNamespace(
                protocol=SimpleNamespace(transport=transport),
                run_ps=MagicMock(return_value=SimpleNamespace(
                    status_code=0,std_out=evidence())))
        auth=SimpleNamespace(scoped_wslpe_resolution=MagicMock())
        with patch.dict("sys.modules",{"winrm":SimpleNamespace(Session=make_session)}):
            MOD.query(auth,"172.28.231.31",b"der-cert","bootstrap","private")
        self.assertIs(http.trust_env,False)
        self.assertEqual(http.proxies,{})
        transport.close_session.assert_called_once()

    def test_guest_query_is_read_only_and_exact_scope(self):
        for allowed in ("Get-LocalUser", "Get-LocalGroupMember",
                        "PartOfDomain", "WSLPE_ACCOUNT_AUDIT_JSON"):
            self.assertIn(allowed,MOD.READ_ONLY)
        for forbidden in ("Set-LocalUser", "Disable-LocalUser", "Enable-LocalUser",
                          "New-LocalUser","Remove-LocalUser","Restart-Service",
                          "GOAD-WS01","10.4.10.31"):
            self.assertNotIn(forbidden, MOD.READ_ONLY)

if __name__=="__main__":
    unittest.main()
