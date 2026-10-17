from dataclasses import dataclass


@dataclass
class Finding:
    """A substantiated audit finding with evidence."""
    kind: str
    serials: list[str]
    evidence: list[dict]
    explanation: str


def detect_duplicate_serials(records) -> list[Finding]:
    """
    Find credits with duplicate serial strings.

    Two or more distinct credit records sharing the same serial.
    """
    serials_seen = {}
    findings = []

    for record in records:
        if record.serial in serials_seen:
            serials_seen[record.serial].append(record)
        else:
            serials_seen[record.serial] = [record]

    duplicates = {s: recs for s, recs in serials_seen.items() if len(recs) > 1}

    for serial, recs in duplicates.items():
        evidence = [
            {
                "serial": rec.serial,
                "project": rec.project,
                "vintage": rec.vintage,
                "quantity": rec.quantity,
                "record_count": len(recs)
            }
            for rec in recs
        ]
        findings.append(
            Finding(
                kind="duplicate_serial",
                serials=[serial],
                evidence=evidence,
                explanation=f"Serial '{serial}' appears on {len(recs)} distinct credit records.",
            )
        )

    return findings


def detect_double_retirement(records) -> list[Finding]:
    """
    Find credits with multiple retired events.

    A single credit record with 2+ events of type 'retired'.
    """
    findings = []

    for record in records:
        retired_events = [e for e in record.events if e.get("type") == "retired"]

        if len(retired_events) > 1:
            evidence = [
                {
                    "serial": record.serial,
                    "event_type": "retired",
                    "event_qty": e.get("qty"),
                    "event_actor": e.get("actor"),
                    "event_date": e.get("date"),
                }
                for e in retired_events
            ]
            findings.append(
                Finding(
                    kind="double_retirement",
                    serials=[record.serial],
                    evidence=evidence,
                    explanation=f"Credit {record.serial} has {len(retired_events)} retirement events.",
                )
            )

    return findings


def detect_retired_then_traded(records) -> list[Finding]:
    """
    Find credits where a transferred event occurs after retirement.

    A 'transferred' event whose date is after a 'retired' event on the same credit.
    """
    findings = []

    for record in records:
        retired_events = [e for e in record.events if e.get("type") == "retired"]
        transferred_events = [e for e in record.events if e.get("type") == "transferred"]

        if not retired_events or not transferred_events:
            continue

        # For simplicity, compare strings; assumes ISO date format (YYYY-MM-DD)
        latest_retirement = max(e.get("date", "") for e in retired_events)

        offending_transfers = [
            e for e in transferred_events
            if e.get("date", "") > latest_retirement
        ]

        if offending_transfers:
            evidence = [
                {
                    "serial": record.serial,
                    "retired_event": {
                        "type": "retired",
                        "date": e.get("date"),
                        "qty": e.get("qty"),
                    }
                }
                for e in retired_events
            ] + [
                {
                    "serial": record.serial,
                    "transferred_event": {
                        "type": "transferred",
                        "date": e.get("date"),
                        "qty": e.get("qty"),
                    }
                }
                for e in offending_transfers
            ]
            findings.append(
                Finding(
                    kind="retired_then_traded",
                    serials=[record.serial],
                    evidence=evidence,
                    explanation=f"Credit {record.serial} transferred after retirement.",
                )
            )

    return findings


def detect_quantity_mismatch(records) -> list[Finding]:
    """
    Find credits where retired + transferred-out qty exceeds issued qty.

    The issued quantity is the qty of the 'issued' event if present,
    otherwise the record's quantity field.
    """
    findings = []

    for record in records:
        issued_event = next((e for e in record.events if e.get("type") == "issued"), None)
        issued_qty = issued_event.get("qty") if issued_event else record.quantity

        retired_qty = sum(
            e.get("qty", 0) for e in record.events if e.get("type") == "retired"
        )
        transferred_out_qty = sum(
            e.get("qty", 0) for e in record.events if e.get("type") == "transferred"
        )

        total_out = retired_qty + transferred_out_qty

        if total_out > issued_qty:
            evidence = [
                {
                    "serial": record.serial,
                    "issued_qty": issued_qty,
                    "retired_qty": retired_qty,
                    "transferred_out_qty": transferred_out_qty,
                    "total_out": total_out,
                    "events": record.events,
                }
            ]
            findings.append(
                Finding(
                    kind="quantity_mismatch",
                    serials=[record.serial],
                    evidence=evidence,
                    explanation=f"Credit {record.serial}: issued {issued_qty}, "
                                f"but retired {retired_qty} + transferred {transferred_out_qty} = {total_out}.",
                )
            )

    return findings


def near_misses(records) -> list[dict]:
    """
    Find suspicious-but-legitimate patterns that are NOT findings.

    Returns list of dicts, each with pattern, serials, and why_not_a_finding explanation.
    """
    patterns = []

    # Pattern A: Two credits sharing project+vintage but distinct serials.
    project_vintage_map = {}
    for record in records:
        key = (record.project, record.vintage)
        if key not in project_vintage_map:
            project_vintage_map[key] = []
        project_vintage_map[key].append(record)

    for (proj, vint), recs in project_vintage_map.items():
        if len(recs) > 1 and len(set(r.serial for r in recs)) > 1:
            patterns.append(
                {
                    "pattern": "multiple_credits_same_project_vintage",
                    "serials": [r.serial for r in recs],
                    "why_not_a_finding": "Multiple credits from the same project and vintage year is legitimate; "
                                         "each maintains its own serial and lifecycle.",
                }
            )

    # Pattern B: A credit retired exactly once for its full quantity (clean full retirement).
    for record in records:
        retired_events = [e for e in record.events if e.get("type") == "retired"]

        if len(retired_events) == 1:
            retired_qty = retired_events[0].get("qty", 0)
            if retired_qty == record.quantity:
                patterns.append(
                    {
                        "pattern": "clean_full_retirement",
                        "serials": [record.serial],
                        "why_not_a_finding": "Credit retired exactly once for its full quantity; "
                                            "this is the normal end-of-life for a consumed credit.",
                    }
                )

    # Pattern C: Transfers that all occur before retirement.
    for record in records:
        retired_events = [e for e in record.events if e.get("type") == "retired"]
        transferred_events = [e for e in record.events if e.get("type") == "transferred"]

        if retired_events and transferred_events:
            earliest_retirement = min(e.get("date", "") for e in retired_events)
            all_transfers_before = all(
                e.get("date", "") < earliest_retirement for e in transferred_events
            )

            if all_transfers_before:
                patterns.append(
                    {
                        "pattern": "transfers_before_retirement",
                        "serials": [record.serial],
                        "why_not_a_finding": "All transfers occur before retirement; "
                                            "the credit changed hands and was then retired by the final owner.",
                    }
                )

    return patterns
