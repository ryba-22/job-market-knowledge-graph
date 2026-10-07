from ingestion.model import ParsedPosting, norm_key
from ingestion.sources import JustJoinItAdapter, TheProtocolAdapter


def test_theprotocol_listing_extracts_stable_id():
    html = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url>
        <loc>https://theprotocol.it/szczegoly/praca/x%2Coferta%2C01000000-2f10-afe4-f1b5-08df23ba5ced</loc>
      </url>
    </urlset>
    """
    refs = TheProtocolAdapter().parse_listing(html, "https://theprotocol.it/praca/")
    assert len(refs) == 1
    assert refs[0].source_posting_id == "01000000-2f10-afe4-f1b5-08df23ba5ced"


def test_jjit_listing_deduplicates_by_slug_at_caller_boundary():
    html = """
    <a href="/job-offer/acme-senior-platform-engineer-warszawa-devops">A</a>
    <a href="/job-offer/acme-senior-platform-engineer-warszawa-devops?x=1">B</a>
    """
    refs = JustJoinItAdapter().parse_listing(html, "https://justjoin.it/job-offers/all-locations")
    assert {r.source_posting_id for r in refs} == {
        "acme-senior-platform-engineer-warszawa-devops"
    }


def test_projection_hash_ignores_source_specific_interpretation():
    p = ParsedPosting(
        source="justjoinit",
        source_posting_id="x",
        url="https://example/x",
        title=" Senior  Engineer ",
        company_mention=" ACME ",
        body_text="A\n  B",
        source_specific={"platform_only": "value"},
    )
    first = p.normalized_hash()
    p.source_specific["platform_only"] = "changed"
    assert p.normalized_hash() == first
    assert norm_key(" ACME  Sp. z o.o. ") == "acme sp. z o.o."
