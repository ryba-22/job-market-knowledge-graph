"""Offline checkpoint tests for unsampled 309-source review with source-only model calls."""
from __future__ import annotations
import json
import pytest
from ingestion import classification03_ai_archive as m

def row(i):
    id=str(70000+i)
    return {
        "posting_id":id,"revision_id":"rev-"+id,"raw_payload_sha256":"raw-"+id,
        "source":"aplikuj","source_url":"https://example.com/"+id,
        "title":"Developer" if i%2 else "Courier Driver",
        "source_industry":"Informatyk" if i%2 else "Kierowca",
        "description":"Develop Python software applications." if i%2 else "Deliver packages using company car."
    }

def answer(r):
    it=r["title"]=="Developer"
    return {
        "posting_id":r["posting_id"],"label":"IT_TECHNICAL" if it else "NON_IT",
        "family":"software_engineering" if it else "transport_logistics",
        "evidence_field":"description","quote":r["description"][:25],
        "notes":"Explicit duties.","confidence":"high"
    }

def test_309_source_only_locked_and_resumable(tmp_path,monkeypatch):
    data=[row(i) for i in range(309)]
    monkeypatch.setattr(m,"sample",lambda:data)
    requests=[]
    def fake(items,model,timeout=330):
        assert model=="sonnet"
        assert all(set(x)==set(data[0]) for x in items)
        requests.extend(r["posting_id"] for r in items)
        return [m.validate_model_output(items,{"annotations":[answer(x) for x in items]})[i] for i in range(len(items))],{"cost_usd":0.0}
    monkeypatch.setattr(m,"call_ai",fake)
    root=tmp_path/"archive"
    result=m.run(model="sonnet",workers=3,root=root)
    assert result["assessed"]==309 and result["failed_chunks"]==[]
    assert len(requests)==len(set(requests))==309
    assert m.run(model="sonnet",workers=3,root=root)["assessed"]==309
    assert len(requests)==309
    contract=root/"sonnet"/"contract.json"
    frozen=json.loads(contract.read_text())
    frozen["source_sha256"]="tampered"
    contract.write_text(json.dumps(frozen))
    with pytest.raises(ValueError,match="contract"):
        m.run(model="sonnet",workers=1,root=root)

def test_no_gold_promotions():
    assert m.VERSION.endswith("-v1")
def test_509_archive_merge_keeps_silver_and_all_identities(tmp_path,monkeypatch):
    all_items=[row(i) for i in range(509)]
    source={x["posting_id"]:x for x in all_items}
    rules={x["posting_id"]:{"assessment":{"status":"REVIEW_REQUIRED"}} for x in all_items}
    local=tmp_path/"c03";local.mkdir()
    monkeypatch.setattr(m,"OUT",local)
    monkeypatch.setattr(m,"packet",lambda x:x)
    monkeypatch.setattr(m,"load_verified_population",lambda:(source,rules))
    def full(x):
        return {**answer(x),"revision_id":x["revision_id"],"raw_payload_sha256":x["raw_payload_sha256"]}
    def dump(path,entries):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text("".join(json.dumps(e)+"\n" for e in entries))
    dump(local/"ai-silver-v1"/"silver-annotations.jsonl",[full(x) for x in all_items[:200]])
    dump(local/"ai-remaining153-v1"/"ai-proposals-200.jsonl",[
        {"posting_id":x["posting_id"],"revision_id":x["revision_id"],
         "raw_payload_sha256":x["raw_payload_sha256"],
         "is_gold":False,"proposal":answer(x)["label"],
         "source_only_votes":{"first_sonnet":answer(x)["label"],"second_sonnet":answer(x)["label"],"third_opus":answer(x)["label"]}}
        for x in all_items[:200]
    ])
    rest=all_items[200:]
    out=tmp_path/"archive"
    dump(out/"sonnet"/"annotations.jsonl",[full(x) for x in rest])
    opus=[full(x) for x in rest]
    opus[0]={**opus[0],"label":"IT_ADJACENT","family":"other","notes":"Some roles may be mixed."}
    dump(out/"opus"/"annotations.jsonl",opus)
    merged=m.merge(root=out,report=None)
    assert merged["source_total"]==509
    assert merged["at_least_two_ai_reviews_coverage"]==509
    assert merged["proposed_silver_scope_counts_509"]["REVIEW_REQUIRED"]==1
    assert merged["human_gold"]==0 and merged["production_go"] is False
    saved=[json.loads(x) for x in (out/"merged"/"ai-archive509-sidecar.jsonl").read_text().splitlines()]
    assert len(saved)==len({e["posting_id"] for e in saved})==509
    assert all(e["not_human_gold"] is True for e in saved)
    assert sum(e["source_panel"]=="FROZEN_C03_SAMPLE_200" for e in saved)==200
    assert sum(e["source_panel"]=="UNSAMPLED_309" for e in saved)==309
def test_partial_opus_returns_only_frozen_verified_chunks(tmp_path):
    import json
    rows=[row(i) for i in range(309)]
    folder=tmp_path/"opus";(folder/"parts").mkdir(parents=True)
    (folder/"contract.json").write_text(json.dumps({"model":"opus","source_sha256":m.sha(rows),"count":309}))
    from ingestion.classification03_ai import validate_model_output
    for n in [0,1]:
        part=rows[n*6:(n+1)*6]
        assessments=validate_model_output(part,{"annotations":[answer(x) for x in part]})
        (folder/"parts"/f"batch-{n:03}.json").write_text(json.dumps({
            "format":m.VERSION,"model":"opus","source_sha256":m.sha(part),
            "annotations":assessments
        }))
    partial=m.verified_opus_partial(tmp_path,rows)
    assert len(partial)==12 and set(partial)=={x["posting_id"] for x in rows[:12]}
    assert len((folder/"opus-partial-verified.jsonl").read_text().splitlines())==12
    bad=folder/"parts"/"batch-001.json"
    data=json.loads(bad.read_text())
    data["source_sha256"]="tampered"
    bad.write_text(json.dumps(data))
    with pytest.raises(ValueError,match="tampered"):
        m.verified_opus_partial(tmp_path,rows)


def test_archive_stops_on_provider_session_quota(tmp_path,monkeypatch):
    import json
    from ingestion import classification03_ai_archive as a
    a.QUOTA_STOP.clear()
    def limited(*args,**kwargs):
        raise RuntimeError("PROVIDER_QUOTA: session limit")
    monkeypatch.setattr(a,"call_ai",limited)
    row1=row(1)
    first=a.do_batch(0,[row1],tmp_path,"opus")
    assert first["status"]=="BLOCKED_QUOTA"
    second=a.do_batch(1,[row1],tmp_path,"opus")
    assert second["status"]=="BLOCKED_QUOTA"
    a.QUOTA_STOP.clear()
def test_model_quota_error_extracted_from_stdout(monkeypatch):
    from types import SimpleNamespace
    from ingestion import classification03_ai as ai
    monkeypatch.setattr(ai.subprocess,"run",lambda *args,**kwargs:SimpleNamespace(
        returncode=1,stdout=json.dumps({"is_error":True,"result":"You've hit your session limit; resets 11am"}),stderr=""))
    with pytest.raises(RuntimeError,match="PROVIDER_QUOTA"):
        ai.call_ai([],model="opus",timeout=10)
