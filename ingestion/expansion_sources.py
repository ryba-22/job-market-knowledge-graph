from __future__ import annotations

import gzip
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .model import ParsedPosting, PostingRef, norm_text
from .sources import _jobposting_json_ld, _stable_sections, canonical_url


NFJ_SEARCH_URL = "https://nofluffjobs.com/api/search/posting"
NFJ_DETAIL_URL = "https://nofluffjobs.com/api/posting/{slug}"
ROCKET_SITEMAP_INDEX = "https://rocketjobs.pl/sitemaps/active-jobs.xml"
BULLDOG_JOBS_SITEMAP = "https://bulldogjob.com/en/jobs.xml.gz"
ISITFAIR_SEARCH_URL = "https://isitfair.pl/api/v1/offers/search"
PRACUJ_SEARCH_TERMS = (
    "developer","engineer","programista","java","python","devops","data","tester",
    "analityk","administrator","cloud","security","frontend","backend","fullstack",
    "architect","ai","mlops","scrum","product","software","kubernetes","sql","automation",
)


class NoFluffJobsSource:
    code = "nofluffjobs"

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        refs = []
        seen_references = set()
        page = 1
        while len(refs) < limit:
            response = client.post(
                NFJ_SEARCH_URL,
                params={
                    "salaryCurrency": "original",
                    "salaryPeriod": "original",
                    "region": "pl",
                    "page": page,
                },
                json={"criteriaSearch": {}},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            rows = response.json().get("postings", [])
            if not rows:
                break
            before = len(refs)
            for row in rows:
                reference = row.get("reference")
                slug = row.get("url") or row.get("id")
                if not reference or not slug or reference in seen_references:
                    continue
                seen_references.add(reference)
                refs.append(
                    PostingRef(
                        self.code,
                        f"https://nofluffjobs.com/pl/job/{slug}",
                        str(reference),
                    )
                )
                if len(refs) >= limit:
                    break
            if len(refs) == before:
                break
            page += 1
        return refs

    def fetch_detail(self, client: httpx.Client, ref: PostingRef):
        slug = ref.url.rstrip("/").split("/")[-1]
        response = client.get(
            NFJ_DETAIL_URL.format(slug=slug),
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return response.text, str(response.url), response.status_code, response.headers.get("content-type", "")

    def parse_detail(self, raw: str, ref: PostingRef) -> ParsedPosting:
        data = json.loads(raw)
        slug = data.get("postingUrl") or data.get("defaultUrl") or data.get("id") or ref.source_posting_id
        company = (data.get("company") or {}).get("name")
        stable_keys = (
            "title", "basics", "company", "details", "essentials", "requirements",
            "specs", "methodology", "recruitment", "benefits", "location",
            "reference", "status", "expiresAt", "apply",
        )
        revision_projection = {k: data[k] for k in stable_keys if k in data}
        return ParsedPosting(
            source=self.code,
            source_posting_id=ref.source_posting_id,
            url=f"https://nofluffjobs.com/pl/job/{slug}",
            title=norm_text(data.get("title")),
            company_mention=norm_text(company) or None,
            body_text=raw,
            source_specific={
                "reference": data.get("reference"),
                "canonical_posting_slug": slug,
                "status": data.get("status"),
                "version": data.get("version"),
                "company_url": data.get("companyUrl"),
                "posting_url": data.get("postingUrl"),
            },
            revision_projection=revision_projection,
        )


class RocketJobsSource:
    code = "rocketjobs"

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        index = client.get(ROCKET_SITEMAP_INDEX)
        index.raise_for_status()
        root = ET.fromstring(index.text)
        sitemap_urls = [n.text.strip() for n in root.iter() if n.tag.endswith("loc") and n.text]
        refs = []
        seen = set()
        for sitemap_url in sitemap_urls:
            response = client.get(sitemap_url)
            response.raise_for_status()
            sitemap = ET.fromstring(response.text)
            for node in sitemap.iter():
                if not node.tag.endswith("loc") or not node.text:
                    continue
                url = canonical_url(node.text.strip())
                marker = "/oferta-pracy/"
                if marker not in url:
                    continue
                slug = url.split(marker, 1)[1].strip("/")
                if not slug or slug in seen:
                    continue
                seen.add(slug)
                refs.append(PostingRef(self.code, url, slug))
                if len(refs) >= limit:
                    return refs
        return refs

    def fetch_detail(self, client: httpx.Client, ref: PostingRef):
        response = client.get(ref.url)
        response.raise_for_status()
        return response.text, str(response.url), response.status_code, response.headers.get("content-type", "")

    def parse_detail(self, raw: str, ref: PostingRef) -> ParsedPosting:
        soup = BeautifulSoup(raw, "html.parser")
        structured = _jobposting_json_ld(soup)
        if not structured:
            raise ValueError("PARSER_DRIFT: RocketJobs JobPosting JSON-LD missing")
        title = structured.get("title")
        hiring = structured.get("hiringOrganization") or {}
        company = hiring.get("name") if isinstance(hiring, dict) else None
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(" ", strip=True) if h1 else None
        if not title:
            raise ValueError("PARSER_DRIFT: RocketJobs title missing")
        return ParsedPosting(
            source=self.code,
            source_posting_id=ref.source_posting_id,
            url=canonical_url(ref.url),
            title=norm_text(title),
            company_mention=norm_text(company) or None,
            body_text=soup.get_text("\n", strip=True),
            source_specific={
                "hiring_organization": hiring,
                "date_posted": structured.get("datePosted"),
                "valid_through": structured.get("validThrough"),
                "employment_type": structured.get("employmentType"),
            },
            revision_projection={
                "jobposting_json_ld": structured,
                "stable_sections": _stable_sections(soup),
            },
        )


class BulldogJobSource:
    code = "bulldogjob"

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        response = client.get(BULLDOG_JOBS_SITEMAP)
        response.raise_for_status()
        data = response.content
        try:
            xml = gzip.decompress(data).decode("utf-8")
        except OSError:
            xml = response.text
        root = ET.fromstring(xml)
        refs = []
        seen = set()
        for node in root.iter():
            if not node.tag.endswith("loc") or not node.text:
                continue
            url = canonical_url(node.text.strip())
            marker = "/companies/jobs/"
            if marker not in url:
                continue
            tail = url.split(marker, 1)[1].strip("/")
            match = re.match(r"(\d+)-", tail)
            if not match:
                continue
            source_id = match.group(1)
            if source_id in seen:
                continue
            seen.add(source_id)
            refs.append(PostingRef(self.code, url, source_id))
            if len(refs) >= limit:
                break
        return refs

    def fetch_detail(self, client: httpx.Client, ref: PostingRef):
        response = client.get(ref.url)
        response.raise_for_status()
        return response.text, str(response.url), response.status_code, response.headers.get("content-type", "")

    def parse_detail(self, raw: str, ref: PostingRef) -> ParsedPosting:
        soup = BeautifulSoup(raw, "html.parser")
        structured = _jobposting_json_ld(soup)
        if not structured:
            raise ValueError("PARSER_DRIFT: Bulldogjob JobPosting JSON-LD missing")
        title = structured.get("title")
        hiring = structured.get("hiringOrganization") or {}
        company = hiring.get("name") if isinstance(hiring, dict) else None
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(" ", strip=True) if h1 else None
        if not title:
            raise ValueError("PARSER_DRIFT: Bulldogjob title missing")
        return ParsedPosting(
            source=self.code,
            source_posting_id=ref.source_posting_id,
            url=canonical_url(ref.url),
            title=norm_text(title),
            company_mention=norm_text(company) or None,
            body_text=soup.get_text("\n", strip=True),
            source_specific={
                "jobposting_id": structured.get("@id"),
                "hiring_organization": hiring,
                "skills": structured.get("skills"),
                "date_posted": structured.get("datePosted"),
                "valid_through": structured.get("validThrough"),
                "employment_type": structured.get("employmentType"),
            },
            revision_projection={
                "jobposting_json_ld": structured,
                "stable_sections": _stable_sections(soup),
            },
        )


class PracujSecondarySource:
    code = "pracuj"

    def discover_records(self, client: httpx.Client, limit: int):
        found = {}
        for term in PRACUJ_SEARCH_TERMS:
            response = client.get(
                ISITFAIR_SEARCH_URL,
                params={"search": term, "offer_status": "active"},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            for item in response.json().get("data", []):
                if item.get("offer_source") != "pracuj.pl":
                    continue
                source_url = canonical_url(item.get("offer_href") or "")
                match = re.search(r",oferta,(\d+)", source_url)
                if not match:
                    continue
                sid = match.group(1)
                if sid in found:
                    continue
                found[sid] = (
                    PostingRef(self.code, source_url, sid),
                    item,
                    str(response.url),
                )
                if len(found) >= limit:
                    return list(found.values())[:limit]
        return list(found.values())[:limit]

    def parse_detail(self, raw: str, ref: PostingRef) -> ParsedPosting:
        item = json.loads(raw)
        if item.get("offer_source") != "pracuj.pl":
            raise ValueError("PARSER_DRIFT: Pracuj mirror upstream source mismatch")
        source_url = canonical_url(item.get("offer_href") or ref.url)
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


SOURCES = {
    "nofluffjobs": NoFluffJobsSource(),
    "rocketjobs": RocketJobsSource(),
    "bulldogjob": BulldogJobSource(),
    "pracuj": PracujSecondarySource(),
}
