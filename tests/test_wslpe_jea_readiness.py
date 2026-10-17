"""Mock-only regression of authenticated WSLPE JEA status preflight."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/wslpe-jea-readiness.py"
SPEC=importlib.util.spec_from_file_location("wslpe_jea_readiness",SCRIPT)
assert SPEC and SPEC.loader
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

BASE={"machine":"WSLPE-WS01","domain_joined":False,"learner_enabled":True,
      "winrm_running":True,"endpoint_count":0,"module_present":False,
      "fixture_present":False}

def evidence(**changes):
    state=dict(BASE,**changes)
    return ("WSLPE_JEA_PREFLIGHT_JSON="+json.dumps(state)+"\n").encode()

class JeaReadiness(unittest.TestCase):
    def test_clean_status(self):
        self.assertEqual(MOD.parse_result(evidence()),BASE)

    def test_detects_partial_existing_state(self):
        for change in ({"endpoint_count":1},{"module_present":True},
                       {"fixture_present":True}):
            state=MOD.parse_result(evidence(**change))
            self.assertTrue(state["endpoint_count"] or
                            state["module_present"] or state["fixture_present"])

    def test_fail_closed_when_identity_or_schema_bad(self):
        for change in ({"machine":"NORTH"},{"domain_joined":True},
                       {"learner_enabled":False},{"winrm_running":False},
                       {"endpoint_count":-1},{"endpoint_count":False},
                       {"module_present":"false"}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                MOD.parse_result(evidence(**change))
        with self.assertRaises(ValueError):
            MOD.parse_result(evidence(extra=True))
        with self.assertRaises(ValueError):
            MOD.parse_result(evidence()+evidence())
        with self.assertRaises(ValueError):
            MOD.parse_result(b"OK\n")

    def test_real_transport_contract_enforces_pin_and_no_proxy(self):
        transport=MagicMock()
        http=transport.build_session.return_value
        result=SimpleNamespace(status_code=0,std_out=evidence())
        def new_session(*args,**kwargs):
            self.assertEqual(args[0],"https://WSLPE-WS01:5986/wsman")
            self.assertEqual(kwargs["server_cert_validation"],"validate")
            self.assertEqual(kwargs["transport"],"ntlm")
            self.assertIsNone(kwargs["proxy"])
            self.assertTrue(Path(kwargs["ca_trust_path"]).is_file())
            http.verify=kwargs["ca_trust_path"]
            return SimpleNamespace(
                protocol=SimpleNamespace(transport=transport),
                run_ps=MagicMock(return_value=result))
        fake=SimpleNamespace(Session=MagicMock(side_effect=new_session))
        auth=SimpleNamespace(scoped_wslpe_resolution=MagicMock())
        auth.scoped_wslpe_resolution.return_value.__enter__.return_value=None
        with patch.dict("sys.modules",{"winrm":fake}):
            state=MOD.query_jea_state(auth,"172.28.231.31",b"der-cert","local","secret")
        self.assertEqual(state,BASE)
        self.assertIs(http.trust_env,False)
        self.assertEqual(http.proxies,{})
        transport.close_session.assert_called_once()
        auth.scoped_wslpe_resolution.assert_called_once_with("172.28.231.31")

    def test_remote_query_is_read_only(self):
        script=MOD.READ_ONLY_JEA
        for necessary in ("Get-PSSessionConfiguration","Get-Service","Get-LocalUser",
                          "PartOfDomain","Get-LocalGroupMember","WSLPE_JEA_PREFLIGHT_JSON="):
            self.assertIn(necessary,script)
        for forbidden in ("Register-PSSessionConfiguration","Unregister-PSSessionConfiguration",
                          "Restart-Service","Stop-Service","Set-Service",
                          "Set-ItemProperty","New-Item","Remove-Item",
                          "vmrun","GOAD-WS01","10.4.10.31"):
            self.assertNotIn(forbidden,script)
        self.assertIn("checked_certificate(",SCRIPT.read_text())
        self.assertNotIn('server_cert_validation="ignore"',SCRIPT.read_text())

if __name__=="__main__":
    unittest.main()
