"""Model-assisted RI-01 annotation contracts without invoking external models."""
import json
from types import SimpleNamespace

from scripts import ri01_ai_firstpass as first
from scripts import ri01_ai_disputes_ui as disputes


def sample():
    return {
        "posting_id": "nofluffjobs:fixture", "title": "Engineer", "company": "Example",
        "url": "https://example.invalid/job", "revision_id": "rev-01",
        "split": "development", "full_text": "Python is mandatory. Docker is a plus.",
        "source": "nofluffjobs",
    }


def test_model_firstpass_preserves_unanchored_quote_not_as_ground_truth(tmp_path, monkeypatch):
    monkeypatch.setattr(first, "WORK", tmp_path)
    reply = {
        "annotations": [{
            "id": "nofluffjobs:fixture",
            "items": [
                {"kind": "MUST", "quote": "Python is mandatory.", "concept": "Python", "certainty": "high"},
                {"kind": "NICE", "quote": "Docker is required.", "concept": "Docker", "certainty": "high"},
            ],
        }],
    }
    called = []
    def fake_model(*args, **kwargs):
        called.append(args)
        return SimpleNamespace(stdout=json.dumps(reply), stderr="", returncode=0)
    monkeypatch.setattr(first.subprocess, "run", fake_model)
    out = first.request(1, [sample()], True)
    assert out["status"] == "MODEL_DRAFT_NOT_GOLD"
    assert out["invalid_quotes"] == 1
    assert out["assertions"][0]["source_exact"] is True
    assert out["assertions"][1]["source_exact"] is False
    assert all(x["review_status"] == "MODEL_DRAFT_UNVERIFIED" for x in out["assertions"])
    again = first.request(1, [sample()], True)
    assert again == out and len(called) == 1


def test_firstpass_detects_changed_source_input(tmp_path, monkeypatch):
    monkeypatch.setattr(first, "WORK", tmp_path)
    saved = tmp_path / "draft-001.json"
    saved.write_text(json.dumps({"prompt_sha256": "wrong"}))
    try:
        first.request(1, [sample()], False)
        assert False, "Expected mismatch"
    except ValueError as exc:
        assert "input mismatch" in str(exc)


def test_dispute_ui_escapes_untrusted_job_text():
    cases = [{
        "posting_id": "a:b", "source": "a", "title": "<script>alert(9)</script>",
        "url": "https://example.invalid", "quote": "<img src=x onerror=alert(9)>",
        "priority": "P0", "reasons": ["TEST"], "model_label": "MUST",
        "extractor_labels": ["UNKNOWN"],
    }]
    page = disputes.render(cases)
    assert "alert(9)</script>" not in page
    assert "\\u003cscript" in page
    assert "ri01-dispute-review-v1" in page
