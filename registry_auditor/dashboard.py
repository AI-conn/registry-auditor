"""Static audit dashboard — Registry Auditor's verification view.

Renders a completed audit batch (report + anchor receipt + verification +
tamper demonstration) as ONE self-contained HTML file: no external assets,
no server, no dependencies beyond the standard library. A judge can open it
from the repo and, with the embedded verification panel, recompute the
report's canonical SHA-256 in the browser and check it against the anchored
hash — the same check `scripts/verify_report.py` performs in Python.

Honesty rules baked in:
- The local chain fixture is labeled as a fixture wherever it appears; a
  testnet deployment (scripts/deployment.json) is shown as testnet, with
  its explorer link, only when that file exists.
- The tamper block shows a real edited copy of the report and its real
  recomputed verification result (match=False), computed at build time.
"""
from __future__ import annotations

import html
import json

from .anchor import LocalChainFixture
from .audit import canonical_report, report_hash, run_audit


def build_batch(records, dataset_label: str, chain: LocalChainFixture | None = None) -> dict:
    """Run one audit batch end to end: audit → anchor → verify → tamper demo."""
    chain = chain or LocalChainFixture()
    report = run_audit(records)
    digest = report_hash(report)
    receipt = chain.commit(digest)
    verification = chain.verify_report(report)

    tampered = json.loads(json.dumps(report))
    tamper_note = None
    if tampered["findings"]:
        original = tampered["findings"][0]["explanation"]
        tampered["findings"][0]["explanation"] = original + " (edited after anchoring)"
        tamper_note = {
            "field": "findings[0].explanation",
            "original": original,
            "edited": tampered["findings"][0]["explanation"],
        }
    tamper_verification = chain.verify_report(tampered)

    return {
        "dataset": dataset_label,
        "report": report,
        "canonical": canonical_report(report),
        "hash": digest,
        "receipt": receipt,
        "verification": verification,
        "tampered_report": tampered,
        "tamper_note": tamper_note,
        "tamper_verification": tamper_verification,
    }


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _pretty(obj) -> str:
    return _esc(json.dumps(obj, indent=2, ensure_ascii=False))


def _finding_rows(report: dict) -> str:
    if not report["findings"]:
        return '<p class="clean">No substantiated findings. This dataset is clean.</p>'
    out = []
    for i, f in enumerate(report["findings"], 1):
        out.append(
            '<article class="finding">'
            f'<h4><span class="badge">{_esc(f["kind"])}</span> Finding {i}</h4>'
            f'<p><strong>Serials:</strong> {_esc(", ".join(f["serials"]))}</p>'
            f'<p>{_esc(f["explanation"])}</p>'
            f'<details><summary>Evidence records ({len(f["evidence"])})</summary>'
            f'<pre>{_pretty(f["evidence"])}</pre></details>'
            "</article>"
        )
    return "\n".join(out)


def _near_miss_rows(report: dict) -> str:
    if not report["near_misses"]:
        return "<p>None recorded for this batch.</p>"
    out = []
    for nm in report["near_misses"]:
        out.append(
            '<article class="near-miss">'
            f'<h4>{_esc(nm["pattern"])}</h4>'
            f'<p><strong>Serials:</strong> {_esc(", ".join(nm["serials"]))}</p>'
            f'<p>{_esc(nm["why_not_a_finding"])}</p>'
            "</article>"
        )
    return "\n".join(out)


# In-browser verifier: replicates registry_auditor.audit.canonical_report
# byte-for-byte (report minus batch_id, keys sorted, separators "," and ":",
# ensure_ascii escaping incl. \uXXXX for non-ASCII and control characters).
# Non-integer numbers fall back to JS String(n); audit reports carry ints,
# strings, booleans, null, lists and dicts by construction.
_JS_VERIFIER = r"""
function pyCanonical(value) {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "number") {
    if (!isFinite(value)) throw new Error("non-finite number");
    return String(value);
  }
  if (typeof value === "string") return pyString(value);
  if (Array.isArray(value)) return "[" + value.map(pyCanonical).join(",") + "]";
  var keys = Object.keys(value).sort();
  return "{" + keys.map(function (k) { return pyString(k) + ":" + pyCanonical(value[k]); }).join(",") + "}";
}
function pyString(s) {
  var out = '"';
  for (var i = 0; i < s.length; i++) {
    var c = s.charCodeAt(i);
    if (c === 0x22) out += '\\"';
    else if (c === 0x5c) out += "\\\\";
    else if (c === 0x08) out += "\\b";
    else if (c === 0x0c) out += "\\f";
    else if (c === 0x0a) out += "\\n";
    else if (c === 0x0d) out += "\\r";
    else if (c === 0x09) out += "\\t";
    else if (c < 0x20 || c > 0x7e) out += "\\u" + c.toString(16).padStart(4, "0");
    else out += s[i];
  }
  return out + '"';
}
async function sha256Hex(text) {
  var buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, "0"); }).join("");
}
async function verifyBatch(idx, anchoredHash, resultId) {
  var el = document.getElementById(resultId);
  try {
    var report = JSON.parse(document.getElementById("report-" + idx).textContent);
    delete report.batch_id;
    var canonical = pyCanonical(report);
    var digest = await sha256Hex(canonical);
    var ok = digest === anchoredHash;
    el.textContent = (ok ? "MATCH — recomputed hash equals the anchored hash: " : "MISMATCH — recomputed hash: ") + digest;
    el.className = ok ? "verify-ok" : "verify-bad";
  } catch (e) {
    el.textContent = "Verification error: " + e.message;
    el.className = "verify-bad";
  }
}
"""


def render_dashboard(batches: list[dict], deployment: dict | None = None) -> str:
    """Render the full dashboard HTML for one or more audit batches."""
    history_rows = []
    sections = []
    for idx, b in enumerate(batches):
        report = b["report"]
        counts = report["finding_counts"]
        total_findings = sum(counts.values())
        history_rows.append(
            "<tr>"
            f"<td>{idx + 1}</td><td>{_esc(b['dataset'])}</td>"
            f"<td>{report['records_checked']}</td><td>{total_findings}</td>"
            f"<td><code>{_esc(b['hash'][:16])}…</code></td>"
            f"<td>{'yes' if b['verification']['anchored'] else 'no'}</td>"
            "</tr>"
        )
        counts_line = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        if deployment:
            anchor_block = (
                f'<p><strong>Testnet deployment:</strong> contract '
                f'<code>{_esc(deployment.get("contract_address"))}</code> on '
                f'{_esc(deployment.get("network", "sepolia"))} — '
                f'<a href="{_esc(deployment.get("explorer_url", ""))}">explorer</a>. '
                f'Deploy tx <code>{_esc(deployment.get("deploy_tx"))}</code>, '
                f'commit tx <code>{_esc(deployment.get("commit_tx"))}</code>.</p>'
            )
        else:
            r = b["receipt"]
            anchor_block = (
                '<p><strong>Anchor:</strong> LOCAL FIXTURE (in-memory simulation of the '
                "AuditAnchor contract — not a blockchain). "
                f"Receipt: tx <code>{_esc(r['tx_id'])}</code>, block {r['block']}, "
                f"timestamp {r['timestamp']}. The same report hash is what the testnet "
                "deployment commits on-chain (see scripts/TESTNET-DEPLOY.md).</p>"
            )
        tamper_block = ""
        if b["tamper_note"]:
            tv = b["tamper_verification"]
            tamper_block = (
                '<div class="tamper"><h4>Tamper demonstration (computed at build time)</h4>'
                f'<p>One field of a copy of this report was edited after anchoring — '
                f'<code>{_esc(b["tamper_note"]["field"])}</code>: “{_esc(b["tamper_note"]["edited"])}”</p>'
                f'<p>Recomputed hash: <code>{_esc(tv["recomputed_hash"])}</code><br>'
                f'Verification of the edited copy: <strong>match = {tv["match"]}</strong> '
                "(must be False — the edited report is not the anchored report).</p></div>"
            )
        sections.append(
            f'<section class="batch" id="batch-{idx}">'
            f"<h2>Batch {idx + 1} — {_esc(b['dataset'])}</h2>"
            f'<p>Records checked: <strong>{report["records_checked"]}</strong> · '
            f"Clean: <strong>{report['clean']}</strong> · Findings by kind: {_esc(counts_line)}</p>"
            f'<p>Report hash (SHA-256 of canonical report): <code>{_esc(b["hash"])}</code></p>'
            + anchor_block
            + "<h3>Findings — every finding quotes its evidence</h3>"
            + _finding_rows(report)
            + "<h3>Near-misses — suspicious, and explained as legitimate</h3>"
            + _near_miss_rows(report)
            + tamper_block
            + '<div class="verify"><h3>Verify this report yourself</h3>'
            "<p>Recompute the canonical SHA-256 of the report shown on this page, "
            "in your browser, and compare it with the anchored hash above.</p>"
            f'<button onclick="verifyBatch({idx}, \'{_esc(b["hash"])}\', \'verify-result-{idx}\')">'
            "Recompute &amp; verify</button>"
            f'<p id="verify-result-{idx}" class="verify-pending">Not run yet.</p></div>'
            f'<script type="application/json" id="report-{idx}">'
            # Raw embed (script content is raw text — HTML entities are NOT
            # decoded there); only the </script> sequence is neutralized,
            # which JSON.parse accepts as an escaped solidus.
            + json.dumps(report, ensure_ascii=False).replace("</", "<\\/")
            + "</script>"
            "</section>"
        )

    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<title>Registry Auditor — Audit Dashboard</title>\n<style>\n"
        "body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:2rem auto;max-width:960px;padding:0 1rem;color:#1b1f23;line-height:1.5}"
        "h1{margin-bottom:.2rem}.sub{color:#57606a;margin-top:0}"
        "table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #d0d7de;padding:.4rem .6rem;text-align:left}th{background:#f6f8fa}"
        "section.batch{border:1px solid #d0d7de;border-radius:8px;padding:1rem 1.25rem;margin:1.5rem 0}"
        ".finding,.near-miss{border-left:4px solid #cf222e;background:#fff8f8;padding:.5rem .9rem;margin:.7rem 0}"
        ".near-miss{border-left-color:#bf8700;background:#fffdf5}"
        ".badge{background:#cf222e;color:#fff;border-radius:4px;padding:.05rem .45rem;font-size:.85em}"
        "pre{background:#f6f8fa;padding:.7rem;overflow-x:auto;border-radius:6px}"
        "code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.92em;word-break:break-all}"
        ".tamper{border:1px dashed #bf8700;border-radius:6px;padding:.6rem .9rem;margin:1rem 0}"
        ".verify{border-top:1px solid #d0d7de;margin-top:1rem;padding-top:.5rem}"
        "button{background:#0969da;color:#fff;border:0;border-radius:6px;padding:.5rem 1rem;cursor:pointer}"
        ".verify-ok{color:#1a7f37;font-weight:600}.verify-bad{color:#cf222e;font-weight:600}.clean{color:#1a7f37;font-weight:600}"
        "</style>\n</head>\n<body>\n"
        "<h1>Registry Auditor — Audit Dashboard</h1>\n"
        '<p class="sub">Carbon-credit registry double-counting audit · '
        "IEEE ClimateChain — Carbon Markets &amp; Emissions Transparency track. "
        "Every finding quotes its evidence records; every report is canonically "
        "hashed (SHA-256) and anchored. The shipped dataset is SYNTHETIC and "
        "labeled as such in its file.</p>\n"
        "<h2>Batch history</h2>\n<table><tr><th>#</th><th>Dataset</th><th>Records</th>"
        "<th>Findings</th><th>Report hash</th><th>Anchored</th></tr>\n"
        + "\n".join(history_rows)
        + "\n</table>\n"
        + "\n".join(sections)
        + "\n<script>" + _JS_VERIFIER + "</script>\n</body>\n</html>\n"
    )


def write_dashboard(out_path, dataset_paths, deployment: dict | None = None) -> list[dict]:
    """Build batches from dataset files and write the dashboard HTML."""
    from .ingest import load_dataset  # local import: keeps module import light

    batches = [build_batch(load_dataset(p), str(p)) for p in dataset_paths]
    html_text = render_dashboard(batches, deployment=deployment)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    return batches
