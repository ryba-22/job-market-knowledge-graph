"""Priority human packet combines independent control and AI domain disputes without leaking predictions."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from ingestion import classification03_ai_priority as priority

def original(i):
    id=str(60000+i)
    return {
        "posting_id":id,"revision_id":"rev"+id,"raw_payload_sha256":"sha"+id,
        "source":"aplikuj","source_url":"https://www.aplikuj.pl/oferta/"+id+"/example",
        "title":"IT Developer" if i%2 else "Salesperson",
        "source_industry":"Informatyk",
        "description":"Coding in Python and SQL." if i%2 else "Customer sales and invoices.",
    }

def test_priority_selection_blinds_and_freezes(tmp_path):
    rows=[original(i) for i in range(69)]
    root=tmp_path/"c03";root.mkdir()
    (root/"reviewer-human.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
    controls=[row["posting_id"] for row in rows[:40]]
    domain=[row["posting_id"] for row in rows[:5]+rows[40:47]]
    (root/"silver-human-triage-manifest.json").write_text(json.dumps({"human_controls":controls}))
    (root/"ai-domain-third-v1").mkdir()
    (root/"ai-domain-third-v1"/"comparison.json").write_text(json.dumps({"disputed_ids":domain}))
    res=priority.prepare(root,None)
    assert res["human_review_priority_unique"]==47
    assert res["model_labels_hidden"] is True
    packet=[json.loads(x) for x in (root/"reviewer-priority-human.jsonl").read_text().splitlines()]
    assert len(packet)==47 and len({r["posting_id"] for r in packet})==47
    assert all("ai_label" not in r and "classifier_status" not in r for r in packet)
    assert "IT_CONFIRMED" not in (root/"reviewer-priority-human.html").read_text()
    assert priority.score(root)["status"]=="BLOCKED_NO_HUMAN_PRIORITY_REVIEWS"
    assert priority.prepare(root,None)["human_review_priority_unique"]==47
    altered=domain[:11]+[rows[48]["posting_id"]]
    (root/"ai-domain-third-v1"/"comparison.json").write_text(json.dumps({"disputed_ids":altered}))
    with pytest.raises(ValueError,match="locked priority selection differs"):
        priority.prepare(root,None)
