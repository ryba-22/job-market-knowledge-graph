"""Classification03 source-only AI delegation invariants."""
import json
import pytest
from ingestion import classification03_ai_delegate as m

def row(i):
    sid=str(90000+i)
    return {"posting_id":sid,"source":"aplikuj","source_url":"https://example.com/"+sid,
            "revision_id":"rev-"+sid,"raw_payload_sha256":"raw-"+sid,
            "title":"Backend Developer" if i%2 else "Driver",
            "source_industry":"Informatyk" if i%2 else "Kierowca",
            "description":"Develop Python APIs." if i%2 else "Transport freight across Europe."}

def label(r):
    it=r["title"]=="Backend Developer"
    return {"posting_id":r["posting_id"],"revision_id":r["revision_id"],
            "raw_payload_sha256":r["raw_payload_sha256"],
            "label":"IT_TECHNICAL" if it else "NON_IT",
            "family":"software_engineering" if it else "transport_logistics",
            "quote":r["description"][:26],"evidence_field":"description",
            "notes":"Duties are explicit.","confidence":"high"}

def test_blind_opus_resume_no_fake_gold(tmp_path,monkeypatch):
    rows=[row(i) for i in range(47)]
    cached={r["posting_id"]:label(r)|{"origin":"DOMAIN_THIRD_AI_NOT_HUMAN"} for r in rows[:12]}
    prior={r["posting_id"]:{"assessment":{"status":"REVIEW_REQUIRED"}} for r in rows}
    p=tmp_path/"priority.jsonl";p.write_text("".join(json.dumps(x)+"\n" for x in rows))
    q=tmp_path/"prior.jsonl";q.write_text("".join(json.dumps(x)+"\n" for x in cached.values()))
    monkeypatch.setattr(m,"PRIORITY",p)
    monkeypatch.setattr(m,"PREVIOUS_DOMAIN",q)
    monkeypatch.setattr(m,"source_population",lambda:(rows,cached,prior))
    requested=[]
    def ai(group,model,timeout=330):
        assert model=="opus"
        assert all(set(r)==set(rows[0]) for r in group)
        requested.extend(x["posting_id"] for x in group)
        return [label(x) for x in group],{"cost_usd":0.0}
    monkeypatch.setattr(m,"call_ai",ai)
    dest=tmp_path/"result"
    assert m.run(dest,"opus",workers=2)["opus_reviewed"]==47
    assert len(requested)==35
    assert m.run(dest,"opus",workers=2)["opus_reviewed"]==47
    assert len(requested)==35
    with pytest.raises(ValueError,match="contract"):
        m.run(dest,"sonnet",workers=1)

def test_tampered_cached_batch_rejected(tmp_path):
    p=tmp_path/"parts"/"part-00.json";p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"input_sha256":"wrong","model":"opus","version":m.VERSION,"annotations":[]}))
    with pytest.raises(ValueError,match="frozen contract"):
        m.one_batch(0,[row(1)],tmp_path,"opus")

def test_three_ai_consensus_remains_silver(tmp_path,monkeypatch):
    rows=[row(i) for i in range(47)]
    upstream={r["posting_id"]:label(r)|{"origin":"DOMAIN_THIRD_AI_NOT_HUMAN"} for r in rows[:12]}
    rules={r["posting_id"]:{"assessment":{"status":"REVIEW_REQUIRED"}} for r in rows}
    monkeypatch.setattr(m,"source_population",lambda:(rows,upstream,rules))
    monkeypatch.setattr(m,"OUT",tmp_path)
    for name in ("ai-silver-v1","ai-blind-second-v1"):
        folder=tmp_path/name
        folder.mkdir()
        filename="silver-annotations.jsonl" if name=="ai-silver-v1" else "annotations.jsonl"
        dataset=[label(r) for r in rows]
        if name=="ai-blind-second-v1":
            dataset[1]["label"]="IT_ADJACENT"
            dataset[1]["family"]="other"
            dataset[1]["notes"]="Source includes mixed responsibilities."
        (folder/filename).write_text("".join(json.dumps(x)+"\n" for x in dataset))
    result=tmp_path/"third"
    result.mkdir()
    third=[label(r) for r in rows]
    third[1]["label"]="IT_ADJACENT"
    third[1]["family"]="other"
    third[1]["notes"]="Source includes mixed responsibilities."
    (result/"opus-47-annotations.jsonl").write_text("".join(json.dumps(x)+"\n" for x in third))
    report=m.reconcile(result,None)
    assert report["source_reviewed"]==47
    assert report["gold_labels"]==0
    assert report["production_go"] is False
    assert report["proposed_silver_scope_counts"]["REVIEW_REQUIRED"]==1
    proposals=[json.loads(x) for x in (result/"ai-silver-proposals.jsonl").read_text().splitlines()]
    assert len(proposals)==47
    assert all(x["is_human_gold"] is False for x in proposals)
    assert proposals[1]["disposition"]=="AI_AGREE_OUTSIDE_BINARY_SCOPE"
