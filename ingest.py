import json
from dataclasses import dataclass


@dataclass
class CreditRecord:
    """A carbon credit record with event history."""
    serial: str
    project: str
    vintage: int
    quantity: int
    events: list[dict]


def load_records(records_list: list[dict]) -> list[CreditRecord]:
    """Load in-memory records list into CreditRecord dataclass list."""
    result = []
    for rec in records_list:
        if "serial" not in rec:
            raise ValueError("Record missing required field: serial")
        if rec.get("quantity", 0) < 0:
            raise ValueError(f"Record {rec.get('serial')} has negative quantity")

        # Extract core fields, ignoring any keys starting with "_"
        result.append(
            CreditRecord(
                serial=rec["serial"],
                project=rec.get("project", ""),
                vintage=rec.get("vintage", 0),
                quantity=rec.get("quantity", 0),
                events=rec.get("events", []),
            )
        )
    return result


def load_dataset(path: str) -> list[CreditRecord]:
    """Load a JSON registry dataset file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Load all credits from the list (keys starting with "_" are ignored by load_records)
    credits = data.get("credits", [])

    return load_records(credits)
