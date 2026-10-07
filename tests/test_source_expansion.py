from __future__ import annotations
import json
from ingestion.sources import (
    ADAPTERS,
    BULLDOG_ID,
)

def test_nfj_listing_and_detail_preserve_direct_source_identity():
    listing = {
        "postings": [{
            "id": "Senior-Python-Acme-Remote",
            "url": "senior-python-acme-remote",
            "reference": "NFJ-REF-1",
            "title": "Senior Python Developer",
            "name": "Acme",
        }]
    }
    refs = ADAPTERS["nofluffjobs"].parse_listing(json.dumps(listing), "https://nofluffjobs.com")
    assert refs[0].source_posting_id == "NFJ-REF-1"
    detail = {
        "id": "senior-python-acme-remote",
        "reference": "NFJ-REF-1",
        "title": "Senior Python Developer",
        "company": {"name": "Acme", "url": "https://acme.example"},
        "basics": {"category": "backend", "seniority": ["Senior"]},
        "requirements": {"musts": ["Python"]},
        "specs": {"dailyTasks": ["Build APIs"]},
        "apply": {"option": "url", "referenceNumber": "REQ-1"},
        "location": {"places": [{"city": "Remote"}]},
        "salary": {"from": 20000, "to": 26000, "currency": "PLN"},
    }
    parsed = ADAPTERS["nofluffjobs"].parse_detail(json.dumps(detail), refs[0].url)
    assert parsed.source_posting_id == "NFJ-REF-1"
    assert parsed.company_mention == "Acme"
    assert parsed.source_specific["observation_provenance"] == "DIRECT_PUBLIC_API"

def test_rocket_listing_and_jsonld_detail():
    html = '<a href="/oferta-pracy/acme-ai-engineer-warszawa-ai-1234abcd">x</a>'
    refs = ADAPTERS["rocketjobs"].parse_listing(html, "https://rocketjobs.pl/oferty-pracy/wszystkie-lokalizacje")
    assert refs[0].source_posting_id == "acme-ai-engineer-warszawa-ai-1234abcd"
    detail = '''<html><script type="application/ld+json">{
      "@context":"https://schema.org","@type":"JobPosting",
      "title":"AI Engineer",
      "description":"Build AI systems",
      "employmentType":"FULL_TIME",
      "hiringOrganization":{"@type":"Organization","name":"Acme"}
    }</script></html>'''
    parsed = ADAPTERS["rocketjobs"].parse_detail(detail, refs[0].url)
    assert parsed.title == "AI Engineer"
    assert parsed.company_mention == "Acme"
    assert parsed.source_specific["observation_provenance"] == "DIRECT_SSR"

def test_bulldog_numeric_identity_and_jsonld():
    html = '<a href="https://bulldogjob.com/companies/jobs/255371-full-stack-engineer-ai-systems-acme">x</a>'
    refs = ADAPTERS["bulldogjob"].parse_listing(html, "https://bulldogjob.com/companies/jobs")
    assert refs[0].source_posting_id == "255371"
    assert BULLDOG_ID.search(refs[0].url)
    detail = '''<html><script type="application/ld+json">{
      "@context":"http://schema.org","@type":"JobPosting",
      "@id":"https://bulldogjob.com/companies/jobs/255371-full-stack-engineer-ai-systems-acme",
      "title":"Full Stack Engineer, AI Systems",
      "skills":"Python, Kubernetes",
      "description":"Build reliable agents",
      "hiringOrganization":{"@type":"Organization","name":"Acme"}
    }</script></html>'''
    parsed = ADAPTERS["bulldogjob"].parse_detail(detail, refs[0].url)
    assert parsed.source_posting_id == "255371"
    assert parsed.source_specific["observation_provenance"] == "DIRECT_SSR"

def test_pracuj_secondary_index_keeps_upstream_url_and_id():
    item = {
        "offer_uuid": "mirror-uuid",
        "offer_source": "pracuj.pl",
        "offer_title": "AI Engineer",
        "offer_href": "https://www.pracuj.pl/praca/ai-engineer-warszawa,oferta,1005138472",
        "offer_city": "Warszawa",
        "offer_remote_available": True,
        "offer_category": "it",
        "offer_technologies": ["Python", "LLM"],
        "offer_salary_interval": "monthly",
        "offer_salary_min": 20000,
        "offer_salary_max": 30000,
        "offer_salary_currency": "PLN",
        "offer_published_at": "2026-10-07T10:00:00Z",
        "company": {"company_name": "Acme"},
    }
    refs = ADAPTERS["pracuj"].parse_listing(
        json.dumps({"data":[item]}), "https://isitfair.pl/api/v1/offers/search"
    )
    assert refs[0].source_posting_id == "1005138472"
    parsed = ADAPTERS["pracuj"].parse_detail(json.dumps(item), refs[0].url)
    assert parsed.url.startswith("https://www.pracuj.pl/")
    assert parsed.source_specific["upstream_source"] == "pracuj.pl"
    assert parsed.source_specific["mirror"] == "isitfair.pl"
    assert parsed.source_specific["observation_provenance"] == "SECONDARY_PUBLIC_INDEX"


def test_bulldog_listing_urls_use_path_pagination():
    urls=list(ADAPTERS["bulldogjob"].listing_urls())
    assert urls[0] == "https://bulldogjob.com/companies/jobs"
    assert urls[1] == "https://bulldogjob.com/companies/jobs/s/page,2"
