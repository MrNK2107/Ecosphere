"""
Unit tests for cognition engine — heuristic extraction.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cognition import extract_heuristic, detect_conflicts, detect_gaps


class TestHeuristicExtraction:
    def test_u001_fact_extraction(self):
        seg = {"id": "u-001", "text": "I am Priya, SRE Lead. Payments are failing hard — error rate spiked to 12% at checkout since 14:02 UTC.", "speakerName": "Priya", "role": "SRE"}
        result = extract_heuristic(seg, "payment-001")
        assert len(result) == 1
        assert result[0]["kind"] == "Fact"
        assert "12%" in result[0]["statement"]
        assert result[0]["status"] == "Reported"

    def test_u002_fact_extraction(self):
        seg = {"id": "u-002", "text": "Copy, I checked Datadog — DB replica lag on payments-db-03 is 45 seconds.", "speakerName": "Alex", "role": "Backend"}
        result = extract_heuristic(seg, "payment-001")
        assert len(result) == 1
        assert result[0]["kind"] == "Fact"
        assert "replica lag" in result[0]["statement"].lower()

    def test_u004_hypothesis_extraction(self):
        seg = {"id": "u-004", "text": "I think it's a recent deploy that caused this — maybe the retry logic merged at 13:40?", "speakerName": "Alex", "role": "Backend"}
        result = extract_heuristic(seg, "payment-001")
        assert len(result) == 1
        assert result[0]["kind"] == "Hypothesis"
        assert result[0]["status"] == "Active"

    def test_u007_decision_extraction(self):
        seg = {"id": "u-007", "text": "Let's rollback the payment service to v2.14.3 — that rev reverts the retry change.", "speakerName": "Priya", "role": "SRE"}
        result = extract_heuristic(seg, "payment-001")
        assert len(result) == 1
        assert result[0]["kind"] == "Decision"
        assert result[0]["status"] == "Proposed"

    def test_u010_action_extraction(self):
        seg = {"id": "u-010", "text": "Can someone create a Jira to track the DB replica fix? Assign to Backend, due in 30 minutes.", "speakerName": "Alex", "role": "Backend"}
        result = extract_heuristic(seg, "payment-001")
        assert len(result) == 1
        assert result[0]["kind"] == "ActionItem"
        assert "jira" in result[0].get("toolKey", "").lower()

    def test_u006_chatter(self):
        seg = {"id": "u-006", "text": "Comms here — should we send a status page update?", "speakerName": "Maya", "role": "Comms"}
        result = extract_heuristic(seg, "payment-001")
        assert len(result) == 0

    def test_u009_chatter(self):
        seg = {"id": "u-009", "text": "Conflicting — I still see 12% at 14:06. Alex, what time window are you looking at?", "speakerName": "Priya", "role": "SRE"}
        result = extract_heuristic(seg, "payment-001")
        assert len(result) == 0


class TestConflictDetection:
    def test_detects_percentage_conflicts(self):
        facts = [
            {"id": "f1", "statement": "Error rate is 12%", "status": "Reported"},
            {"id": "f2", "statement": "Error rate dropped to 2%", "status": "Reported"},
        ]
        gaps = detect_conflicts(facts)
        assert len(gaps) >= 1
        assert gaps[0]["kind"] == "ConflictingInfo"

    def test_no_conflict_same_value(self):
        facts = [
            {"id": "f1", "statement": "Error rate is 12%", "status": "Reported"},
            {"id": "f2", "statement": "Error rate is 12%", "status": "Corroborated"},
        ]
        gaps = detect_conflicts(facts)
        assert len(gaps) == 0


class TestGapDetection:
    def test_missing_owner_gap(self):
        snapshot = {
            "actions": [
                {"id": "a1", "title": "Fix DB", "status": "Open", "ownerId": None, "ownerName": None},
            ],
            "hypotheses": [],
        }
        gaps = detect_gaps(snapshot)
        assert any(g["kind"] == "MissingOwner" for g in gaps)

    def test_unverified_hypothesis_gap(self):
        snapshot = {
            "actions": [],
            "hypotheses": [
                {"id": "h1", "statement": "Deploy caused outage", "status": "Active"},
            ],
        }
        gaps = detect_gaps(snapshot)
        assert any(g["kind"] == "UnverifiedAssumption" for g in gaps)

    def test_no_gaps_clean_snapshot(self):
        snapshot = {
            "actions": [
                {"id": "a1", "title": "Fix DB", "status": "Done", "ownerName": "Alex"},
            ],
            "hypotheses": [
                {"id": "h1", "statement": "Deploy caused outage", "status": "Disproven"},
            ],
        }
        gaps = detect_gaps(snapshot)
        assert len(gaps) == 0
