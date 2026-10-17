from registry_auditor.audit import run_audit, report_hash


class LocalChainFixture:
    """
    LOCAL FIXTURE — simulates AuditAnchor contract semantics in memory.
    NOT a blockchain. Replaced by the testnet deployment at the same interface.

    This fixture provides deterministic commitment semantics for testing and
    development: block counter, timestamp derivation, and idempotent hashing.
    """

    def __init__(self):
        """Initialize the fixture with block counter and empty commitments."""
        self.block_counter = 1_000_000
        self.commitments = {}  # hash -> {hash, block, timestamp, committer}

    def commit(self, report_hash_hex: str, committer: str = "auditor") -> dict:
        """
        Commit a report hash.

        Increments block counter, derives deterministic timestamp from block,
        stores commitment, returns receipt.

        Idempotent: committing the same hash twice returns the ORIGINAL receipt.

        Args:
            report_hash_hex: SHA-256 hex string of the canonical report
            committer: the entity committing (default: "auditor")

        Returns:
            Receipt dict: {tx_id, block, timestamp}
        """
        if report_hash_hex in self.commitments:
            # Idempotent: return the original commitment
            commitment = self.commitments[report_hash_hex]
            return {
                "tx_id": commitment["tx_id"],
                "block": commitment["block"],
                "timestamp": commitment["timestamp"],
            }

        # New commitment
        self.block_counter += 1
        block = self.block_counter
        timestamp = 1_760_000_000 + block  # deterministic derivation
        tx_id = f"local-fixture-tx-{block}"

        self.commitments[report_hash_hex] = {
            "hash": report_hash_hex,
            "block": block,
            "timestamp": timestamp,
            "committer": committer,
            "tx_id": tx_id,
        }

        return {
            "tx_id": tx_id,
            "block": block,
            "timestamp": timestamp,
        }

    def verify(self, report_hash_hex: str) -> dict:
        """
        Verify if a report hash is anchored.

        Args:
            report_hash_hex: SHA-256 hex string to verify

        Returns:
            Dict: {"anchored": bool, "commitment": commitment_dict_or_None}
        """
        if report_hash_hex in self.commitments:
            return {
                "anchored": True,
                "commitment": self.commitments[report_hash_hex],
            }
        return {
            "anchored": False,
            "commitment": None,
        }

    def verify_report(self, report: dict) -> dict:
        """
        Recompute the hash from a report and verify its anchoredness.

        A tampered report (any finding edited) will produce match=False
        because its recomputed hash differs from the committed one.
        In that case, anchored refers to the RECOMPUTED hash (False).

        Args:
            report: the audit report dict (may be tampered)

        Returns:
            Dict: {
                "match": bool (hash in report matches recomputed),
                "anchored": bool (recomputed hash is in commitments),
                "commitment": commitment_or_None,
                "recomputed_hash": the freshly computed hash
            }
        """
        recomputed = report_hash(report)
        committed_match = False
        commitment = None

        if recomputed in self.commitments:
            committed_match = True
            commitment = self.commitments[recomputed]

        return {
            "match": committed_match,
            "anchored": committed_match,
            "commitment": commitment,
            "recomputed_hash": recomputed,
        }


def audit_and_anchor(records, chain: LocalChainFixture) -> dict:
    """
    Run an audit on records and immediately anchor the report hash.

    Args:
        records: list of CreditRecord objects
        chain: a LocalChainFixture instance (or compatible interface)

    Returns:
        Dict with:
        - report: the audit report
        - receipt: the commitment receipt
        - verification: result of chain.verify_report(report)
    """
    report = run_audit(records)
    receipt = chain.commit(report_hash(report))
    verification = chain.verify_report(report)

    return {
        "report": report,
        "receipt": receipt,
        "verification": verification,
    }
