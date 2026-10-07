"""Conservative technical-IT scope for Aplikuj.pl.

The site's IT category is a discovery surface, not proof that every sponsored
or keyword-matched job is a technical IT position. Uncertain titles are excluded
from the automatic technical-IT corpus for manual review.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse


def normalized(value: str | None) -> str:
    raw = unicodedata.normalize("NFKD", (value or "").casefold().replace("ł", "l"))
    plain = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


CORE = re.compile(
    r"\b(?:developer|programist\w*|programowanie|frontend|front end|backend|back end|"
    r"fullstack|full stack|devops|sre|site reliability|cloud engineer|"
    r"data engineer|data scientist|data analyst|inzynier danych|analityk danych|"
    r"machine learning|mlops|ai engineer|inzynier ai|inzynier sztucznej inteligencji|"
    r"llm engineer|aiops|informatyk\w*|cyberbezpieczenstw\w*|cybersecurity|"
    r"pentester|penetration tester|security engineer|"
    r"tester oprogramowania|test engineer|qa engineer|qa automation|"
    r"network engineer|inzynier sieci komputerowych|"
    r"administrator systemow|administrator baz danych|administrator sieci|"
    r"system administrator|database administrator|"
    r"it support|support it|it specialist|specjalist\w* it|"
    r"specjalist\w* ds it|helpdesk|help desk|service desk|"
    r"it architect|architekt it|architekt oprogramowania|"
    r"software engineer|software architect|software tester|"
    r"wdrozeniowiec|konsultant oprogramowania|konsultant erp|sap consultant|"
    r"it analyst|it process manager|analityk systemowo biznesowy|"
    r"administrator infrastruktury teleinformatycznej|wms system specialist|"
    r"ux designer|ui designer|product owner|scrum master|"
    r"administrator it|technik informatyk|specjalista ds infrastruktury it)\b"
)
NON_TECHNICAL = re.compile(
    r"\b(?:sprzedaz\w*|handlow\w*|pozyskiwani\w* klient\w*|"
    r"telemarketer\w*|doradc\w* klient\w*|obsluga klienta|"
    r"przedstawiciel\w*|monter\w*|instalator\w*|"
    r"robotow przemyslowych|sterownikow plc|"
    r"nauczyciel\w*|trener zajec|szkoleniowiec|"
    r"tester produktow|tester zywnosci|"
    r"fotowoltaik\w*|it ar|itar|technik audiowizualny|"
    r"\bcnc\b|\bcam\b|tokar\w*|frezar\w*|obrabiar\w*|"
    r"robotow spawalniczych|programista produkcji|technolog programista|"
    r"programist\w* maszyn|automatyk programista|"
    r"zajec z informatyki|zajec informatycznych|"
    r"social media|specjalista seo|grafik komputerowy)\b"
)


def is_technical_it(title: str, industry: str | None = None) -> bool:
    """Technical IT is an explicit title signal, not an industry/keyword guess."""
    t = normalized(title)
    if NON_TECHNICAL.search(t):
        return False
    return bool(CORE.search(t))


def is_it_listing_candidate(title: str) -> bool:
    return is_technical_it(title)


def title_from_url(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return slug.replace("-", " ")


def is_legacy_it_candidate(url: str) -> bool:
    """For advisory migration of the unscoped historical inventory only."""
    return is_it_listing_candidate(title_from_url(url))
