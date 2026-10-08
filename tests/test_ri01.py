"""RI-01 adversarial contract tests. These are fixtures, NOT human gold labels."""
import json

from ingestion.requirement_intelligence import (
    anchored_in_source, classify_title, extract, html_segments, identity,
    plain_segments, sample_corpus, seniority, summarize,
)
from scripts.ri01 import make_explorer


def mk(source="nofluffjobs", sem=None, body=None, source_id="fixture-1"):
    normalized = {"semantic_content": sem or {}, "title": "Solution Architect"}
    if body is not None:
        normalized["body_text"] = json.dumps(body, ensure_ascii=False)
    return {
        "source": source, "source_posting_id": source_id, "title": "Solution Architect",
        "organization_mention": "Example", "normalized_projection": normalized,
        "revision_id": "test-revision", "url": "https://example.test/job",
    }


def test_structured_must_nice_and_provenance():
    r = mk(sem={"requirements": {
        "musts": [{"value": "API design"}, {"value": "Linux"}],
        "nices": [{"value": "Kubernetes"}],
    }, "specs": {"dailyTasks": ["Design REST API and monitor distributed systems."]}})
    a = extract(r)
    assert [(x["quote"], x["modality_candidate"]) for x in a] == [
        ("API design", "MUST"), ("Linux", "MUST"), ("Kubernetes", "NICE"),
        ("Design REST API and monitor distributed systems.", "TASK"),
    ]
    assert all(anchored_in_source(r, x) for x in a)
    assert all(x["span"]["found"] and x["span"]["start"] is not None for x in a)
    assert "kubernetes" not in a[0]["concept_candidates"]
    assert "rest api" in a[-1]["concept_candidates"]


def test_explicit_headers_required_preferred_tasks():
    r = mk(source="bulldogjob", sem={"jobposting_json_ld": {"description":
        "<h3>Requirements</h3><ul><li>Hands-on Linux administration</li></ul>"
        "<h3>Preferred Qualifications</h3><ul><li>Docker experience</li></ul>"
        "<h3>Responsibilities</h3><ul><li>Design secure API services</li></ul>"
        "<h3>Benefits</h3><ul><li>Kubernetes training budget</li></ul>"
    }})
    a = extract(r)
    by_quote = {x["quote"]: x["modality_candidate"] for x in a}
    assert by_quote["Hands-on Linux administration"] == "MUST"
    assert by_quote["Docker experience"] == "NICE"
    assert by_quote["Design secure API services"] == "TASK"
    assert by_quote["Kubernetes training budget"] == "UNKNOWN"
    assert all(anchored_in_source(r, x) for x in a)


def test_negated_requirement_not_positive_must():
    r = mk(sem={"requirements": {"musts": [
        {"value": "No Kubernetes experience required"},
        {"value": "Experience with Linux"}
    ]}})
    a = extract(r)
    assert a[0]["negation_detected"] is True
    assert a[0]["modality_candidate"] == "UNKNOWN"
    assert a[1]["modality_candidate"] == "MUST"


def test_no_invented_obligations_from_plain_description():
    r = mk(source="rocketjobs", sem={"jobposting_json_ld": {"description":
        "We build security tools with Kubernetes and Linux. "
        "We offer developers an excellent sports card. "
        "Please help our customers succeed."}})
    a = extract(r)
    assert a
    assert all(x["modality_candidate"] == "UNKNOWN" for x in a)
    assert all(anchored_in_source(r, x) for x in a)


def test_theprotocol_typed_sections():
    body = {"textSections": [
        {"type": "technologies-expected", "elements": ["Python", "Git"]},
        {"type": "technologies-optional", "elements": ["AWS"]},
        {"type": "responsibilities", "elements": ["Maintain the backend API"]},
        {"type": "benefits", "elements": ["Medical insurance"]},
    ]}
    r = mk(source="theprotocol", body=body)
    a = extract(r)
    assert [(x["quote"], x["modality_candidate"]) for x in a] == [
        ("Python", "MUST"), ("Git", "MUST"), ("AWS", "NICE"),
        ("Maintain the backend API", "TASK")
    ]
    assert all(anchored_in_source(r, x) for x in a)


def test_uncertainty_is_not_claimed_as_ground_truth():
    r = mk(sem={"requirements": {"musts": [{"value": "Linux"}]}})
    a = extract(r)
    assert all(x["review_status"] == "UNREVIEWED" for x in a)
    s = summarize([r], a)
    assert s["quality_metrics"]["precision"] is None
    assert s["quality_metrics"]["recall"] is None
    assert s["status"] == "CANDIDATE_ONLY_NO_GOLD"


def test_deterministic_stratified_sampler_and_heldout_identity():
    records = []
    for source in ("nofluffjobs", "justjoinit", "rocketjobs"):
        for i in range(12):
            row = mk(source, source_id=f"{i}")
            row["title"] = "Backend developer" if i % 2 else "Senior Solution Architect"
            records.append(row)
    quota = {"nofluffjobs": 6, "justjoinit": 6, "rocketjobs": 6}
    one = sample_corpus(records, quota)
    two = sample_corpus(records[::-1], quota)
    assert [identity(x) for x in one] == [identity(x) for x in two]
    assert len(one) == 18 and len({identity(x) for x in one}) == 18
    assert len({x["source"] for x in one}) == 3


def test_explorer_escapes_hostile_source_content():
    row = mk()
    row["title"] = '<img src=x onerror="alert(1)">'
    a = extract(mk(sem={"requirements": {"musts": [{"value": "<script>bad</script> Linux"}]}}))
    a[0]["title"] = row["title"]
    page = make_explorer(a, summarize([row], a))
    assert '&lt;img' in page
    assert '<img src=x onerror' not in page
    assert '<script>bad</script> Linux' not in page


def test_empty_source_is_not_a_negative_requirement():
    row = mk(source="itleaders", sem={"meta_description": "Junior Full Stack developer"})
    assert extract(row) == []


def test_header_classification_does_not_assume_generic_text_is_required():
    lines = html_segments("<p>We build platforms with Kubernetes.</p><p>We offer health care.</p>", "$.desc")
    assert len(lines) == 2
    assert all(x[2] == "UNKNOWN" for x in lines)


def test_plain_fragments_are_anchored_even_when_long():
    text = "We maintain production Python services. " * 60
    lines = plain_segments(text, "$.desc")
    assert lines and len(lines) > 4
    assert all(x[1] in text and x[2] == "UNKNOWN" for x in lines)
