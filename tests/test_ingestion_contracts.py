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


def test_jjit_dynamic_shell_does_not_change_revision_hash():
    url = "https://justjoin.it/job-offer/acme-senior-platform-engineer-warszawa-devops"
    stable = """
    <html><body>
      <div class="rotating-banner">Viewed 10 seconds ago</div>
      <h1>Senior Platform Engineer</h1>
      <h2 data-testid="company-name">ACME</h2>
      <h3>Requirements</h3>
      <ul><li>Kubernetes</li><li>Terraform</li></ul>
      <h3>Responsibilities</h3>
      <ul><li>Operate production platform</li></ul>
      <script type="application/ld+json">
      {
        "@context":"https://schema.org",
        "@type":"JobPosting",
        "title":"Senior Platform Engineer",
        "description":"Build and operate the platform",
        "skills":"Kubernetes, Terraform",
        "hiringOrganization":{"@type":"Organization","name":"ACME"}
      }
      </script>
    </body></html>
    """
    noisy = stable.replace(
        "Viewed 10 seconds ago",
        "Viewed 47 seconds ago — 12 people viewed this offer"
    ).replace(
        "</body>",
        "<div class=\"recommendations\">Recommended job #91827</div></body>"
    )

    adapter = JustJoinItAdapter()
    first = adapter.parse_detail(stable, url)
    second = adapter.parse_detail(noisy, url)

    assert first.body_text != second.body_text
    assert first.normalized_hash() == second.normalized_hash()


def test_jjit_material_job_change_changes_revision_hash():
    url = "https://justjoin.it/job-offer/acme-senior-platform-engineer-warszawa-devops"
    original = """
    <html><body>
      <h1>Senior Platform Engineer</h1>
      <h2 data-testid="company-name">ACME</h2>
      <h3>Requirements</h3><ul><li>Kubernetes</li></ul>
    </body></html>
    """
    changed = original.replace(
        "<li>Kubernetes</li>",
        "<li>Kubernetes</li><li>Terraform</li>"
    )
    adapter = JustJoinItAdapter()
    assert adapter.parse_detail(original, url).normalized_hash() != adapter.parse_detail(changed, url).normalized_hash()
