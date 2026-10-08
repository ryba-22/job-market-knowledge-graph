"""No-network tests for remaining 153 source-only review and full 200 reconciliation."""
from __future__ import annotations
import json
from collections import Counter
import pytest
from ingestion import classification03_ai_remaining as m

def record(i):
    id=str(80000+i)
    return {
        "posting_id":id,"revision_id":"rev"+id,"raw_payload_sha256":"hash"+id,
        "source":"aplikuj","source_url":"https://example.com/"+id,
        "title":"Backend Developer" if i%2 else "Driver",
        "source_industry":"Informatyk" if i%2 else "Kierowca",
        "description":"Develop backend APIs in Python." if i%2 else "Drive trucks and transport goods."
    }

def verdict(row):
    it=row["title"]=="Backend Developer"
    return {
        "posting_id":row["posting_id"],
        "revision_id":row["revision_id"],
        "raw_payload_sha256":row["raw_payload_sha256"],
        "label":"IT_TECHNICAL" if it else "NON_IT",
        "family":"software_engineering" if it else "transport_logistics",
        "evidence_field":"description","quote":row["description"][:29],
        "notes":"Explicit source duties.","confidence":"high",
        "origin":"C03_REMAINING_SOURCE_ONLY_AI_SILVER",
        "policy_version":m.VERSION
    }

def test_frozen_153_complement(tmp_path,monkeypatch):
    root=tmp_path/"c03";root.mkdir()
    a=[record(i) for i in range(200)]
    priority=a[:47]
    sa=root/"source.jsonl"
    pb=root/"priority.jsonl"
    sa.write_text("".join(json.dumps(x)+"\n" for x in a))
    pb.write_text("".join(json.dumps(x)+"\n" for x in priority))
    monkeypatch.setattr(m,"SOURCE",sa)
    monkeypatch.setattr(m,"PRIORITY",pb)
    from ingestion import classification03
    upstream={r["posting_id"]:{"revision_id":r["revision_id"],"raw_payload_sha256":r["raw_payload_sha256"]} for r in a}
    monkeypatch.setattr(classification03,"load_verified_population",lambda: (upstream,{}))
    assert len(m.remaining())==153
    assert not {r["posting_id"] for r in m.remaining()}.intersection({r["posting_id"] for r in priority})
    # No model predictions accidentally sent; reusing source-only full packet.
    model_calls=[]
    def fake_ai(items,model,timeout=330):
        assert model=="sonnet"
        assert all(set(x)==set(a[0]) for x in items)
        model_calls.extend(x["posting_id"] for x in items)
        return [verdict(x) for x in items],{"cost_usd":0.0}
    monkeypatch.setattr(m,"call_ai",fake_ai)
    target=tmp_path/"result"
    out=m.run_one("second_sonnet",target,workers=3)
    assert out["completed"]==153 and out["failed_batches"]==[]
    assert len(model_calls)==153 and len(set(model_calls))==153
    assert m.run_one("second_sonnet",target,workers=3)["completed"]==153
    assert len(model_calls)==153
    with pytest.raises(ValueError,match="cached batch"):
        (target/"second_sonnet"/"parts"/"part-000.json").write_text(json.dumps({
            "source_sha256":"corrupt","model":"sonnet","version":m.VERSION,"annotations":[]}))
        m.run_one("second_sonnet",target,workers=3)

def test_invalid_model_contract():
    with pytest.raises(ValueError,match="reviewer"):
        m.run_one("unknown",workers=1)
def test_full200_reconcile_is_never_gold(tmp_path,monkeypatch):
    from ingestion import classification03 as frozen
    packets=[record(i) for i in range(200)]
    priority=packets[:47]
    remaining=packets[47:]
    folder=tmp_path/"c03"
    folder.mkdir()
    (folder/"reviewer-a.jsonl").write_text("".join(json.dumps(x)+"\n" for x in packets))
    (folder/"reviewer-priority-human.jsonl").write_text("".join(json.dumps(x)+"\n" for x in priority))
    monkeypatch.setattr(m,"SOURCE",folder/"reviewer-a.jsonl")
    monkeypatch.setattr(m,"PRIORITY",folder/"reviewer-priority-human.jsonl")
    monkeypatch.setattr(m,"OUT",folder)
    upstream={x["posting_id"]:{"revision_id":x["revision_id"],"raw_payload_sha256":x["raw_payload_sha256"]} for x in packets}
    previous={x["posting_id"]:{"assessment":{"status":"REVIEW_REQUIRED"}} for x in packets}
    monkeypatch.setattr(frozen,"load_verified_population",lambda:(upstream,previous))
    # Entire benchmark first model, separate second/third for priority and its complement.
    def write(path,items):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text("".join(json.dumps(verdict(x))+"\n" for x in items))
    write(folder/"ai-silver-v1"/"silver-annotations.jsonl",packets)
    write(folder/"ai-blind-second-v1"/"annotations.jsonl",priority)
    write(folder/"ai-delegation-v1"/"opus-47-annotations.jsonl",priority)
    out=tmp_path/"result"
    write(out/"second_sonnet"/"annotations.jsonl",remaining)
    write(out/"third_opus"/"annotations.jsonl",remaining)
    result=m.compare(out,None)
    assert result["source_postings"]==200
    assert result["first_ai_review"]==result["second_ai_review"]==result["third_ai_review"]==200
    assert result["unanimous_labels"]==200
    assert result["not_gold"] and result["human_reviewed"]==0 and not result["production_go"]
    assert result["proposed_scope_counts"]=={"IT_TECHNICAL":100,"NON_IT":100}
    assert len((out/"ai-proposals-200.jsonl").read_text().splitlines())==200
    rows=[json.loads(x) for x in (out/"ai-proposals-200.jsonl").read_text().splitlines()]
    assert all(x["source_grounded_evidence"] and not x["is_gold"] for x in rows)
    (out/"third_opus"/"annotations.jsonl").write_text((out/"third_opus"/"annotations.jsonl").read_text().splitlines()[0]+"\n")
    with pytest.raises(ValueError,match="coverage"):
        m.compare(out,None)
