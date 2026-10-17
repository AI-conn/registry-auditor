import hashlib
import json
import uuid
from registry_auditor.ingest import load_dataset
from registry_auditor.detectors import (
    detect_duplicate_serials,
    detect_double_retirement,
    detect_retired_then_traded,
    detect_quantity_mismatch,
    near_misses,
)


def run_audit(records, batch_id=None) -> dict:
    """
    Run a complete audit on a list of CreditRecord objects.

    Args:
        records: list of CreditRecord objects
        batch_id: optional UUID hex string (defaults to uuid4 hex if not provided)

    Returns:
        A report dict with structure:
        {
            "batch_id": str,
            "generated_from": int (record count),
            "findings": [finding dicts],
            "finding_counts": {kind: count},
            "near_misses": [...],
            "records_checked": int,
            "clean": bool (True if findings is empty)
        }

    Note: batch_id is included in the report but EXCLUDED from the canonical hash.
    """
    if batch_id is None:
        batch_id = uuid.uuid4().hex

    # Run all detectors
    all_findings = []
    all_findings.extend(detect_duplicate_serials(records))
    all_findings.extend(detect_double_retirement(records))
    all_findings.extend(detect_retired_then_traded(records))
    all_findings.extend(detect_quantity_mismatch(records))

    # Convert Finding dataclass objects to dicts
    finding_dicts = [
        {
            "kind": f.kind,
            "serials": f.serials,
            "evidence": f.evidence,
            "explanation": f.explanation,
        }
        for f in all_findings
    ]

    # Count findings by kind
    finding_counts = {}
    for f in finding_dicts:
        kind = f["kind"]
        finding_counts[kind] = finding_counts.get(kind, 0) + 1

    # Get near-miss patterns
    near_miss_patterns = near_misses(records)

    report = {
        "batch_id": batch_id,
        "generated_from": len(records),
        "findings": finding_dicts,
        "finding_counts": finding_counts,
        "near_misses": near_miss_patterns,
        "records_checked": len(records),
        "clean": len(finding_dicts) == 0,
    }

    return report


def canonical_report(report: dict) -> str:
    """
    Return the canonical JSON form of a report (without batch_id).

    Deterministic ordering: json.dumps with sort_keys=True, separators=(",", ":"),
    ensure_ascii=True.
    """
    # Make a copy without batch_id
    canonical = {k: v for k, v in report.items() if k != "batch_id"}

    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def report_hash(report: dict) -> str:
    """
    Return the SHA-256 hex digest of the canonical report form.
    """
    canonical = canonical_report(report)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_audit_file(path: str) -> dict:
    """
    Load a dataset file and run audit on it.

    Returns the report dict.
    """
    records = load_dataset(path)
    return run_audit(records)
