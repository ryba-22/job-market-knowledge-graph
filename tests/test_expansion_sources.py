import json

from ingestion.expansion_sources import NoFluffJobsSource, RocketJobsSource
from ingestion.model import PostingRef


def test_nfj_parses_structured_detail():
    raw=json.dumps({
        "id":"senior-python-acme-warszawa",
        "postingUrl":"senior-python-acme-warszawa",
        "title":"Senior Python Engineer",
        "company":{"name":"Acme","url":"/company/acme"},
        "basics":{"category":"backend","seniority":["senior"]},
        "details":{"description":"Build APIs"},
        "requirements":{"musts":["Python"]},
        "reference":"ABC123",
        "status":"PUBLISHED",
    })
    ref=PostingRef("nofluffjobs","https://nofluffjobs.com/pl/job/senior-python-acme-warszawa","ABC123")
    p=NoFluffJobsSource().parse_detail(raw,ref)
    assert p.source_posting_id=="ABC123"
    assert p.source_specific["canonical_posting_slug"]=="senior-python-acme-warszawa"
    assert p.title=="Senior Python Engineer"
    assert p.company_mention=="Acme"
    assert p.revision_projection["requirements"]["musts"]==["Python"]


def test_rocket_parses_jobposting_jsonld():
    html='''<html><head><script type="application/ld+json">{
      "@context":"https://schema.org","@type":"JobPosting",
      "title":"Data Engineer",
      "description":"Build data platform",
      "hiringOrganization":{"@type":"Organization","name":"Acme","sameAs":"https://acme.example"},
      "employmentType":"FULL_TIME"
    }</script></head><body><h1>Data Engineer</h1></body></html>'''
    ref=PostingRef("rocketjobs","https://rocketjobs.pl/oferta-pracy/acme-data-engineer","acme-data-engineer")
    p=RocketJobsSource().parse_detail(html,ref)
    assert p.source_posting_id=="acme-data-engineer"
    assert p.title=="Data Engineer"
    assert p.company_mention=="Acme"
    assert p.revision_projection["jobposting_json_ld"]["employmentType"]=="FULL_TIME"
