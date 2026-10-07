from ingestion.org_enrichment import _domain, _extract_explicit_urls
from ingestion.er_eval import _jaccard, _seniority, _title_tokens


def test_domain_rejects_source_portals():
    assert _domain("https://justjoin.it/job-offer/x") is None
    assert _domain("https://theprotocol.it/szczegoly/praca/x") is None
    assert _domain("https://careers.example.com/jobs/1") == "careers.example.com"


def test_org_url_extraction_requires_explicit_semantic_path():
    projection = {
        "details": {
            "companyUrl": "https://example.com",
            "description": "See https://random.example/blog but this is prose",
        }
    }
    rows = _extract_explicit_urls("theprotocol", projection, {})
    assert any(x["url"] == "https://example.com" for x in rows)
    assert not any("random.example" in x["url"] for x in rows)


def test_title_similarity_is_not_identity():
    a = _title_tokens("Senior Platform Engineer")
    b = _title_tokens("Platform Engineer")
    assert 0 < _jaccard(a, b) < 1
    assert _seniority(a) != _seniority(b)
