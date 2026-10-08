"""Aplikuj category acquisition is lossless; IT suitability is a reviewable decision.

The category is a discovery source, not an IT truth oracle. The classifier
annotates observations; it never authorizes deletion or skipping a posting.
"""
from __future__ import annotations

import re
from bs4 import BeautifulSoup

from .aplikuj_it_scope import CORE, NON_TECHNICAL, normalized
from .model import ParsedPosting

APLIKUJ_SCOPE = "it-category-v2"
CLASSIFIER_VERSION = "aplikuj-evidence-v1"
IT_CONFIRMED = "IT_CONFIRMED"
NON_IT_CONFIRMED = "NON_IT_CONFIRMED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
STATUSES = (IT_CONFIRMED, NON_IT_CONFIRMED, REVIEW_REQUIRED)

# These are *work duties*, not simply a technology mentioned in an ad.
TECH_WORK = re.compile(
    r"\b(?:tworzen\w*|rozwijani\w*|projektowani\w*|implementac\w*|"
    r"utrzymani\w*|wdrazani\w*|konfigurowani\w*|administrowani\w*|"
    r"monitorowani\w*|testowani\w*|zabezpieczani\w*|automatyzac\w*|"
    r"development|developing|designing|implementing|maintaining|"
    r"deploying|configuring|monitoring|testing|securing|automating)\b"
    r".{0,90}\b(?:aplikac\w*|oprogramowani\w*|system\w* informatycz\w*|"
    r"sieci\w* komputerow\w*|infrastruktur\w* it|baz\w* danych|"
    r"kodu|api|backend|frontend|cyberbezpieczenstw\w*|cloud|"
    r"serwer\w*|platform\w* danych|software|application\w*|"
    r"database\w*|network\w*|infrastructure|code)\b"
)

OFF_TOPIC_INDUSTRIES = {
    "kierowca", "magazynier", "pracownik produkcji", "pracownik sprzatajacy",
    "operator maszyn", "pracownik fizyczny", "kucharz szef kuchni",
    "nauczyciel wychowania przedszkolnego", "budowlaniec", "kelner",
}
OFF_TOPIC_WORK = re.compile(
    r"\b(?:prowadzeni\w* pojazd\w*|przewoz\w* towar\w*|"
    r"kompletacj\w* zamowien|zaladun\w*|rozladun\w*|"
    r"obslug\w* maszyn produkcyjnych|prace budowlane|"
    r"sprzatani\w* pomieszczen|przygotowywani\w* posilkow)\b"
)


def _work_description(posting: ParsedPosting) -> str:
    semantic = posting.revision_projection or {}
    structured = semantic.get("jobposting_json_ld") or {}
    raw = structured.get("description") if isinstance(structured, dict) else None
    if not raw:
        raw = (posting.source_specific or {}).get("meta_description")
    if not raw:
        # HTML fallback may have no structured description. Insufficient evidence
        # cannot be upgraded into a confident assessment using the page chrome.
        return ""
    return normalized(BeautifulSoup(str(raw), "html.parser").get_text(" ", strip=True))


def assess(posting: ParsedPosting) -> dict:
    title = normalized(posting.title)
    raw_industry = (posting.source_specific or {}).get("industry")
    industry = normalized(raw_industry if isinstance(raw_industry, str) else "")
    duties = _work_description(posting)
    technical_title = bool(CORE.search(title)) and not bool(NON_TECHNICAL.search(title))
    technical_duties = bool(TECH_WORK.search(duties))
    nontechnical_title = bool(NON_TECHNICAL.search(title)) or not bool(CORE.search(title))
    nontechnical_industry = industry in OFF_TOPIC_INDUSTRIES
    nontechnical_duties = bool(OFF_TOPIC_WORK.search(duties))
    if technical_title and technical_duties and not nontechnical_industry:
        status = IT_CONFIRMED
        evidence = ["TECHNICAL_TITLE", "TECHNICAL_DUTIES"]
    elif nontechnical_title and nontechnical_industry and nontechnical_duties and not technical_duties:
        status = NON_IT_CONFIRMED
        evidence = ["NON_TECHNICAL_TITLE", "NON_TECHNICAL_INDUSTRY", "NON_TECHNICAL_DUTIES"]
    else:
        status = REVIEW_REQUIRED
        evidence = ["INSUFFICIENT_OR_CONFLICTING_EVIDENCE"]
        if technical_title:
            evidence.append("TECHNICAL_TITLE_ONLY")
        if technical_duties:
            evidence.append("TECHNICAL_DUTIES_ONLY")
        if nontechnical_industry:
            evidence.append("NON_TECHNICAL_INDUSTRY")
    return {"status": status, "policy_version": CLASSIFIER_VERSION, "evidence_codes": evidence}
