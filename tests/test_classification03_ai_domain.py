"""AI domain-review remains source-only and cannot authorize a human-gold gate."""
from __future__ import annotations
import json
from pathlib import Path
import pytest

from ingestion import classification03_ai_domain as third

def source(i):
    ident=f"case{i:02}"
    return {
        "posting_id":ident,"revision_id":f"rev{i}","raw_payload_sha256":f"hash{i}",
        "source":"aplikuj","source_url":f"https://www.aplikuj.pl/oferta/{ident}/example",
        "title":"Software Developer" if i%2 else "IT sales",
        "source_industry":"Informatyk",
        "description":"Develop web APIs in Python." if i%2 else "Sell IT software solutions to customers.",
    }

def ai_annotation(row):
    label="IT_TECHNICAL" if "Developer" in row["title"] else "NON_IT"
    return {
        "posting_id":row["posting_id"],
        "revision_id":row["revision_id"],"raw_payload_sha256":row["raw_payload_sha256"],
        "label":label,"family":"software_engineering" if label=="IT_TECHNICAL" else "tech_sales",
        "quote":row["description"][:32],"evidence_field":"description",
        "notes":"Source job duties.","confidence":"high",
        "origin":"AI_SILVER_NOT_HUMAN_GOLD","policy_version":"diagnostic",
    }

def test_domain_model_only_sees_blinded_source_and_outputs_12(tmp_path,monkeypatch):
    original=[source(i) for i in range(12)]
    monkeypatch.setattr(third,"source_candidates",lambda:original)
    prompts=[]
    def fake_ai(records,model,timeout=300):
        assert model=="opus"
        assert all(set(r)==set(original[0]) for r in records)
        assert all(not any(p in r for p in ("first_ai_label","second_ai_label","classifier_status")) for r in records)
        prompts.append([r["posting_id"] for r in records])
        return [ai_annotation(r) for r in records],{"cost_usd":0,"duration_ms":1}
    monkeypatch.setattr(third,"call_ai",fake_ai)
    folder=tmp_path/"third"
    result=third.run(folder,"opus")
    assert result["items"]==12
    assert result["requires_real_human_adjudication"] is True
    assert len(prompts)==3
    assert len((folder/"annotations.jsonl").read_text().splitlines())==12
    result2=third.run(folder,"opus")
    assert result2["items"]==12
    assert len(prompts)==3
    with pytest.raises(ValueError,match="checkpoint differs"):
        third.run(folder,"sonnet")

def test_union_of_critical_and_disputes_can_only_reference_source(tmp_path):
    root=tmp_path/"source";root.mkdir()
    entries=[source(i) for i in range(69)]
    (root/"reviewer-human.jsonl").write_text("".join(json.dumps(r)+"\n" for r in entries))
    (root/"ai-blind-second-v1").mkdir()
    (root/"ai-blind-second-v1"/"comparison.json").write_text(json.dumps({
        "disputed_ids":[r["posting_id"] for r in entries[:10]]
    }))
    (root/"silver-human-triage-manifest.json").write_text(json.dumps({
        "selected":[{"posting_id":r["posting_id"],
                     "reasons":["CRITICAL_DISAGREEMENT"] if i in (8,9,10,11) else ["CONTROL_STRATIFIED"]}
                    for i,r in enumerate(entries)]
    }))
    res=third.source_candidates(root)
    assert len(res)==12
    assert all("reasons" not in x and "ai_label" not in x for x in res)
    doc=json.loads((root/"ai-blind-second-v1"/"comparison.json").read_text())
    doc["disputed_ids"][-1]="not-a-source-id"
    (root/"ai-blind-second-v1"/"comparison.json").write_text(json.dumps(doc))
    with pytest.raises(ValueError,match="outside 69 locked"):
        third.source_candidates(root)
