"""Checks evaluation abstention, missing-claim accounting, and revision safety."""
import json

from scripts.ri01_score import evaluate


def make_review_inputs(tmp_path):
    posting = {"posting_id": "board:123", "revision_id": "abc"}
    claim1 = {"assertion_id": "a", "posting_id": "board:123", "modality_candidate": "MUST"}
    claim2 = {"assertion_id": "b", "posting_id": "board:123", "modality_candidate": "NICE"}
    packets = tmp_path / "packets.jsonl"
    assertions = tmp_path / "claims.jsonl"
    export = tmp_path / "review.json"
    packets.write_text(json.dumps(posting) + "\n")
    assertions.write_text(json.dumps(claim1) + "\n" + json.dumps(claim2) + "\n")
    return packets, assertions, export


def test_no_manual_review_is_blocked(tmp_path):
    packets, assertions, export = make_review_inputs(tmp_path)
    export.write_text(json.dumps({"format": "ri01-manual-reviews-v1", "reviews": []}))
    result = evaluate(export, packets, assertions)
    assert result["status"] == "NO_MANUAL_GOLD"
    assert result["release_gate"] == "BLOCKED"
    assert result["precision"] is None and result["recall"] is None


def test_count_false_positives_and_manual_omissions_separately(tmp_path):
    packets, assertions, export = make_review_inputs(tmp_path)
    export.write_text(json.dumps({"format": "ri01-manual-reviews-v1", "reviews": [{
        "posting_id": "board:123", "revision_id": "abc", "review_status": "REVIEWED",
        "reviewer": "independent-01", "decisions": {"a": "ACCEPT", "b": "REJECT"},
        "missing": "TASK | Need to maintain the API", "notes": ""
    }]}))
    result = evaluate(export, packets, assertions)
    assert result["tp_accepted_candidates"] == 1
    assert result["fp_rejected_candidates"] == 1
    assert result["fn_manually_added_assertions"] == 1
    assert result["precision"] == 0.5 and result["recall"] == 0.5
    assert result["release_gate"] == "BLOCKED"


def test_revision_mismatch_invalidates_review(tmp_path):
    packets, assertions, export = make_review_inputs(tmp_path)
    export.write_text(json.dumps({"format": "ri01-manual-reviews-v1", "reviews": [{
        "posting_id": "board:123", "revision_id": "stale",
        "review_status": "REVIEWED", "reviewer": "reviewer",
        "decisions": {"a": "ACCEPT", "b": "ACCEPT"}, "missing": ""
    }]}))
    result = evaluate(export, packets, assertions)
    assert result["reviewed_postings"] == 0
    assert result["errors"] and "Revision mismatch" in result["errors"][0]
