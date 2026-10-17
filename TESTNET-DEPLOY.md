# AuditAnchor — testnet deployment kit ($0)

The contract (`contracts/AuditAnchor.sol`) is finished: commitment-only,
no tokens, no funds. Deploying it needs exactly one thing this repo cannot
create for you: a throwaway testnet wallet key (keys are created by the
account holder alone, never by a tool).

## Prove readiness first (local, $0, no wallet needed)
Run `.venv/bin/python scripts/deploy_preflight.py` from the repo root. It
checks the contract's structure, recomputes the exact bytes32 the deploy
must commit (the fixture report's canonical SHA-256, `0x`-prefixed), and
re-runs the local-fixture verification (anchored match=True, tampered
match=False). Expected final line: "READY — everything except the wallet
signature is proven." Verified 2026-10-16: READY, exit code 0, commit
argument `0xe0c3bd15343afa8a7b6fc4fde628576f62ef9820ba22c71c2fbf502b77f4ca17`
(the fixture dataset's report hash — a real registry batch would print its
own).

## The one manual step (account holder) (~5 minutes, once)
1. In a wallet he controls (e.g. MetaMask): create a NEW throwaway account
   labeled "climatechain-testnet". Never reuse any funded wallet.
2. Fund it with Sepolia test ETH from a public faucet (e.g. the Google
   Cloud / Alchemy Sepolia faucets) — test ETH has no value.
3. Put the account ADDRESS (public information) in
   `scripts/deploy_config.json` — copy `deploy_config.example.json` and
   replace the zero address. The private key never enters chat or a file;
   deployment runs in the browser session (Remix) or on the account holder's
   machine. Re-run the preflight: it confirms the address drop-in.

## Deploy (Remix route — no local toolchain needed)
1. Open remix.ethereum.org → paste `contracts/AuditAnchor.sol` → compile (0.8.20).
2. Deploy & Run → environment "Injected Provider" (the throwaway account),
   network Sepolia → Deploy. Record: contract address + deploy tx hash.
3. Call `commit(bytes32)` with the report hash printed by
   `scripts/deploy_preflight.py` (or `scripts/verify_report.py`, prefix
   `0x`). Record the commit tx hash.
4. Write both into `scripts/deployment.json`:
   `{"network":"sepolia","contract_address":"0x…","deploy_tx":"0x…","commit_tx":"0x…","explorer_url":"https://sepolia.etherscan.io/address/0x…"}`
   `verify_report.py` picks this file up automatically and prints it, and
   re-running `scripts/make_dashboard.py` makes the dashboard show the
   testnet contract + explorer link instead of the fixture label.

## Foundry route (if forge is installed on the deploy machine)
```bash
forge create contracts/AuditAnchor.sol:AuditAnchor --rpc-url $SEPOLIA_RPC --private-key $TESTNET_KEY
```
Same recording step afterward.

## Honesty line for the submission
Until deployment.json exists, the submission text says the anchor runs on
the labeled local fixture with the contract ready — which is true, scores
less on Technical Execution, and is never dressed as a testnet deployment.
