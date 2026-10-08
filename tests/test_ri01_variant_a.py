"""RI-01 option A: user-approved, pinned, non-destructive selection contracts."""
import gzip
import json
from collections import Counter
from pathlib import Path

from ingestion.requirement_intelligence import classify_title, identity
from ingestion.ri01_replacement import evidence_eligibility, REPLACEMENT_QUOTA
from tests.test_ri01 import mk

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/evals/ri01-variant-a-selection.json"


def test_option_a_manifest_pins_original_and_exact_replacements():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["format"] == "ri01-variant-a-v1" and data["decision"] == "A"
    original = {x["posting_id"] for x in data["original_200"]}
    kept = {x["posting_id"] for x in data["kept"]}
    removed = {x["posting_id"] for x in data["removed"]}
    replacements = {x["posting_id"] for x in data["replacement"]}
    assert len(original) == 200
    assert len(kept) == 150 and len(removed) == 50 and len(replacements) == 50
    assert original == kept | removed
    assert kept.isdisjoint(removed)
    assert replacements.isdisjoint(original)
    assert Counter(x["source"] for x in data["removed"]) == {"itleaders": 10, "pracuj": 20, "teamquest": 20}
    assert Counter(x["source"] for x in data["replacement"]) == REPLACEMENT_QUOTA
    assert all(x["quality"]["eligible"] and x["quality"]["description_chars"] >= 900
               and x["quality"]["source_fragments"] >= 5 for x in data["replacement"])
    assert all(x["quality"]["family_candidate"] != "nontechnical" for x in data["replacement"])


def test_frozen_corpus_revisions_match_all_200_new_selected():
    plan = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {x["posting_id"]: x["revision_id"] for x in plan["kept"] + plan["replacement"]}
    present = {}
    with gzip.open(ROOT / plan["corpus"], "rt", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            key = identity(record)
            if key in expected:
                present[key] = record.get("revision_id")
    assert present == expected


def test_non_it_platforma_does_not_become_platform_engineering():
    assert classify_title("PPC Specialist - Platforma Marketingowa") == "nontechnical"
    assert classify_title("Senior Platform Engineer Kubernetes") == "platform_devops"
    assert classify_title("Fullstack Developer") == "backend_fullstack"


def test_metadata_only_record_is_ineligible():
    record = mk(source="solidjobs", sem={"title": "Backend Developer"})
    assert evidence_eligibility(record)["eligible"] is False


def test_structured_requirement_record_eligible():
    record = mk(source="nofluffjobs", sem={
        "jobposting_json_ld": {"description": "<p>" + ("Responsibilities and design secure systems. " * 50) + "</p>"},
        "requirements": {
            "description": "<h3>Requirements</h3><ul><li>Practical knowledge of Python and SQL</li><li>Practical experience with production APIs</li></ul>",
            "musts": [{"value": "Python"}, {"value": "SQL"}],
            "nices": [{"value": "Docker"}],
        },
        "specs": {"dailyTasks": ["Build API", "Review code"]},
    })
    assert evidence_eligibility(record)["eligible"]


def test_pinned_selection_corrected_ppc_false_positive():
    plan = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert plan["selection_correction"]["rejected_posting_id"] == "solidjobs:36214"
    assert "solidjobs:36214" not in {x["posting_id"] for x in plan["replacement"]}
