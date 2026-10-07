import json

from ingestion.expansion_sources import AplikujSource, BulldogJobSource, EuroTechJobsSource, HNWhoIsHiringSource, ITLeadersSource, MichaelPageSource, NoFluffJobsSource, PracujSecondarySource, RocketJobsSource
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


def test_rocket_html_fallback_archived_without_jsonld():
    html="""<html><head><link rel="canonical" href="https://rocketjobs.pl/oferta-pracy/ab-industry-example"><meta property="og:title" content="Administrator - Projektant 3D: Macierzysz / Warszawa"></head><body><h1>Administrator - Projektant 3D: Macierzysz / Warszawa</h1><div>Oferta archiwalna</div><a class="company_all_offers_link">Praca AB Industry</a><section><h2>Opis stanowiska</h2><p>Projektowanie instalacji.</p></section></body></html>"""
    ref=PostingRef("rocketjobs","https://rocketjobs.pl/oferta-pracy/ab-industry-example","ab-industry-example")
    parsed=RocketJobsSource().parse_detail(html,ref)
    assert parsed.title=="Administrator - Projektant 3D: Macierzysz / Warszawa"
    assert parsed.company_mention=="AB Industry"
    assert parsed.source_specific["parse_mode"]=="HTML_FALLBACK"
    assert parsed.source_specific["archived"] is True


def test_bulldog_parses_numeric_identity_and_jsonld():
    html='''<html><head><script type="application/ld+json">{
      "@context":"https://schema.org","@type":"JobPosting",
      "@id":"https://bulldogjob.com/companies/jobs/256852-example",
      "title":"Principal Developer",
      "description":"Build systems",
      "skills":"C#, Angular",
      "hiringOrganization":{"@type":"Organization","name":"Luxoft DXC"},
      "employmentType":"FULL_TIME"
    }</script></head><body><h1>Principal Developer</h1></body></html>'''
    ref=PostingRef("bulldogjob","https://bulldogjob.com/companies/jobs/256852-example","256852")
    p=BulldogJobSource().parse_detail(html,ref)
    assert p.source_posting_id=="256852"
    assert p.title=="Principal Developer"
    assert p.company_mention=="Luxoft DXC"
    assert p.source_specific["skills"]=="C#, Angular"


def test_pracuj_secondary_parses_upstream_identity_and_provenance():
    raw=json.dumps({
        "offer_source":"pracuj.pl",
        "offer_href":"https://www.pracuj.pl/praca/data-engineer-warszawa,oferta,1005078091",
        "offer_uuid":"mirror-uuid-1",
        "offer_title":"Data Engineer",
        "offer_city":"Warszawa",
        "offer_remote_available":True,
        "offer_category":"data",
        "offer_technologies":["Python","SQL"],
        "offer_salary_interval":"month",
        "offer_salary_min":20000,
        "offer_salary_max":26000,
        "offer_salary_currency":"PLN",
        "offer_published_at":"2026-10-01T08:00:00Z",
        "company":{"company_name":"Acme"},
    })
    ref=PostingRef(
        "pracuj",
        "https://www.pracuj.pl/praca/data-engineer-warszawa,oferta,1005078091",
        "1005078091",
    )
    p=PracujSecondarySource().parse_detail(raw,ref)
    assert p.source_posting_id=="1005078091"
    assert p.title=="Data Engineer"
    assert p.company_mention=="Acme"
    assert p.source_specific["observation_provenance"]=="SECONDARY_PUBLIC_INDEX"
    assert p.source_specific["upstream_source"]=="pracuj.pl"
    assert p.source_specific["mirror"]=="isitfair.pl"


def test_pracuj_secondary_rejects_non_pracuj_upstream():
    raw=json.dumps({
        "offer_source":"other.example",
        "offer_href":"https://www.pracuj.pl/praca/x,oferta,1005078091",
        "offer_title":"X",
    })
    ref=PostingRef("pracuj","https://www.pracuj.pl/praca/x,oferta,1005078091","1005078091")
    try:
        PracujSecondarySource().parse_detail(raw,ref)
    except ValueError as exc:
        assert "upstream source mismatch" in str(exc)
    else:
        raise AssertionError("expected upstream-source rejection")

from ingestion.expansion_sources import SolidJobsSource


def test_solid_html_fallback_without_jsonld():
    html = """<html><head><link rel="canonical" href="https://solid.jobs/offer/30898/affirm-senior-software-engineer-iam"><meta property="og:description" content="IAM role"></head><body><h1>Senior Software Engineer - IAM</h1><section><h2>Zakres zadań</h2><p>Build IAM systems</p></section></body></html>"""
    ref = PostingRef("solidjobs","https://solid.jobs/offer/30898/affirm-senior-software-engineer-iam","30898")
    parsed = SolidJobsSource().parse_detail(html, ref)
    assert parsed.source_posting_id == "30898"
    assert parsed.title == "Senior Software Engineer - IAM"
    assert parsed.source_specific["parse_mode"] == "HTML_FALLBACK"
    assert parsed.source_specific["observation_provenance"] == "DIRECT"


def test_solid_prefers_jsonld_when_present():
    html = """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"AI Engineer","identifier":{"value":"38940"},"url":"https://solid.jobs/offer/38940/itfs-ai-specialist","hiringOrganization":{"name":"ITFS"}}</script></head><body><h1>AI Engineer</h1></body></html>"""
    ref = PostingRef("solidjobs","https://solid.jobs/offer/38940/itfs-ai-specialist","38940")
    parsed = SolidJobsSource().parse_detail(html, ref)
    assert parsed.source_posting_id == "38940"
    assert parsed.company_mention == "ITFS"
    assert parsed.source_specific["parse_mode"] == "JSON_LD"


def test_solid_generic_shell_is_source_gone():
    from ingestion.model import SourceGoneError
    html = """<html><head><title>SOLID.Jobs – Platforma rekrutacyjna dla specjalistów</title></head><body><div id="app"></div></body></html>"""
    ref = PostingRef("solidjobs","https://solid.jobs/offer/31077/example","31077")
    try:
        SolidJobsSource().parse_detail(html, ref)
    except SourceGoneError:
        pass
    else:
        raise AssertionError("expected SourceGoneError")


def test_aplikuj_parses_jobposting_jsonld():
    html = """<html><head><link rel="canonical" href="https://www.aplikuj.pl/oferta/3313385/example"><script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"Operator","hiringOrganization":{"@type":"Organization","name":"Acme"},"datePosted":"2026-10-01","validThrough":"2026-11-01","employmentType":"FULL_TIME","industry":"Produkcja"}</script></head><body><h1>Operator</h1></body></html>"""
    ref=PostingRef("aplikuj","https://www.aplikuj.pl/oferta/3313385/example","3313385")
    parsed=AplikujSource().parse_detail(html,ref)
    assert parsed.source_posting_id=="3313385"
    assert parsed.title=="Operator"
    assert parsed.company_mention=="Acme"
    assert parsed.source_specific["observation_provenance"]=="DIRECT"


def test_aplikuj_html_fallback_without_jsonld():
    html = """<html><head><title>Oferta pracy Doradca Klienta, PRO DOMO Sp. z o.o. - Pabianice - Aplikuj.pl</title><link rel="canonical" href="https://www.aplikuj.pl/oferta/1038688/doradca-klienta-umowa-o-prace-lento"><meta name="description" content="Zapoznaj się z ofertą pracy Doradca Klienta w Pabianicach. Pracownika poszukuje firma PRO DOMO Sp. z o.o.. Aplikuj już dzisiaj!"></head><body><h1>Doradca Klienta</h1><div class="offer-employer-header__company text-md lg:text-base">Pracodawca - PRO DOMO Sp. z o.o.</div><section><h2>Opis stanowiska</h2><p>Obsługa klientów.</p></section></body></html>"""
    ref=PostingRef("aplikuj","https://www.aplikuj.pl/oferta/1038688/doradca-klienta-umowa-o-prace-lento","1038688")
    parsed=AplikujSource().parse_detail(html,ref)
    assert parsed.source_posting_id=="1038688"
    assert parsed.title=="Doradca Klienta"
    assert parsed.company_mention=="PRO DOMO Sp. z o.o."
    assert parsed.source_specific["observation_provenance"]=="DIRECT"
    assert parsed.source_specific["parse_mode"]=="HTML_FALLBACK"


def test_itleaders_parses_role_and_company_from_meta():
    html = """<html><head><meta name="description" content="Junior Backend Developer (Python), Lokalizacja: Gliwice, Wynagrodzenie:"><meta property="og:title" content="MindPal Sp. z o.o. - Junior Backend Developer (Python)"></head><body><h1>Oferty pracy</h1><h2>Wymagania</h2><p>Python</p></body></html>"""
    ref=PostingRef("itleaders","https://it-leaders.pl/oferta-pracy/junior-backend-developer-python-gliwice-3851","3851")
    parsed=ITLeadersSource().parse_detail(html,ref)
    assert parsed.title=="Junior Backend Developer (Python)"
    assert parsed.company_mention=="MindPal Sp. z o.o."
    assert parsed.source_specific["observation_provenance"]=="DIRECT"


def test_michaelpage_parses_recruiter_jsonld():
    html = """<html><head><link rel="canonical" href="https://www.michaelpage.pl/en/job-detail/manager-sysops/ref/jn-092026-7112987"><script type="application/ld+json">{"@context":"http://schema.org/","@type":"JobPosting","title":"Manager SysOps","hiringOrganization":{"@type":"Organization","name":"Michael Page Poland"},"datePosted":"2026-09-29","employmentType":"FULL_TIME","industry":"Information Technology"}</script></head><body><h1>Manager SysOps</h1></body></html>"""
    ref=PostingRef("michaelpage","https://www.michaelpage.pl/en/job-detail/manager-sysops/ref/jn-092026-7112987","jn-092026-7112987")
    parsed=MichaelPageSource().parse_detail(html,ref)
    assert parsed.title=="Manager SysOps"
    assert parsed.company_mention=="Michael Page Poland"
    assert parsed.source_specific["observation_provenance"]=="DIRECT_RECRUITER"

def test_michaelpage_tolerates_control_chars_in_jsonld_description():
    html = '''<html><head><script type="application/ld+json">{"@context":"http://schema.org/","@type":"JobPosting","title":"Power BI Lead","description":"line 1
line 2","hiringOrganization":{"@type":"Organization","name":"Michael Page Poland"},"industry":"Information Technology"}</script></head><body><h1>Power BI Lead</h1></body></html>'''
    ref=PostingRef("michaelpage","https://www.michaelpage.pl/job-detail/power-bi-lead/ref/jn-1","jn-1")
    parsed=MichaelPageSource().parse_detail(html,ref)
    assert parsed.title=="Power BI Lead"
    assert parsed.company_mention=="Michael Page Poland"


def test_eurotechjobs_parses_visible_detail():
    html = """<html><head><link rel="canonical" href="https://www.eurotechjobs.com/job_display/296685/Example"><meta property="og:title" content="Senior AI Engineer - Aptiv, Krakow"><meta property="og:description" content="Build robotics systems"></head><body><div class="jobDisplay"><h1>Senior AI Engineer</h1><h2>Aptiv</h2><h2>Krakow, Poland</h2><p>Build robotics systems</p></div></body></html>"""
    ref=PostingRef("eurotechjobs","https://www.eurotechjobs.com/job_display/296685/Example","296685")
    parsed=EuroTechJobsSource().parse_detail(html,ref)
    assert parsed.source_posting_id=="296685"
    assert parsed.title=="Senior AI Engineer"
    assert parsed.company_mention=="Aptiv"
    assert parsed.source_specific["location"]=="Krakow, Poland"
    assert parsed.source_specific["observation_provenance"]=="DIRECT"


def test_hn_whoishiring_parses_top_level_comment():
    raw=json.dumps({
        "id":49995549,
        "parent":49922569,
        "by":"founder",
        "time":1791000000,
        "type":"comment",
        "text":"Acme AI | Remote | Senior Platform Engineer<br>We build inference infrastructure."
    })
    ref=PostingRef("hnwhoishiring","https://news.ycombinator.com/item?id=49995549","49995549")
    parsed=HNWhoIsHiringSource().parse_detail(raw,ref)
    assert parsed.source_posting_id=="49995549"
    assert parsed.company_mention=="Acme AI"
    assert parsed.title.startswith("Acme AI | Remote | Senior Platform Engineer")
    assert parsed.source_specific["thread_id"]=="49922569"
    assert parsed.source_specific["observation_provenance"]=="COMMUNITY_DIRECT"
