#!/usr/bin/env python3
"""WSLPE41 learner-acceptance inventory and freeze gate; NO live exploits yet.

Source-only planning is supported. A future adapter framework must prove each
scenario from lpe.trainee and only on a verified disposable clone. This script
never supplies a privileged action or claims learner acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms import wslpe45_deploy21 as deployment
from kingdoms import wslpe45_batch_operator as batch

FREEZE_SNAPSHOT = "KINGDOMS-WSLPE41-CONFIG-VALIDATED"
EXCLUDED = {25,36,38,40}


def scenario_manifest() -> list[dict]:
    source = ROOT / "ansible/roles/windows_lpe/defaults/main.yml"
    if source.is_symlink() or not source.is_file():
        raise batch.BatchBlocked("Standalone baseline catalog not from trusted source")
    records = yaml.safe_load(source.read_text(encoding="utf-8"))
    original = records.get("windows_lpe_implemented_techniques")
    if (not isinstance(original,list) or len(original)!=20
            or len(set(original))!=20
            or not all(isinstance(n,str) and re.fullmatch(r"[a-z_]+",n) for n in original)):
        raise batch.BatchBlocked("Expected exact 20 shared foundation identifiers")
    additions = deployment.selection()
    if (len(additions)!=21 or
            {item["number"] for item in additions} != set(range(21,46))-EXCLUDED):
        raise batch.BatchBlocked("Expected exact approved 21 additions")
    rows = [{"number":i,"id":name,"family":"foundation",
             "configuration":"OPERATOR_BASELINE","learner":"NOT_TESTED"}
            for i,name in enumerate(original,1)]
    rows.extend({"number":row["number"],"id":row["id"],"family":"additional",
                 "configuration":"DEPLOYMENT_PASS","learner":"NOT_TESTED"}
                for row in additions)
    if (len(rows)!=41 or len({r["id"] for r in rows})!=41
            or len({r["number"] for r in rows})!=41):
        raise batch.BatchBlocked("WSLPE41 identity collision or cardinality mismatch")
    return rows


def verify_receipt(path: str, root: Path | None = None) -> dict:
    private_root = root or batch.make_private_dir(str(deployment.STATE))
    target = Path(path).expanduser()
    if (target.parent != private_root or not re.fullmatch(
            r"wslpe41-freeze-[a-f0-9]{16}\.json", target.name)):
        raise batch.BatchBlocked("Freeze receipt must reside in original private journal directory")
    receipt = json.loads(deployment.read_private_evidence(target))
    if (receipt.get("schema")!="kingdoms.wslpe41.freeze.v1"
            or receipt.get("status")!="PASS"
            or receipt.get("snapshot")!=FREEZE_SNAPSHOT
            or receipt.get("deployed_source_commit")!=deployment.helper("wslpe41-freeze.py").SOURCE
            or receipt.get("fingerprint")!=deployment.helper("wslpe41-freeze.py").FINGERPRINT
            or receipt.get("learner_exploitation")!="NOT_TESTED"):
        raise batch.BatchBlocked("Unverified or incomplete WSLPE41 frozen-master receipt")
    return receipt


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json",action="store_true",help="Print complete 41-scenario source-only acceptance matrix")
    parser.add_argument("--freeze-receipt",help="Explicit already-verified frozen-master receipt (local evidence gate only)")
    args=parser.parse_args(argv)
    rows=scenario_manifest()
    if args.freeze_receipt:
        receipt=verify_receipt(args.freeze_receipt)
        frozen=f"RECEIPT_VERIFIED: {receipt['snapshot']}"
    else:
        frozen="FREEZE_RECEIPT_REQUIRED"
    if args.json:
        print(json.dumps({"schema":"kingdoms.wslpe41.acceptance-plan.v1",
                          "target":"WSLPE-WS01","active_count":41,
                          "excluded":sorted(EXCLUDED),"freeze":frozen,
                          "learner_pass_count":0,"scenarios":rows},indent=2))
    else:
        print(f"[PLAN] WSLPE41: {len(rows)} unique scenarios, exclusions 25/36/38/40")
        print(f"[FREEZE] {frozen}")
        print("[LEARNER] 0 demonstrated by this plan; individual lpe.trainee proof adapters pending")
        print("[SAFETY] Source-only: no WinRM, VMware, reset, privilege escalation or admin impersonation")
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (OSError,ValueError,KeyError) as e:
        print("[BLOCKED] Cannot establish exact WSLPE41 acceptance plan: "+str(e),file=sys.stderr)
        raise SystemExit(2)
