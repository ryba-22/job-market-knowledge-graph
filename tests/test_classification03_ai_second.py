"""Second blind AI review is silver only, fully source-reconciled, resumable."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from ingestion import classification03_ai_second as mod

def source(i):
    id=str(40000+i)
    return {
        "posting_id":id,"revision_id":f"rev-{id}","raw_payload_sha256":f"sha-{id}",
        "source":"aplikuj","source_url":f"https://www.aplikuj.pl/oferta/{id}/test",
        "title":"Frontend Developer" if i%2 else "Warehouse Operator",
        "source_industry":"Informatyk" if i%2 else "Magazynier",
        "description":"Designing software applications with Python." if i%2 else "Physical picking and packing shipments.",
    }

def evaluation(row,label):
    return {
        "posting_id":row["posting_id"],"revision_id":row["revision_id"],
        "raw_payload_sha256":row["raw_payload_sha256"],"label":label,
        "family":"software_engineering" if label=="IT_TECHNICAL" else "transport_logistics",
        "evidence_field":"description","quote":row["description"][:40],
        "notes":"Evidence from original job duties.","confidence":"high",
        "origin":"SECOND_BLIND_AI_NOT_HUMAN_GOLD",
        "policy_version":mod.VERSION,
    }

def test_second_pass_source_only_and_resumable(tmp_path,monkeypatch):
    cohort=[source(i) for i in range(69)]
    packet=tmp_path/"triage.jsonl"
    packet.write_text("".join(json.dumps(x)+"\n" for x in cohort))
    monkeypatch.setattr(mod,"PACKET",packet)
    monkeypatch.setattr(mod,"read_items",lambda path=packet:cohort)
    calls=[]
    def fake_ai(items,model,timeout=240):
        calls.append([x["posting_id"] for x in items])
        assert model=="sonnet"
        assert all("classifier_status" not in x and "ai_label" not in x for x in items)
        return ([evaluation(x,"IT_TECHNICAL" if x["title"]=="Frontend Developer" else "NON_IT") for x in items],
                {"model":"sonnet","cost_usd":0,"duration_ms":1,"usage":None,"n":len(items)})
    monkeypatch.setattr(mod,"call_ai",fake_ai)
    out=tmp_path/"silver-second"
    result=mod.run(root=out,model="sonnet",workers=1)
    assert result["assessed"]==69
    assert result["batches"]==12
    assert result["batch_failures"]==[]
    assert len(calls)==12
    second=mod.run(root=out,model="sonnet",workers=1)
    assert second["assessed"]==69
    assert len(calls)==12  # resumes from verified batches, never reprompt
    rows=list(map(json.loads,(out/"annotations.jsonl").read_text().splitlines()))
    assert len({r["posting_id"] for r in rows})==69
    assert all(r["origin"]=="SECOND_BLIND_AI_NOT_HUMAN_GOLD" for r in rows)
    with pytest.raises(ValueError,match="frozen run contract"):
        mod.run(root=out,model="opus",workers=1)

def test_second_pass_rejects_extra_model_fields(tmp_path):
    rows=[source(i) for i in range(69)]
    path=tmp_path/"packet.jsonl"
    rows[5]["classifier_status"]="IT_CONFIRMED"
    path.write_text("".join(json.dumps(r)+"\n" for r in rows))
    with pytest.raises(ValueError,match="non-source"):
        mod.read_items(path)

def test_source_validation_requires_69(tmp_path):
    path=tmp_path/"packet.jsonl"
    path.write_text(json.dumps(source(0))+"\n")
    with pytest.raises(ValueError,match="69-offer"):
        mod.read_items(path)
