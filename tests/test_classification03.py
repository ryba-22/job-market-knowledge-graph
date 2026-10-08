"""CLASSIFICATION-03 integrity / blind annotation / scoring fail-closed tests."""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path

import pytest

from ingestion import classification03 as pilot
from ingestion import classification03_score as score
from ingestion.classification03_score import validate_one, weighted_rates

def population():
    rows, preds = {}, {}
    for i in range(509):
        if i < 93:
            cls="IT_CONFIRMED"
        elif i < 242:
            cls="NON_IT_CONFIRMED"
        else:
            cls="REVIEW_REQUIRED"
        id=str(1000+i)
        row={
            "source_posting_id":id,"revision_id":"rev"+id,"raw_payload_sha256":"raw"+id,
            "url":"https://www.aplikuj.pl/oferta/"+id+"/test",
            "title":("IT Frontend Developer" if i%2 else "Operator CNC") +" number "+id,
            "source_projection":{"industry":"Informatyk" if i%2 else "Operator"},
            "normalized_projection":{"semantic_content":{"jobposting_json_ld":{
                "description":"Praca techniczna przy aplikacjach." if i%2 else "Obsługa maszyn i elementów produkcji."
            }}},
        }
        rows[id]=row
        preds[id]={"source_posting_id":id,"revision_id":row["revision_id"],
            "raw_payload_sha256":row["raw_payload_sha256"],
            "previous_status":"REVIEW_REQUIRED",
            "assessment":{"status":cls}}
    return rows,preds


def setup(tmp_path,monkeypatch):
    rows,preds=population()
    c02=tmp_path/"c02";c02.mkdir()
    (c02/"assessments.jsonl.gz").write_bytes(b"frozen-predictions")
    monkeypatch.setattr(pilot,"load_verified_population",lambda *args:(rows,preds))
    out=tmp_path/"case"
    summary=pilot.prepare(tmp_path/"source",c02,out,tmp_path/"report.json")
    return rows,preds,c02,out,summary


def test_frozen_stratified_blind_sampling(tmp_path,monkeypatch):
    rows,preds,c02,out,result=setup(tmp_path,monkeypatch)
    design=json.loads((out/"private-sample-manifest.json").read_text())["selection"]
    assert len(design)==len({x["posting_id"] for x in design})==200
    assert Counter(x["panel"] for x in design)=={"probability":160,"challenge":40}
    assert Counter(x["stratum"] for x in design if x["panel"]=="probability")==pilot.QUOTAS
    assert sum(x["second_review_required"] for x in design)==40
    assert Counter(x["split"] for x in design)=={"development":160,"holdout":40}
    for round,size in (("a",200),("b",40)):
        packets=[json.loads(s) for s in (out/f"reviewer-{round}.jsonl").read_text().splitlines()]
        assert len(packets)==size
        assert "stratum" not in packets[0] and "predicted_status" not in packets[0]
        assert "description" in packets[0]
        html=(out/f"reviewer-{round}.html").read_text()
        for model_label in ("IT_CONFIRMED","NON_IT_CONFIRMED","REVIEW_REQUIRED"):
            assert model_label not in html
        from bs4 import BeautifulSoup
        script=BeautifulSoup(html,"html.parser").find(id="sample")
        assert len(json.loads(script.string)["items"])==size
        assert html.count("</script>")==2
    old=(out/"private-sample-manifest.json").read_bytes()
    pilot.prepare(tmp_path/"source",c02,out,tmp_path/"report.json")
    assert old==(out/"private-sample-manifest.json").read_bytes()
    (c02/"assessments.jsonl.gz").write_bytes(b"DIFFERENT")
    with pytest.raises(ValueError,match="DIFFERENT sample manifest"):
        pilot.prepare(tmp_path/"source",c02,out,tmp_path/"report.json")


def test_anchored_annotations_must_match_source():
    row={"posting_id":"1","revision_id":"revision","raw_payload_sha256":"sha","title":"Frontend Developer","description":"Tworzenie aplikacji internetowych.","source_industry":"Informatyk"}
    a={"posting_id":"1","revision_id":"revision","raw_payload_sha256":"sha",
       "label":"IT_TECHNICAL","family":"software_engineering","evidence_field":"description",
       "quote":"Tworzenie aplikacji","notes":""}
    validate_one(a,row)
    with pytest.raises(ValueError,match="ungrounded evidence"):
        validate_one(a|{"quote":"Nieistniejący cytat"},row)
    with pytest.raises(ValueError,match="revision"):
        validate_one(a|{"revision_id":"other"},row)
    with pytest.raises(ValueError,match="anchored quote"):
        validate_one(a|{"quote":""},row)
    with pytest.raises(ValueError,match="explanation"):
        validate_one(a|{"label":"UNDETERMINABLE","quote":"","notes":""},row)


def simulated_export(data,round,reviewer,answers):
    return {"format":"classification03-annotations-v1","round":round,
            "reviewer":reviewer,"independent_attested":True,
            "annotations":answers}


def annotation(row,label):
    if label=="IT_TECHNICAL":family="software_engineering"
    elif label=="NON_IT":family="transport_logistics"
    else:family="other"
    return {"posting_id":row["posting_id"],"revision_id":row["revision_id"],
            "raw_payload_sha256":row["raw_payload_sha256"],
            "label":label,"family":family,
            "evidence_field":"description" if label=="IT_TECHNICAL" else ("title" if label=="NON_IT" else ""),
            "quote":row["description"][:45] if label=="IT_TECHNICAL" else (row["title"][:45] if label=="NON_IT" else ""),
            "notes":"Unclear work scope from this source." if label in ("IT_ADJACENT","UNDETERMINABLE") else ""}


def test_evaluation_fail_closed_and_adjudication(tmp_path,monkeypatch):
    rows,preds,c02,root,_=setup(tmp_path,monkeypatch)
    assert score.evaluate(tmp_path/"source",c02,root)["status"]=="BLOCKED_NO_INDEPENDENT_GOLD"
    a_rows=[json.loads(s) for s in (root/"reviewer-a.jsonl").read_text().splitlines()]
    b_rows=[json.loads(s) for s in (root/"reviewer-b.jsonl").read_text().splitlines()]
    selection=json.loads((root/"private-sample-manifest.json").read_text())["selection"]
    strata={x["posting_id"]:x["stratum"] for x in selection}
    def expected(row):
        s=strata[row["posting_id"]]
        return "IT_TECHNICAL" if s=="IT_CONFIRMED" else "NON_IT" if s=="NON_IT_CONFIRMED" else "IT_ADJACENT"
    a=[annotation(row,expected(row)) for row in a_rows]
    (root/"reviewer-a-annotations.json").write_text(json.dumps(simulated_export(None,"a","alice",a[:50])))
    assert score.evaluate(tmp_path/"source",c02,root)["status"]=="BLOCKED_INCOMPLETE_FIRST_REVIEW"
    (root/"reviewer-a-annotations.json").write_text(json.dumps(simulated_export(None,"a","alice",a)))
    assert score.evaluate(tmp_path/"source",c02,root)["status"]=="BLOCKED_SECOND_REVIEW"
    b=[annotation(row,expected(row)) for row in b_rows]
    (root/"reviewer-b-annotations.json").write_text(json.dumps(simulated_export(None,"b","alice",b)))
    with pytest.raises(ValueError,match="distinct identity"):
        score.evaluate(tmp_path/"source",c02,root)
    # Independent second reviewer disagrees on one complete role.
    changed=b[0]
    changed_label = "NON_IT" if changed["label"]!="NON_IT" else "IT_TECHNICAL"
    b[0]=annotation(b_rows[0],changed_label)
    (root/"reviewer-b-annotations.json").write_text(json.dumps(simulated_export(None,"b","bob",b)))
    res=score.evaluate(tmp_path/"source",c02,root)
    assert res["status"]=="BLOCKED_PENDING_ADJUDICATION"
    assert res["disagreement_count"]==1
    third_packet=score.prepare_third_review(root)
    assert third_packet["status"]=="THIRD_REVIEW_PACKET_READY"
    assert third_packet["disagreements"]==1
    assert (root/"reviewer-c.html").exists()
    c_answer=next(x for x in a if x["posting_id"]==b[0]["posting_id"])
    (root/"reviewer-c-annotations.json").write_text(json.dumps(simulated_export(None,"c","charlie",[c_answer])))
    monkeypatch.setattr(score,"load_verified_population",lambda *args:(rows,preds))
    third_result=score.evaluate(tmp_path/"source",c02,root)
    assert third_result["status"]=="EVALUATED_INDEPENDENT_GOLD_RELEASE_APPROVAL_REQUIRED"
    (root/"reviewer-c-annotations.json").unlink()
    adjud={"format":"classification03-adjudications-v1","adjudicator":"charlie",
           "annotations":[next(x for x in a if x["posting_id"]==b[0]["posting_id"])]}
    (root/"adjudications.json").write_text(json.dumps(adjud))
    monkeypatch.setattr(score,"load_verified_population",lambda *args:(rows,preds))
    res=score.evaluate(tmp_path/"source",c02,root)
    assert res["status"]=="EVALUATED_INDEPENDENT_GOLD_RELEASE_APPROVAL_REQUIRED"
    assert res["gold_count"]==200 and res["double_review_count"]==40
    assert res["adjudicated_disagreements"]==1
    assert res["release_decision"].startswith("NOT_AUTHORIZED")
    assert res["stratified_probability_metrics"]["it_precision"]==1.0
    assert res["stratified_probability_metrics"]["it_recall"]==1.0
    assert res["stratified_probability_metrics"]["technical_it_count_estimate"]==93.0
    assert sum(res["challenge_confusion_unweighted"].values())==40
    assert sum(res["holdout_confusion_unweighted"].values())==40
    # Model source hash change must invalidate scoring.
    (c02/"assessments.jsonl.gz").write_bytes(b"mutated")
    with pytest.raises(ValueError,match="Frozen model predictions"):
        score.evaluate(tmp_path/"source",c02,root)


def test_weighted_rates_exclude_purposive_challenge(tmp_path,monkeypatch):
    rows,preds,c02,out,_=setup(tmp_path,monkeypatch)
    design=json.loads((out/"private-sample-manifest.json").read_text())["selection"]
    gold={item["posting_id"]:{"label":"IT_ADJACENT"} for item in design}
    for item in design:
        if item["panel"]=="probability" and item["stratum"]=="IT_CONFIRMED":
            gold[item["posting_id"]]={"label":"NON_IT"}
    report=weighted_rates(gold,preds,design)
    assert report["population"]==509
    assert report["it_precision"]==0.0
    assert report["it_recall"] is None
    assert report["model_false_it_assignments_weighted"]==93.0
