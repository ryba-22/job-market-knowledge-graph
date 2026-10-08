"""Safe source-only fourth-review cohort, no promotion to gold."""
import json
from pathlib import Path
from ingestion import classification03_ai_last7 as m

def item(i):
    ident=str(6300+i)
    return {"posting_id":ident,"revision_id":"rev-"+ident,
            "raw_payload_sha256":"hash-"+ident,"source":"aplikuj",
            "source_url":"https://example.com/"+ident,
            "title":"IT internship","source_industry":"Informatyk",
            "description":"Only job requirements are listed, no actual duties."}

def test_last7_challenge_silver_no_existing_sidecar_mutation(tmp_path,monkeypatch):
    records=[item(i) for i in range(7)]
    def answer(r):
        return {"posting_id":r["posting_id"],"label":"UNDETERMINABLE",
                "family":"unknown","quote":"","evidence_field":"",
                "notes":"Insufficient actual duties in the source description.",
                "confidence":"low"}
    monkeypatch.setattr(m,"cohort",lambda:records)
    calls=[]
    def ai(items,model,timeout=300):
        assert model=="opus"
        calls.append(1)
        from ingestion.classification03_ai import validate_model_output
        return validate_model_output(items,{"annotations":[answer(r) for r in items]}),{"cost_usd":0.0}
    monkeypatch.setattr(m,"call_ai",ai)
    out=tmp_path/"challenge"
    first=m.review(out)
    assert first["source_reviewed"]==7 and first["gold_labels"]==0
    assert len(calls)==1
    again=m.review(out)
    assert again["old_pending_count"]==7 and len(calls)==1
    assert len((out/"annotations.jsonl").read_text().splitlines())==7
