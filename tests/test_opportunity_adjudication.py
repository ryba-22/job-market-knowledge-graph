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
