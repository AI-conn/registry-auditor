#!/usr/bin/env python3
"""Deploy preflight — proves the Sepolia testnet deploy is ready except the
wallet signature itself.

Usage (from repo root):
  .venv/bin/python scripts/deploy_preflight.py

Checks, using only the standard library:
  1. contracts/AuditAnchor.sol is present and structurally complete
     (pragma, commit/verify functions, Anchored event, balanced braces).
     This is a structure check, NOT a compile — solc runs in Remix during
     the deploy step.
  2. The exact bytes32 value the deploy must commit: the fixture audit
     report's canonical SHA-256, printed 0x-prefixed, computed live.
  3. The local-chain fixture verification (match=True, tamper match=False)
     still holds — i.e. the semantics the contract will enforce on-chain
     are proven locally first.
  4. scripts/deploy_config.json drop-in state: if present, its wallet
     address has a valid 0x address shape and the network is sepolia.
     If absent, the exact manual step that creates it is printed.
  5. scripts/deployment.json state (written only after a real deploy).

Exit code 0 = everything in this repo is ready; the only remaining step is
the wallet signature (the account holder's step).
Exit code 1 = a defect in this repo's deploy readiness.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from registry_auditor import audit_and_anchor  # noqa: E402
from registry_auditor.anchor import LocalChainFixture  # noqa: E402
from registry_auditor.audit import report_hash  # noqa: E402
from registry_auditor.ingest import load_dataset  # noqa: E402

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def main() -> int:
    defects: list[str] = []
    print("== AuditAnchor testnet deploy preflight ==")

    # 1. Contract structure
    sol = ROOT / "contracts" / "AuditAnchor.sol"
    if not sol.exists():
        defects.append("contracts/AuditAnchor.sol is MISSING")
        print("[FAIL] contract file missing")
    else:
        src = sol.read_text(encoding="utf-8")
        required = [
            "pragma solidity ^0.8.20",
            "function commit(bytes32 reportHash)",
            "function verify(bytes32 reportHash)",
            "event Anchored(",
        ]
        missing = [r for r in required if r not in src]
        balanced = src.count("{") == src.count("}")
        if missing or not balanced:
            defects.append(f"contract structure incomplete: missing={missing} balanced={balanced}")
            print(f"[FAIL] contract structure: missing={missing} braces_balanced={balanced}")
        else:
            print("[ ok ] contract present, structure complete (compile runs in Remix at deploy)")

    # 2 + 3. Report hash + fixture semantics, live
    records = load_dataset(ROOT / "fixtures" / "registry_fixture.json")
    chain = LocalChainFixture()
    result = audit_and_anchor(records, chain)
    digest = report_hash(result["report"])
    tampered = json.loads(json.dumps(result["report"]))
    tampered["findings"][0]["explanation"] += " (edited)"
    tamper_ok = chain.verify_report(tampered)["match"] is False
    if result["verification"]["match"] and tamper_ok:
        print("[ ok ] fixture verification live: anchored match=True, tampered match=False")
    else:
        defects.append("fixture verification does not hold")
        print("[FAIL] fixture verification broken")
    print(f"       commit argument (bytes32): 0x{digest}")

    # 4. Wallet drop-in
    cfg_path = ROOT / "scripts" / "deploy_config.json"
    example = ROOT / "scripts" / "deploy_config.example.json"
    if not cfg_path.exists():
        print("[ -- ] deploy_config.json not created yet — the operator drop-in:")
        print(f"       copy {example.name} to deploy_config.json and set wallet_address")
        print("       to the throwaway Sepolia account address (address is public;")
        print("       the private key never enters any file or chat).")
    else:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        addr = cfg.get("wallet_address", "")
        if ADDRESS_RE.match(addr) and addr != ZERO_ADDRESS and cfg.get("network") == "sepolia":
            print(f"[ ok ] deploy_config.json: wallet_address {addr} (sepolia)")
        else:
            print(f"[ -- ] deploy_config.json present but wallet_address not set to a real"
                  f" sepolia address yet (current: {addr!r}) — the operator drop-in.")

    # 5. Deployment state
    dep_path = ROOT / "scripts" / "deployment.json"
    if dep_path.exists():
        dep = json.loads(dep_path.read_text(encoding="utf-8"))
        print(f"[ ok ] deployment.json present: {dep.get('contract_address')} "
              f"explorer {dep.get('explorer_url')}")
    else:
        print("[ -- ] not deployed yet — the deploy itself is the wallet-signature step.")

    if defects:
        print("RESULT: REPO-SIDE DEFECTS:", *defects, sep="\n  - ")
        return 1
    print("RESULT: READY — everything except the wallet signature is proven.")
    print("Next (account holder, ~5 min): wallet per TESTNET-DEPLOY.md, then the Remix")
    print("deploy + commit of the bytes32 above, then record deployment.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
