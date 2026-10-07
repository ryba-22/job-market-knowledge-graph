from ingestion.opportunity_evidence import _ats_identity, _external
from ingestion.adjudicate import _same_ats, _same_application_url


def test_portal_urls_are_not_external_application_targets():
    assert not _external("https://og-image.justjoin.it/logo.png")
    assert not _external("https://static.theprotocol.it/x")
    assert _external("https://jobs.example.com/req/123")


def test_ats_identity_extracts_requisition():
    x=_ats_identity("https://boards.greenhouse.io/acme/jobs/123456")
    assert x["host"]=="boards.greenhouse.io"
    assert x["requisition"]=="123456"


def test_shared_ats_requisition_is_decisive():
    evidence=[
        {"posting_id":1,"type":"ATS_URL","value":{"ats":{"host":"boards.greenhouse.io","requisition":"123"}}},
        {"posting_id":2,"type":"ATS_URL","value":{"ats":{"host":"boards.greenhouse.io","requisition":"123"}}},
    ]
    assert _same_ats(evidence)==("boards.greenhouse.io","123")


def test_shared_application_target_requires_both_postings():
    evidence=[
        {"posting_id":1,"type":"APPLICATION_URL","value":{"url":"https://jobs.example.com/123"}},
        {"posting_id":2,"type":"APPLICATION_URL","value":{"url":"https://jobs.example.com/123"}},
    ]
    assert _same_application_url(evidence)=="https://jobs.example.com/123"


def test_rocketjobs_source_family_is_not_application_target():
    assert not _external("https://rocketjobs.pl/")
    assert not _external("https://panel.rocketjobs.com/")


def test_reviewer_fixture_has_only_supported_labels():
    import json
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/"data"/"evals"/"er-eval-02-reviewer-decisions.json"
    payload=json.loads(path.read_text(encoding="utf-8"))
    labels={x["label"] for x in payload["decisions"]}
    assert labels <= {"SAME_OPPORTUNITY","DISTINCT_OPPORTUNITY","UNRESOLVED"}
    assert any(x["label"]=="SAME_OPPORTUNITY" for x in payload["decisions"])
    assert any(x["label"]=="DISTINCT_OPPORTUNITY" for x in payload["decisions"])
    for item in payload["decisions"]:
        assert item["rationale"]
        assert item["evidence"]


def test_required_reviewer_postings_are_deduplicated():
    from ingestion.ensure_eval_postings import _required
    payload={"decisions":[
        {"a":{"source":"a","source_posting_id":"1"},"b":{"source":"b","source_posting_id":"2"}},
        {"a":{"source":"a","source_posting_id":"1"},"b":{"source":"c","source_posting_id":"3"}},
    ]}
    assert _required(payload)==[("a","1"),("b","2"),("c","3")]
