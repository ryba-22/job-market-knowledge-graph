"""No-network regression tests for AI-silver classification and human triage."""
from __future__ import annotations

import json
from pathlib import Path
from hashlib import sha256
from collections import Counter
import pytest

from ingestion import classification03_ai as ai
from ingestion import classification03_triage as triage


def packet(i):
    id=str(5000+i)
    return {
        "posting_id":id,
        "revision_id":"rev-"+id,"raw_payload_sha256":"sha-"+id,
        "source":"aplikuj","source_url":"https://www.aplikuj.pl/oferta/"+id+"/example",
        "source_industry":"Informatyk" if i%2 else "Inny",
        "title":"Frontend Developer" if i%2 else "Magazynier",
        "description":"Tworzenie aplikacji przy użyciu Python i API." if i%2 else "Obsługa magazynu oraz kompletacja zamówień.",
    }


def candidate(row, label, confidence="high"):
    return {
        "posting_id":row["posting_id"],
        "label":label,"family":"software_engineering" if label=="IT_TECHNICAL" else ("transport_logistics" if label=="NON_IT" else "other"),
        "evidence_field":"description" if label in ("IT_TECHNICAL","NON_IT") else "",
        "quote":row["description"][:35] if label in ("IT_TECHNICAL","NON_IT") else "",
        "notes":"Duties cross multiple domains." if label=="IT_ADJACENT" else ("Insufficient source material." if label=="UNDETERMINABLE" else "Source duty shows the role."),
        "confidence":confidence,
    }


def test_silver_anchoring_and_identity_guards():
    items=[packet(0),packet(1)]
    assessed=[candidate(items[0],"NON_IT"),candidate(items[1],"IT_TECHNICAL")]
    result=ai.validate_model_output(items,{"annotations":assessed})
    assert len(result)==2 and result[0]["origin"]=="AI_SILVER_NOT_HUMAN_GOLD"
    assert all(x["revision_id"].startswith("rev-") for x in result)
    with pytest.raises(ValueError,match="identities"):
        ai.validate_model_output(items,{"annotations":[assessed[0],assessed[0]]})
    with pytest.raises(ValueError,match="ungrounded"):
        ai.validate_model_output(items,{"annotations":[assessed[0],assessed[1]|{"quote":"Nie istnieje w źródle."}]})
    with pytest.raises(ValueError,match="actual source duties"):
        ai.validate_model_output(items,{"annotations":[assessed[0],assessed[1]|{"evidence_field":"title","quote":"Frontend Developer"}]})


def test_silver_raises_on_skipped_rows():
    items=[packet(0),packet(1)]
    with pytest.raises(ValueError,match="skipped"):
        ai.validate_model_output(items,{"annotations":[candidate(items[0],"NON_IT")]})


def test_triage_samples_40_controls_blinds_human_and_blocks_leaks(tmp_path,monkeypatch):
    packets=[packet(i) for i in range(200)]
    root=tmp_path/"c03";root.mkdir()
    (root/"reviewer-a.jsonl").write_text("".join(json.dumps(r)+"\n" for r in packets))
    labels={}
    selection=[]
    # Synthetic frozen sample: 160 probability, 40 challenge, quota 45/45/70.
    for i,p in enumerate(packets):
        if i<45:status="IT_CONFIRMED"
        elif i<90:status="NON_IT_CONFIRMED"
        elif i<160:status="REVIEW_REQUIRED"
        else:status="IT_CONFIRMED"
        labels[p["posting_id"]]=status
        selection.append({
            "posting_id":p["posting_id"],
            "panel":"probability" if i<160 else "challenge",
            "stratum":status,
        })
    (root/"private-sample-manifest.json").write_text(json.dumps({"selection":selection}))
    side=tmp_path/"silver";side.mkdir()
    silver=[]
    for i,r in enumerate(packets):
        label="IT_TECHNICAL" if i%2 else "NON_IT"
        if i in (2,4,6):label="IT_ADJACENT"
        row=ai.validate_model_output([r],{"annotations":[candidate(r,label,confidence="low" if i==9 else "high")]})[0]
        silver.append(row)
    (side/"silver-annotations.jsonl").write_text("".join(json.dumps(x)+"\n" for x in silver))
    model={x["posting_id"]:{"assessment":{"status":labels[x["posting_id"]]}} for x in packets}
    original={x["posting_id"]:{"revision_id":x["revision_id"],"raw_payload_sha256":x["raw_payload_sha256"]} for x in packets}
    monkeypatch.setattr(triage,"load_verified_population",lambda: (original,model))
    report=triage.triage(root,side,None)
    assert report["status"]=="HUMAN_REVIEW_QUEUE_READY_GOLD_STILL_BLOCKED"
    assert report["ai_silver_count"]==200
    assert report["stratified_random_control_unique"]==40
    assert report["high_priority_flagged_unique"]>=3
    assert report["human_queue_unique"]>=40
    source_by_id={r["posting_id"]:r for r in packets}
    sent=[json.loads(line) for line in (root/"reviewer-human.jsonl").read_text().splitlines() if line]
    assert all(row==source_by_id[row["posting_id"]] for row in sent)
    html=(root/"reviewer-human.html").read_text()
    assert "IT_CONFIRMED" not in html and "NON_IT_CONFIRMED" not in html and "REVIEW_REQUIRED" not in html
    assert "AI_SILVER_NOT_HUMAN_GOLD" not in html
    # The selected worklist is locked, deterministic and cannot be resampled silently.
    assert triage.triage(root,side,None)["human_queue_unique"]==len(sent)
    pool=[json.loads(line) for line in (side/"silver-annotations.jsonl").read_text().splitlines()]
    present={r["posting_id"] for r in sent}
    mutate=next(x for x in pool if x["posting_id"] not in present and x["confidence"]=="high")
    mutate["confidence"]="low"
    (side/"silver-annotations.jsonl").write_text("".join(json.dumps(x)+"\n" for x in pool))
    with pytest.raises(ValueError,match="queue changed"):
        triage.triage(root,side,None)


def test_human_scoring_blocks_without_reviews(tmp_path):
    r=tmp_path/"c03";r.mkdir()
    assert triage.human_compare(r,tmp_path/"silver")["status"]=="BLOCKED_NO_TRIAGE"
    (r/"reviewer-human.jsonl").write_text(json.dumps(packet(1))+"\n")
    assert triage.human_compare(r,tmp_path/"silver")["status"]=="BLOCKED_NO_HUMAN_REVIEWS"
