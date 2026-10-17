#!/usr/bin/env python3
"""Verification view — the judge-runnable check for Registry Auditor.

Usage (from repo root):
  .venv/bin/python scripts/verify_report.py [--dataset fixtures/registry_fixture.json]

Runs the audit on the dataset, anchors the report hash through the local
chain fixture, verifies it, then tampers one finding and verifies again —
printing match=True followed by match=False. If a testnet deployment exists
(scripts/deployment.json, written by the deploy step), its contract address,
transaction, and explorer URL are printed so a judge can check the on-chain
commitment independently.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from registry_auditor import audit_and_anchor  # noqa: E402
from registry_auditor.anchor import LocalChainFixture  # noqa: E402
from registry_auditor.audit import report_hash  # noqa: E402
from registry_auditor.ingest import load_dataset  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fixtures/registry_fixture.json")
    args = ap.parse_args()

    records = load_dataset(args.dataset)
    chain = LocalChainFixture()
    result = audit_and_anchor(records, chain)
    report = result["report"]
    print(f"records_checked : {report['records_checked']}")
    print(f"finding_counts  : {report['finding_counts']}")
    print(f"report_hash     : {report_hash(report)}")
    print(f"anchored (local fixture): {result['verification']}")

    tampered = json.loads(json.dumps(report))
    if tampered["findings"]:
        tampered["findings"][0]["explanation"] += " (edited)"
        print(f"tampered verify : {chain.verify_report(tampered)}  <- match must be False")

    dep = Path(__file__).with_name("deployment.json")
    if dep.exists():
        d = json.loads(dep.read_text())
        print(f"testnet contract: {d.get('contract_address')}  tx: {d.get('deploy_tx')}")
        print(f"explorer        : {d.get('explorer_url')}")
    else:
        print("testnet         : not deployed yet — see scripts/TESTNET-DEPLOY.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
