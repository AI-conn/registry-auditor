#!/usr/bin/env python3
"""Generate the static audit dashboard (dashboard.html).

Usage (from repo root):
  .venv/bin/python scripts/make_dashboard.py [--dataset fixtures/registry_fixture.json] [--out dashboard.html]

Runs the audit on each dataset, anchors every report through the local
chain fixture, computes the tamper demonstration, and writes ONE
self-contained HTML file (no server, no external assets). If
scripts/deployment.json exists (written by the testnet deploy step), the
dashboard shows the testnet contract + explorer link instead of the
fixture label.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from registry_auditor.dashboard import write_dashboard  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", action="append", default=None,
                    help="dataset JSON (repeatable); default: the synthetic fixture")
    ap.add_argument("--out", default="dashboard.html")
    args = ap.parse_args()

    datasets = args.dataset or ["fixtures/registry_fixture.json"]
    dep_path = Path(__file__).with_name("deployment.json")
    deployment = json.loads(dep_path.read_text()) if dep_path.exists() else None

    batches = write_dashboard(args.out, datasets, deployment=deployment)
    for b in batches:
        print(f"dataset         : {b['dataset']}")
        print(f"records_checked : {b['report']['records_checked']}")
        print(f"finding_counts  : {b['report']['finding_counts']}")
        print(f"report_hash     : {b['hash']}")
        print(f"anchored        : {b['verification']['anchored']} "
              f"({'testnet deployment shown' if deployment else 'local fixture, labeled'})")
        print(f"tamper verify   : match={b['tamper_verification']['match']} (must be False)")
    print(f"dashboard       : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
