import pytest
from registry_auditor.ingest import CreditRecord, load_records, load_dataset
from registry_auditor.detectors import (
    Finding,
    detect_duplicate_serials,
    detect_double_retirement,
    detect_retired_then_traded,
    detect_quantity_mismatch,
    near_misses,
)
from registry_auditor.audit import (
    run_audit,
    canonical_report,
    report_hash,
)
from registry_auditor.anchor import LocalChainFixture, audit_and_anchor


class TestFixtureDataset:
    """Test 1: Fixture dataset includes all 4 planned finding kinds."""

    def test_fixture_finds_all_error_kinds(self):
        """Load fixture and verify all 4 error kinds are detected."""
        records = load_dataset("fixtures/registry_fixture.json")
        report = run_audit(records)

        finding_kinds = set(f["kind"] for f in report["findings"])

        assert "duplicate_serial" in finding_kinds
        assert "double_retirement" in finding_kinds
        assert "retired_then_traded" in finding_kinds
        assert "quantity_mismatch" in finding_kinds

    def test_fixture_findings_have_evidence(self):
        """Every finding in fixture must have non-empty evidence."""
        records = load_dataset("fixtures/registry_fixture.json")
        report = run_audit(records)

        for finding in report["findings"]:
            assert finding["serials"], "Finding has no serials"
            assert finding["evidence"], "Finding has no evidence"
            assert len(finding["evidence"]) > 0, "Evidence list is empty"


class TestCleanDataset:
    """Test 2: Clean dataset returns zero substantiated findings."""

    def test_clean_dataset_no_findings(self):
        """Construct 3 clean credits (matching near-miss patterns) → no findings."""
        records = [
            CreditRecord(
                serial="CLEAN-1",
                project="Project X",
                vintage=2022,
                quantity=100,
                events=[
                    {"type": "issued", "qty": 100, "actor": "issuer", "date": "2022-01-01"},
                    {"type": "retired", "qty": 100, "actor": "retirer", "date": "2023-01-01"},
                ],
            ),
            CreditRecord(
                serial="CLEAN-2",
                project="Project X",
                vintage=2022,
                quantity=50,
                events=[
                    {"type": "issued", "qty": 50, "actor": "issuer", "date": "2022-02-01"},
                    {"type": "retired", "qty": 50, "actor": "retirer", "date": "2023-02-01"},
                ],
            ),
            CreditRecord(
                serial="CLEAN-3",
                project="Project Y",
                vintage=2021,
                quantity=150,
                events=[
                    {"type": "issued", "qty": 150, "actor": "issuer", "date": "2021-01-01"},
                    {"type": "transferred", "qty": 75, "actor": "trader", "date": "2022-06-01"},
                    {"type": "retired", "qty": 75, "actor": "retirer", "date": "2023-06-01"},
                ],
            ),
        ]

        report = run_audit(records)

        assert report["findings"] == []
        assert report["clean"] is True
        assert len(report["near_misses"]) > 0

    def test_clean_dataset_has_near_misses(self):
        """Clean dataset should identify near-miss patterns with explanations."""
        records = [
            CreditRecord(
                serial="CLEAN-1",
                project="Project X",
                vintage=2022,
                quantity=100,
                events=[
                    {"type": "issued", "qty": 100, "actor": "issuer", "date": "2022-01-01"},
                    {"type": "retired", "qty": 100, "actor": "retirer", "date": "2023-01-01"},
                ],
            ),
        ]

        report = run_audit(records)

        # Should identify clean_full_retirement pattern
        near_miss_patterns = [n["pattern"] for n in report["near_misses"]]
        assert "clean_full_retirement" in near_miss_patterns

        # Each near-miss has explanation
        for nm in report["near_misses"]:
            assert "why_not_a_finding" in nm
            assert len(nm["why_not_a_finding"]) > 0


class TestEvidenceIntegrity:
    """Test 3: Evidence carries actual record/event data."""

    def test_double_retirement_evidence_has_both_events(self):
        """Double retirement finding must include both retired events in evidence."""
        records = [
            CreditRecord(
                serial="DBL-RET",
                project="Project",
                vintage=2020,
                quantity=200,
                events=[
                    {"type": "issued", "qty": 200, "actor": "issuer", "date": "2020-01-01"},
                    {"type": "retired", "qty": 100, "actor": "ret1", "date": "2021-06-01"},
                    {"type": "retired", "qty": 100, "actor": "ret2", "date": "2021-07-01"},
                ],
            ),
        ]

        findings = detect_double_retirement(records)

        assert len(findings) == 1
        finding = findings[0]

        # Evidence should contain both retired events
        retired_in_evidence = [
            e for e in finding.evidence if e.get("event_type") == "retired"
        ]
        assert len(retired_in_evidence) == 2
        assert retired_in_evidence[0]["event_date"] == "2021-06-01"
        assert retired_in_evidence[1]["event_date"] == "2021-07-01"


class TestHashDeterminism:
    """Test 4: Hash is deterministic across different batch_ids."""

    def test_same_records_produce_same_hash(self):
        """Two audits of same records with different batch_ids → identical hash."""
        records = [
            CreditRecord(
                serial="TEST-1",
                project="Test",
                vintage=2020,
                quantity=100,
                events=[
                    {"type": "issued", "qty": 100, "actor": "issuer", "date": "2020-01-01"},
                ],
            ),
        ]

        report1 = run_audit(records, batch_id="batch-aaa")
        report2 = run_audit(records, batch_id="batch-bbb")

        hash1 = report_hash(report1)
        hash2 = report_hash(report2)

        assert hash1 == hash2
        assert report1["batch_id"] != report2["batch_id"]


class TestAnchorRoundtrip:
    """Test 5: Audit → anchor → verify roundtrip."""

    def test_anchor_roundtrip(self):
        """Run audit, anchor it, verify the receipt and verification."""
        records = load_dataset("fixtures/registry_fixture.json")
        chain = LocalChainFixture()

        result = audit_and_anchor(records, chain)

        assert "report" in result
        assert "receipt" in result
        assert "verification" in result

        report = result["report"]
        receipt = result["receipt"]
        verification = result["verification"]

        # Receipt has required fields
        assert "tx_id" in receipt
        assert "block" in receipt
        assert "timestamp" in receipt
        assert receipt["block"] > 1_000_000

        # Verification shows match and anchored
        assert verification["match"] is True
        assert verification["anchored"] is True
        assert verification["commitment"] is not None


class TestTamperDetection:
    """Test 6: Tampering with a finding causes match=False."""

    def test_tamper_detection(self):
        """Modify a finding explanation, verify report → match becomes False."""
        records = load_dataset("fixtures/registry_fixture.json")
        chain = LocalChainFixture()

        result = audit_and_anchor(records, chain)
        original_report = result["report"]

        # Make a tampered copy: modify a finding explanation
        tampered = {
            "batch_id": original_report["batch_id"],
            "generated_from": original_report["generated_from"],
            "findings": [
                {
                    **f,
                    "explanation": f["explanation"] + " TAMPERED"
                    if f["explanation"]
                    else "TAMPERED",
                }
                for f in original_report["findings"]
            ],
            "finding_counts": original_report["finding_counts"],
            "near_misses": original_report["near_misses"],
            "records_checked": original_report["records_checked"],
            "clean": original_report["clean"],
        }

        # Verify the tampered report
        verification = chain.verify_report(tampered)

        assert verification["match"] is False
        assert verification["anchored"] is False


class TestIdempotentCommit:
    """Test 7: Committing the same hash twice returns the original receipt."""

    def test_idempotent_commit(self):
        """Commit hash H, then commit H again → same block number."""
        chain = LocalChainFixture()

        test_hash = "abcd1234" * 8  # 64 hex chars

        receipt1 = chain.commit(test_hash)
        receipt2 = chain.commit(test_hash)

        assert receipt1["block"] == receipt2["block"]
        assert receipt1["tx_id"] == receipt2["tx_id"]
        assert receipt1["timestamp"] == receipt2["timestamp"]


class TestIngestValidation:
    """Test 8: Ingest validation raises on missing serial or negative quantity."""

    def test_missing_serial_raises(self):
        """Record without serial field raises ValueError."""
        records_data = [{"project": "X", "vintage": 2020, "quantity": 100}]

        with pytest.raises(ValueError, match="serial"):
            load_records(records_data)

    def test_negative_quantity_raises(self):
        """Record with negative quantity raises ValueError."""
        records_data = [
            {
                "serial": "NEG-1",
                "project": "X",
                "vintage": 2020,
                "quantity": -50,
            }
        ]

        with pytest.raises(ValueError, match="negative"):
            load_records(records_data)


class TestRetiredThenTradedOrder:
    """Test 9: Detector respects event order (transfer before retirement is OK)."""

    def test_transfer_before_retirement_no_finding(self):
        """Transfer before retirement → no retired_then_traded finding."""
        records = [
            CreditRecord(
                serial="ORDER-TEST",
                project="Test",
                vintage=2020,
                quantity=100,
                events=[
                    {"type": "issued", "qty": 100, "actor": "issuer", "date": "2020-01-01"},
                    {"type": "transferred", "qty": 100, "actor": "trader", "date": "2021-06-01"},
                    {"type": "retired", "qty": 100, "actor": "retirer", "date": "2022-06-01"},
                ],
            ),
        ]

        findings = detect_retired_then_traded(records)

        assert len(findings) == 0

    def test_transfer_after_retirement_fires_finding(self):
        """Transfer after retirement → retired_then_traded finding."""
        records = [
            CreditRecord(
                serial="ORDER-TEST-2",
                project="Test",
                vintage=2020,
                quantity=100,
                events=[
                    {"type": "issued", "qty": 100, "actor": "issuer", "date": "2020-01-01"},
                    {"type": "retired", "qty": 100, "actor": "retirer", "date": "2021-06-01"},
                    {"type": "transferred", "qty": 100, "actor": "trader", "date": "2022-06-01"},
                ],
            ),
        ]

        findings = detect_retired_then_traded(records)

        assert len(findings) == 1
        assert findings[0].kind == "retired_then_traded"
