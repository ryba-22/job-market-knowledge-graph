from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
import json
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from .model import ParsedPosting, PostingRef, norm_text


TP_ID = re.compile(r"(01000000-[0-9a-f-]{20,})", re.I)


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


class SourceAdapter(ABC):
    code: str

    @abstractmethod
    def listing_urls(self) -> Iterable[str]:
        raise NotImplementedError

    @abstractmethod
    def parse_listing(self, html: str, base_url: str) -> list[PostingRef]:
        raise NotImplementedError

    @abstractmethod
    def parse_detail(self, html: str, url: str) -> ParsedPosting:
        raise NotImplementedError

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        out: dict[str, PostingRef] = {}
        for listing_url in self.listing_urls():
            response = client.get(listing_url)
            response.raise_for_status()
            before = len(out)
            for ref in self.parse_listing(response.text, str(response.url)):
                out.setdefault(ref.source_posting_id, ref)
                if len(out) >= limit:
                    return list(out.values())[:limit]
            if len(out) == before and out:
                break
        return list(out.values())[:limit]



NFJ_SEARCH_URL = "https://nofluffjobs.com/api/search/posting"
ROCKET_LISTING_BASE = "https://rocketjobs.pl/oferty-pracy/wszystkie-lokalizacje"
BULLDOG_LISTING_URL = "https://bulldogjob.com/companies/jobs"
BULLDOG_ID = re.compile(r"/companies/jobs/(\d+)-")


class NoFluffJobsAdapter(SourceAdapter):
    code = "nofluffjobs"

    def listing_urls(self):
        return ()

    def parse_listing(self, html: str, base_url: str) -> list[PostingRef]:
        data = json.loads(html)
        found = {}
        for item in data.get("postings", []):
            reference = norm_text(item.get("reference"))
            slug = norm_text(item.get("url") or item.get("id")).casefold()
            if not reference or not slug:
                continue
            url = f"https://nofluffjobs.com/pl/job/{slug}"
            found[reference] = PostingRef(self.code, url, reference)
        return list(found.values())

    def parse_detail(self, html: str, url: str) -> ParsedPosting:
        data = json.loads(html)
        sid = norm_text(data.get("reference"))
        if not sid:
            raise ValueError("PARSER_DRIFT: NFJ reference missing")
        title = norm_text(data.get("title"))
        if not title:
            raise ValueError("PARSER_DRIFT: NFJ title missing")
        company_obj = data.get("company") or {}
        company = norm_text(company_obj.get("name") or data.get("name")) or None
        specs = data.get("specs") or {}
        basics = data.get("basics") or {}
        requirements = data.get("requirements") or {}
        stable = {
            "title": title,
            "company": {
                "name": company,
                "url": company_obj.get("url"),
            },
            "basics": basics,
            "requirements": requirements,
            "dailyTasks": (specs.get("dailyTasks") or []),
            "location": data.get("location") or {},
            "salary": data.get("salary") or {},
            "apply": {
                "option": (data.get("apply") or {}).get("option"),
                "referenceNumber": (data.get("apply") or {}).get("referenceNumber"),
            },
        }
        return ParsedPosting(
            source=self.code,
            source_posting_id=sid,
            url=canonical_url(url),
            title=title,
            company_mention=company,
            body_text=json.dumps(data, ensure_ascii=False, sort_keys=True),
            source_specific={
                "category": basics.get("category"),
                "seniority": basics.get("seniority"),
                "requirements": requirements,
                "daily_tasks": specs.get("dailyTasks") or [],
                "reference": sid,
                "presentation_id": data.get("id"),
                "observation_provenance": "DIRECT_PUBLIC_API",
            },
            revision_projection=stable,
        )


class RocketJobsAdapter(SourceAdapter):
    code = "rocketjobs"

    def listing_urls(self):
        yield ROCKET_LISTING_BASE
        for page in range(2, 21):
            yield f"{ROCKET_LISTING_BASE}?strona={page}"

    def parse_listing(self, html: str, base_url: str) -> list[PostingRef]:
        soup = BeautifulSoup(html, "html.parser")
        found = {}
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/oferta-pracy/" not in href:
                continue
            url = canonical_url(urljoin(base_url, href))
            sid = url.rstrip("/").split("/oferta-pracy/")[-1]
            if sid:
                found[sid] = PostingRef(self.code, url, sid)
        return list(found.values())

    def parse_detail(self, html: str, url: str) -> ParsedPosting:
        soup = BeautifulSoup(html, "html.parser")
        structured = _jobposting_json_ld(soup)
        if not structured:
            raise ValueError("PARSER_DRIFT: Rocket JobPosting JSON-LD missing")
        sid = canonical_url(url).rstrip("/").split("/oferta-pracy/")[-1]
        title = norm_text(structured.get("title"))
        org = structured.get("hiringOrganization") or {}
        company = norm_text(org.get("name")) or None
        if not title or not sid:
            raise ValueError("PARSER_DRIFT: Rocket identity/title missing")
        return ParsedPosting(
            source=self.code,
            source_posting_id=sid,
            url=canonical_url(url),
            title=title,
            company_mention=company,
            body_text=soup.get_text("\n", strip=True),
            source_specific={
                "jobposting_json_ld": structured,
                "observation_provenance": "DIRECT_SSR",
            },
            revision_projection={"jobposting_json_ld": structured},
        )


class BulldogJobAdapter(SourceAdapter):
    code = "bulldogjob"

    def listing_urls(self):
        yield BULLDOG_LISTING_URL
        for page in range(2, 21):
            yield f"{BULLDOG_LISTING_URL}/s/page,{page}"

    def parse_listing(self, html: str, base_url: str) -> list[PostingRef]:
        soup = BeautifulSoup(html, "html.parser")
        found = {}
        for a in soup.find_all("a", href=True):
            url = canonical_url(urljoin(base_url, a["href"]))
            match = BULLDOG_ID.search(url)
            if not match:
                continue
            sid = match.group(1)
            found[sid] = PostingRef(self.code, url, sid)
        return list(found.values())

    def parse_detail(self, html: str, url: str) -> ParsedPosting:
        soup = BeautifulSoup(html, "html.parser")
        structured = _jobposting_json_ld(soup)
        match = BULLDOG_ID.search(canonical_url(url))
        if not structured or not match:
            raise ValueError("PARSER_DRIFT: Bulldog identity/JSON-LD missing")
        title = norm_text(structured.get("title"))
        org = structured.get("hiringOrganization") or {}
        company = norm_text(org.get("name")) or None
        if not title:
            raise ValueError("PARSER_DRIFT: Bulldog title missing")
        return ParsedPosting(
            source=self.code,
            source_posting_id=match.group(1),
            url=canonical_url(url),
            title=title,
            company_mention=company,
            body_text=soup.get_text("\n", strip=True),
            source_specific={
                "jobposting_json_ld": structured,
                "observation_provenance": "DIRECT_SSR",
            },
            revision_projection={"jobposting_json_ld": structured},
        )


class PracujMirrorAdapter(SourceAdapter):
    code = "pracuj"

    def listing_urls(self):
        return ()

    def parse_listing(self, html: str, base_url: str) -> list[PostingRef]:
        data = json.loads(html)
        found = {}
        for item in data.get("data", []):
            if item.get("offer_source") != "pracuj.pl":
                continue
            url = canonical_url(item.get("offer_href") or "")
            match = re.search(r",oferta,(\d+)", url)
            if not match:
                continue
            sid = match.group(1)
            found[sid] = PostingRef(self.code, url, sid)
        return list(found.values())

    def parse_detail(self, html: str, url: str) -> ParsedPosting:
        item = json.loads(html)
        if item.get("offer_source") != "pracuj.pl":
            raise ValueError("PARSER_DRIFT: Pracuj mirror upstream source mismatch")
        source_url = canonical_url(item.get("offer_href") or url)
        match = re.search(r",oferta,(\d+)", source_url)
        if not match:
            raise ValueError("PARSER_DRIFT: Pracuj upstream offer id missing")
        company_obj = item.get("company") or {}
        title = norm_text(item.get("offer_title"))
        company = norm_text(company_obj.get("company_name")) or None
        if not title:
            raise ValueError("PARSER_DRIFT: Pracuj mirror title missing")
        stable = {
            "title": title,
            "company": company,
            "city": item.get("offer_city"),
            "remote": item.get("offer_remote_available"),
            "category": item.get("offer_category"),
            "technologies": sorted(item.get("offer_technologies") or []),
            "salary": {
                "interval": item.get("offer_salary_interval"),
                "min": item.get("offer_salary_min"),
                "max": item.get("offer_salary_max"),
                "currency": item.get("offer_salary_currency"),
            },
            "published_at": item.get("offer_published_at"),
        }
        return ParsedPosting(
            source=self.code,
            source_posting_id=match.group(1),
            url=source_url,
            title=title,
            company_mention=company,
            body_text=json.dumps(item, ensure_ascii=False, sort_keys=True),
            source_specific={
                "upstream_source": "pracuj.pl",
                "mirror": "isitfair.pl",
                "mirror_offer_uuid": item.get("offer_uuid"),
                "technologies": item.get("offer_technologies") or [],
                "observation_provenance": "SECONDARY_PUBLIC_INDEX",
            },
            revision_projection=stable,
        )


class TheProtocolAdapter(SourceAdapter):
    code = "theprotocol"

    SITEMAP_URL = "https://static.theprotocol.it/sitemaps/CurrentOffers/SiteMapJobOffers1.xml"

    def listing_urls(self):
        yield self.SITEMAP_URL

    def parse_listing(self, html: str, base_url: str) -> list[PostingRef]:
        # CurrentOffers sitemap is a public discovery surface and avoids coupling
        # discovery to the Cloudflare-protected interactive listing.
        import xml.etree.ElementTree as ET
        found: dict[str, PostingRef] = {}
        root = ET.fromstring(html)
        for node in root.iter():
            if not node.tag.endswith("loc") or not node.text:
                continue
            url = canonical_url(node.text.strip())
            if "/szczegoly/praca/" not in url:
                continue
            match = TP_ID.search(url)
            if not match:
                continue
            sid = match.group(1)
            found[sid] = PostingRef(self.code, url, sid)
        return list(found.values())

    def parse_detail(self, html: str, url: str) -> ParsedPosting:
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        if not h1:
            raise ValueError("PARSER_DRIFT: TheProtocol h1 missing")
        match = TP_ID.search(url)
        if not match:
            raise ValueError("TheProtocol source ID missing")
        company = _first_text(
            soup,
            [
                '[data-test="text-offerEmployer"]',
                '[data-testid="company-name"]',
                ".company-name",
            ],
        ) or _best_company_heading(soup, h1)
        text = soup.get_text("\n", strip=True)
        ai_derived = bool(re.search(r"wygenerowane przez AI|generated by AI", text, re.I))
        return ParsedPosting(
            source=self.code,
            source_posting_id=match.group(1),
            url=canonical_url(url),
            title=norm_text(h1.get_text(" ", strip=True)),
            company_mention=company,
            body_text=text,
            source_specific={"platform_ai_summary_present": ai_derived},
        )


class JustJoinItAdapter(SourceAdapter):
    code = "justjoinit"

    def listing_urls(self):
        yield "https://justjoin.it/job-offers/all-locations"
        for page in range(2, 31):
            yield f"https://justjoin.it/job-offers/all-locations?page={page}"

    def parse_listing(self, html: str, base_url: str) -> list[PostingRef]:
        soup = BeautifulSoup(html, "html.parser")
        found: dict[str, PostingRef] = {}
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/job-offer/" not in href:
                continue
            url = canonical_url(urljoin(base_url, href))
            sid = url.rstrip("/").split("/")[-1]
            if not sid:
                continue
            found[sid] = PostingRef(self.code, url, sid)
        return list(found.values())

    def parse_detail(self, html: str, url: str) -> ParsedPosting:
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        if not h1:
            raise ValueError("PARSER_DRIFT: JJIT h1 missing")
        sid = canonical_url(url).rstrip("/").split("/")[-1]
        company = _first_text(
            soup,
            ['[data-testid="company-name"]', ".company-name"],
        ) or _best_company_heading(soup, h1)
        skills = []
        for node in soup.select("[data-skill][data-level]"):
            skills.append({"skill": node.get("data-skill"), "level": node.get("data-level")})

        structured = _jobposting_json_ld(soup)
        sections = _stable_sections(soup)
        revision_projection = {
            "jobposting_json_ld": structured or {},
            "stable_sections": sections,
            "skill_expectations": sorted(
                skills,
                key=lambda item: (
                    norm_text(item.get("skill")).casefold(),
                    norm_text(item.get("level")).casefold(),
                ),
            ),
        }
        # Never hash the full rendered document for JJIT. Raw HTML remains in
        # RawObservation; revisions track only job semantics.
        return ParsedPosting(
            source=self.code,
            source_posting_id=sid,
            url=canonical_url(url),
            title=norm_text(h1.get_text(" ", strip=True)),
            company_mention=company,
            body_text=soup.get_text("\n", strip=True),
            source_specific={"skill_expectations": skills},
            revision_projection=revision_projection,
        )


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            value = norm_text(node.get_text(" ", strip=True))
            if value:
                return value
    return None


def _best_company_heading(soup: BeautifulSoup, h1) -> str | None:
    blocked = {
        "job description", "tech stack", "requirements", "responsibilities",
        "nice to have", "benefits", "about the company", "o firmie",
    }
    for node in h1.find_all_next(["h2", "h3"]):
        value = norm_text(node.get_text(" ", strip=True))
        if value and value.casefold() not in blocked and len(value) <= 160:
            return value
    return None


ADAPTERS = {
    "theprotocol": TheProtocolAdapter(),
    "justjoinit": JustJoinItAdapter(),
    "nofluffjobs": NoFluffJobsAdapter(),
    "rocketjobs": RocketJobsAdapter(),
    "bulldogjob": BulldogJobAdapter(),
    "pracuj": PracujMirrorAdapter(),
}


def _jobposting_json_ld(soup: BeautifulSoup):
    """Return stable JobPosting structured data, excluding volatile presentation metadata."""
    candidates = []
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = node.string or node.get_text()
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except Exception:
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                candidates.append(item)
            if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                candidates.extend(
                    x for x in item["@graph"]
                    if isinstance(x, dict) and x.get("@type") == "JobPosting"
                )
    if not candidates:
        return None
    item = candidates[0]
    stable_keys = (
        "title", "description", "qualifications", "skills", "responsibilities",
        "employmentType", "jobLocationType", "applicantLocationRequirements",
        "jobLocation", "baseSalary", "hiringOrganization", "industry",
        "experienceRequirements", "educationRequirements",
    )
    return {k: item[k] for k in stable_keys if k in item}


def _stable_sections(soup: BeautifulSoup):
    """Conservative fallback: only job-content sections, never full rendered page chrome."""
    wanted = {
        "job description", "responsibilities", "requirements", "nice to have",
        "tech stack", "benefits", "about the company", "about us",
    }
    out = {}
    headings = soup.find_all(["h2", "h3"])
    for heading in headings:
        name = norm_text(heading.get_text(" ", strip=True))
        if name.casefold() not in wanted:
            continue
        parts = []
        for node in heading.find_all_next():
            if node is heading:
                continue
            if getattr(node, "name", None) in ("h2", "h3"):
                break
            if getattr(node, "name", None) in ("p", "li", "h4"):
                text = norm_text(node.get_text(" ", strip=True))
                if text and text not in parts:
                    parts.append(text)
        out[name.casefold()] = parts
    return out
