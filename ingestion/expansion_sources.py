from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from .model import ParsedPosting, PostingRef, norm_text
from .sources import _jobposting_json_ld, _stable_sections, canonical_url


NFJ_SEARCH_URL = "https://nofluffjobs.com/api/search/posting"
NFJ_DETAIL_URL = "https://nofluffjobs.com/api/posting/{slug}"
ROCKET_SITEMAP_INDEX = "https://rocketjobs.pl/sitemaps/active-jobs.xml"


class NoFluffJobsSource:
    code = "nofluffjobs"

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        response = client.post(
            NFJ_SEARCH_URL,
            params={"salaryCurrency": "original", "salaryPeriod": "original", "region": "pl"},
            json={"criteriaSearch": {}},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        refs = []
        seen = set()
        for row in response.json().get("postings", []):
            slug = row.get("url") or row.get("id")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            refs.append(PostingRef(self.code, f"https://nofluffjobs.com/pl/job/{slug}", slug))
            if len(refs) >= limit:
                break
        return refs

    def fetch_detail(self, client: httpx.Client, ref: PostingRef):
        response = client.get(
            NFJ_DETAIL_URL.format(slug=ref.source_posting_id),
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
            source_posting_id=str(slug),
            url=f"https://nofluffjobs.com/pl/job/{slug}",
            title=norm_text(data.get("title")),
            company_mention=norm_text(company) or None,
            body_text=raw,
            source_specific={
                "reference": data.get("reference"),
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


SOURCES = {
    "nofluffjobs": NoFluffJobsSource(),
    "rocketjobs": RocketJobsSource(),
}
