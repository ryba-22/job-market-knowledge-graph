"""CLASSIFICATION-02: conservative evidence-backed, non-destructive IT role assessments.

Reads archival source projections only. Emits versioned decisions as a sidecar;
never changes source records or the v1 classification.
"""
from __future__ import annotations

from bs4 import BeautifulSoup
import re

from .aplikuj_it_scope import normalized
from .aplikuj_policy import IT_CONFIRMED, NON_IT_CONFIRMED, REVIEW_REQUIRED

POLICY_VERSION = "classification-02-rules-v1"
SCOPE = "technical-digital-roles"  # Not IT-sector employers / sales / IT teaching.

# Match occupational *roles*, not just words 'IT', 'system' or 'computer'.
TECH_ROLES = (
    ("software_engineering", r"\b(?:frontend|front end|backend|back end|full.?stack|software engineer|software developer|web developer|programist\w* (?:aplikacji|frontend|backend|unity|python|java|php|lowcode|\.?net|oracle)|developer|programista|programistyczny|devops|sre|sysops)\b"),
    ("data_ai", r"\b(?:data (?:scientist|engineer|analyst)|analityk danych|inzynier danych|machine learning|mlops|ai engineer|rpa developer|uipath|business intelligence|power bi developer)\b"),
    ("infrastructure", r"\b(?:administrator(?:ka)? (?:it|systemow|sieci|baz danych|infrastruktury)|informatyk\w*|technik informatyk|it support|help.?desk|service desk|it infrastructure|network administrator|cloud engineer|system administrator|administrator systemow komputerowych|specjalista ds (?:wsparcia it|it)|support specialist.{0,20}it|obslugi technicznej uzytkownikow|administrowania i obslugi sieci informatycznych)\b"),
    ("security", r"\b(?:cyberbezpieczenstw\w*|cybersecurity|security analyst|security engineer|soc analyst|penetration tester|pentester|security operations|information security manager|specjalista ds bezpieczenstwa (?:systemow|teleinformatycznego))\b"),
    ("enterprise_systems", r"\b(?:sap (?:consultant|developer|analyst)|sap .{0,25}(?:developer|consultant|analyst)|erp (?:consultant|developer|analyst)|system(?:owy|owo)?[ -]?(?:business analyst|analyst)|it analyst|analityk systemow\w*|analityk systemowo biznesowy|wdrozeniowiec|implementation consultant|salesforce developer|kinaxis maestro|wms system specialist|it process manager|technical system analyst|servicenow|business analyst|analityk biznesowy|oprogramowania enova365|konsultant oprogramowania)\b"),
    ("it_management", r"\b(?:it project manager|it pmo manager|it product owner|software architect|it architect|architekt rozwiazan it|manager sysops|engineering manager|qa engineer|test(?:er|ing) (?:oprogramowania|automatyczn\w*)|fullstack|qa automation)\b"),
)
TECH_PATTERNS = [(family, re.compile(pattern)) for family, pattern in TECH_ROLES]

NON_TECH_ROLES = (
    ("transport_logistics", r"\b(?:kierowc\w*|bus driver|truck driver|magazynier\w*|kompletacja towaru|pracownik centrum przesylkowego|operator wozka|operator wozkow|operat wozka widl\w*|przesylkow\w*|logistyk magazynowy)\b"),
    ("education", r"\b(?:nauczyciel\w*|nauczani\w*|korepetytor\w*|lektor jezyka|prowadz[a-z]* zajec|trener zajec|egzaminator edukacja|edukacja domowa)\b"),
    ("sales", r"\b(?:handlow(?:iec|czyni)|przedstawiciel handlowy|specjalista ds (?:sprzedazy|pozyskiwania klientow)|doradca klienta|kasjer sprzedawca|it sales manager|sales representative|sprzedawca|opiekun klienta biznesowego|sprzedaz systemow it|specjalista sprzedazy)\b"),
    ("industrial", r"\b(?:cnc|robotow (?:przemyslowych|spawalniczych)|spawacz\w*|operator maszyn|operator produkcji|pracownik produkcji|produkcji montazu|frezark\w*|tokark\w*|odlewa\w*|automaty(?:k|ka) programist\w*|programista plc|programowanie robotow)\b"),
    ("office_marketing", r"\b(?:office manager|pracownik administracyjno biurowy|specjalista ds marketingu|digital marketing|grafik komputerowy|asystent ds|asystentka ds|ksiegow\w*|rachunkow\w*|sekretariatu|pracownik biurowy|wsparcia administracyjnego|konstruktor|specjalista ds planowania produkcji)\b"),
    ("physical_services", r"\b(?:sprzata\w*|pracownik fizyczny|pracownik budowlany|instalator sieci swiatlowodowych|monter sieci swiatlowodowych|instalator sieci|serwis aparatury medycznej|pielegniark\w*|kucharz|rehabilitacj\w*|konserwator budynku)\b"),
    ("training_offer", r"\b(?:szkolenie it|kurs ms office|bezplatne szkolenie|certyfikowany kurs)\b"),
)
NON_TECH_PATTERNS = [(family, re.compile(pattern)) for family, pattern in NON_TECH_ROLES]

# Independent source-description evidence of technical work (not employer description).
TECH_DUTIES = re.compile(
    r"\b(?:tworzeni\w*|implementacj\w*|rozwijani\w*|projektowani\w*|"
    r"administrowani\w*|konfigurowani\w*|wdrazani\w*|programowani\w*|"
    r"diagnozowani\w*|utrzymani\w*|testowani\w*|parametryzacj\w*|"
    r"rozwiązywani\w*|develop\w*|design\w*|implement\w*|configur\w*|"
    r"deploy\w*|maintain\w*|automati\w*|manag\w*|monitor\w*|"
    r"troubleshoot\w*|integration\w*|working with|build\w*)\b"
    r".{0,125}\b(?:aplikacj\w*|oprogramowani\w*|system\w* (?:it|informatycz\w*|komputerow\w*|erp|crm|wms)|"
    r"baz\w* danych|sieci\w* komputerow\w*|serwer\w*|infrastruktur\w* it|"
    r"kodu|api|frontendu|backendu|platform\w*|cyberbezpieczenstw\w*|"
    r"software|application\w*|database\w*|network\w*|cloud|"
    r"architecture|enterprise service|security incident|data pipeline|devops|sap|sql|react|python)\b"
)
TECH_STACK = re.compile(
    r"(?<![a-z0-9])(?:python|javascript|typescript|react|angular|vue|node\.?js|c\+\+|c#|"
    r"\.net|spring boot|java developer|django|php|laravel|gitlab|github|docker|kubernetes|"
    r"azure|aws|gcp|linux|windows server|active directory|sql|postgresql|mysql|"
    r"oracle apex|sap|abap|fiori|servicenow|salesforce|mendix|uipath|power bi|"
    r"unity|mes|wms|erp|crm|api|rest|ci/cd|terraform|jenkins|"
    r"l1 and l2|support l1|support l2|itil|network administration|cybersecurity|"
    r"data engineering|data science|security operations)(?![a-z0-9])"
)
NON_TECH_DUTIES = re.compile(
    r"\b(?:prowadzeni\w* (?:pojazd\w*|lekcj\w*|zajec)|przewoz\w* towar\w*|"
    r"spawani\w*|montaz\w* (?:konstrukcj\w*|slusark\w*)|"
    r"kompletacj\w* zamowien|obslug\w* (?:obrabiarek|wozka|kas\w*|maszyn produkcyjnych)|"
    r"sprzatani\w*|pozyskiwani\w* klient\w*|negocjowani\w*|"
    r"udzielani\w* lekcj\w*|nauczani\w*|produkcj\w* detali|przygotowywani\w* posilkow|"
    r"prowadzenie pojazdu|przewoz towarow|building construction)\b"
)
# IT-discipline anchor permits a job whose title is generic but work is clearly technical.
IT_INDUSTRY = {"informatyk", "programista", "administrator it", "specjalista ds bezpieczenstwa it", "wdrozeniowiec"}
NON_IT_INDUSTRIES = {
    "nauczyciel", "kierowca", "magazynier", "pracownik fizyczny",
    "pracownik produkcji", "pracownik sprzatajacy", "ksiegowy",
    "pracownik biurowy", "pracownik administracji", "handlowiec",
    "przedstawiciel handlowy", "operator wozkow widlowych",
    "specjalista ds marketingu", "operator maszyn", "logistyk"
}
BORDERLINE = re.compile(r"\b(?:presales|przedsprzedaz\w*|sprzedaz i serwis it|it sales|"
                        r"automatyk\w*|plc|embedded|serwisant sprzetu|it oraz wsparcie kadr|"
                        r"administrat\w* danych przetwarzanych|marketing|inspektor ds ezd|obsluga sklepu internetowego|nauczyciel programowania)\b")
ACTIVITY_NOT_REQUIRED = re.compile(r"\b(?:frontend|front end|developer|programist\w*|test(?:er|ing) oprogramowania)\b")
NETWORK_ADMIN_DUTIES = re.compile(r"\b(?:administratora lokalnego|administrator\w* techniczn\w*|zarzadzani\w* serwer\w*|administrowani\w* system\w* informatycz\w*|konserwacj\w* sprzetu informatycz\w*|funkcjonowani\w* sprzetu it)\b")
NON_IT_TASK_CUES = re.compile(r"\b(?:rozmow\w* telefonicznych|sprzedaz\w*|pozyskiwani\w* klient\w*|negocjacj\w*|planow produkcyjnych|harmonogramow produkcyjnych|dokumentacji technicznej 2d|solidworks|cad 2d)\b")
STRONG_NONIT_TITLES = re.compile(r"\b(?:kierowc\w*|driver|magazynier\w*|sprzata\w*|nauczyciel\w*|"
                                 r"odlewacz\w*|slusarz\w*|spawacz\w*|pracownik produkcji|"
                                 r"operator cnc|programista cnc|przedstawiciel handlowy|office manager|wsparcia administracyjnego|specialista sprzedazy|"
                                 r"specjalista ds marketingu|szkolenie it|korepetytor\w*)\b")


def _plain(text: str) -> str:
    return normalized(BeautifulSoup(text, "html.parser").get_text(" ", strip=True))


def _match(pattern: re.Pattern, text: str, field: str, code: str) -> dict | None:
    m = pattern.search(text)
    if not m:
        return None
    # Quoted source passage, with local context; no inferred requirements.
    start, end = max(0, m.start()-45), min(len(text), m.end()+65)
    return {"field": field, "code": code, "span": text[start:end]}


def _family(text: str, patterns: list) -> tuple[str | None, re.Match | None]:
    for name, pattern in patterns:
        m = pattern.search(text)
        if m:
            return name, m
    return None, None


def assess_row(row: dict) -> dict:
    """Return an auditable verdict for one archived v2 corpus record.

    Does not delete/mutate original input; ambiguity and conflict fail to review.
    """
    semantic = (row.get("normalized_projection") or {}).get("semantic_content") or {}
    structured = semantic.get("jobposting_json_ld") or {}
    if not isinstance(structured, dict):
        structured = {}
    description = _plain(str(structured.get("description") or ""))
    title = normalized(row.get("title"))
    industry = normalized(str((row.get("source_projection") or {}).get("industry") or ""))
    tech_family, _ = _family(title, TECH_PATTERNS)
    nontech_family, _ = _family(title, NON_TECH_PATTERNS)
    title_tech = tech_family is not None
    title_nontech = nontech_family is not None
    work = _match(TECH_DUTIES, description, "description", "TECHNICAL_WORK")
    stack = _match(TECH_STACK, description, "description", "TECHNICAL_STACK")
    nonwork = _match(NON_TECH_DUTIES, description, "description", "NON_TECHNICAL_WORK")
    admin_work = _match(NETWORK_ADMIN_DUTIES, description, "description", "IT_NETWORK_ADMIN_WORK")
    nontechnical_work = _match(NON_IT_TASK_CUES, description, "description", "NON_IT_OCCUPATIONAL_DUTIES")
    borderline = bool(BORDERLINE.search(title))
    industry_it = industry in IT_INDUSTRY
    industry_nonit = industry in NON_IT_INDUSTRIES

    evidences = []
    if title_tech:
        evidences.append({"field":"title", "code":"TECHNICAL_ROLE", "span":row["title"][:220]})
    if title_nontech:
        evidences.append({"field":"title", "code":"NON_TECHNICAL_ROLE", "span":row["title"][:220]})
    if industry:
        evidences.append({"field":"industry", "code":"SOURCE_INDUSTRY", "span":str((row.get("source_projection") or {}).get("industry"))[:160]})
    for item in (work, stack, nonwork, admin_work, nontechnical_work):
        if item:
            evidences.append(item)

    reason = "INSUFFICIENT_EVIDENCE"
    verdict = REVIEW_REQUIRED
    role_family = tech_family or nontech_family or "unclassified"
    # Specific, unambiguous non-IT occupation dominates accidental tech vocabulary.
    if (industry == "nauczyciel" and re.search(r"\b(?:nauczyciel\w*|szkola|szkole|technikum|liceum|lekcj\w*|nauczani\w*|zajecia)\b", description) and not (work and stack)):
        verdict = NON_IT_CONFIRMED
        reason = "TEACHING_DUTIES_AND_EDUCATION_INDUSTRY"
        role_family = "education"
    elif nontech_family == "education" and (industry == "nauczyciel" or nonwork or re.search(r"\\b(?:nauczyciel|korepetytor|lekcje)\\b", title)):
        verdict = NON_IT_CONFIRMED
        reason = "TEACHING_ROLE_NOT_TECHNICAL_IT"
        role_family = "education"
    elif (nontech_family == "industrial" and re.search(r"\b(?:cnc|robotow (?:przemyslowych|spawalniczych))\b",title) and not (work and stack)):
        verdict = NON_IT_CONFIRMED
        reason = "INDUSTRIAL_EQUIPMENT_PROGRAMMING"
        role_family = "industrial"
    elif (title_nontech and not title_tech and not borderline and
            ((nonwork is not None) or industry_nonit or STRONG_NONIT_TITLES.search(title) or nontechnical_work)):
        verdict = NON_IT_CONFIRMED
        reason = "EXPLICIT_NON_IT_OCCUPATION"
        role_family = nontech_family
    elif title_tech and not title_nontech and not borderline and (work or stack or admin_work) and (not industry_nonit or (work and stack)):
        verdict = IT_CONFIRMED
        reason = "TECH_ROLE_AND_DESCRIPTION_EVIDENCE"
    elif title_tech and not title_nontech and not borderline and industry_it and ACTIVITY_NOT_REQUIRED.search(title):
        # e.g. frontend developer with description solely listing React/TypeScript requirements.
        # Require a technical stack even for this abbreviated duty text.
        if stack:
            verdict = IT_CONFIRMED
            reason = "TECH_ROLE_AND_TECH_STACK"
    elif not title_nontech and not borderline and work and stack and industry_it:
        verdict = IT_CONFIRMED
        reason = "IT_INDUSTRY_AND_TWO_DESCRIPTION_SIGNALS"
        role_family = "technical_generalist"
    elif title_nontech and title_tech:
        reason = "CONFLICTING_ROLE_SIGNALS"
    elif borderline:
        reason = "IT_ADJACENT_OR_HYBRID_SCOPE"
    elif title_nontech and (work or stack) and not industry_nonit:
        reason = "NON_IT_TITLE_WITH_TECH_MENTION"
    elif title_tech and industry_nonit:
        reason = "IT_ROLE_CONTRADICTS_INDUSTRY"
    elif title_tech and not (work or stack):
        reason = "TECH_TITLE_WITHOUT_DESCRIPTION_SUPPORT"
    elif work or stack:
        reason = "TECH_CONTENT_WITHOUT_CLEAR_IT_ROLE"

    return {
        "status": verdict, "policy_version": POLICY_VERSION,
        "scope": SCOPE, "role_family": role_family,
        "reason_code": reason, "evidence": evidences,
    }
