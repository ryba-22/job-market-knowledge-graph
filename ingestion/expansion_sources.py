from __future__ import annotations

import gzip
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .model import ParsedPosting, PostingRef, SourceGoneError, norm_text
from .sources import _jobposting_json_ld, _stable_sections, canonical_url


NFJ_SEARCH_URL = "https://nofluffjobs.com/api/search/posting"
NFJ_DETAIL_URL = "https://nofluffjobs.com/api/posting/{slug}"
ROCKET_SITEMAP_INDEX = "https://rocketjobs.pl/sitemaps/active-jobs.xml"
BULLDOG_JOBS_SITEMAP = "https://bulldogjob.com/en/jobs.xml.gz"
SOLID_JOBS_SITEMAP = "https://solid.jobs/sitemap-offers.xml"
TEAMQUEST_JOBS_SITEMAP = "https://teamquest.pl/sitemap/praca.xml"
APLIKUJ_SITEMAP_INDEX = "https://www.aplikuj.pl/sitemap/offer_index.xml"
ITLEADERS_LISTING_URL = "https://it-leaders.pl/oferty-pracy"
MICHAELPAGE_LISTING_URL = "https://www.michaelpage.pl/en/jobs"
EUROTECHJOBS_SITEMAP = "https://www.eurotechjobs.com/sitemap.xml"
HN_WHOISHIRING_THREAD_ID = "49922569"
HN_API_ITEM = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
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
        canonical = soup.find("link", attrs={"rel": "canonical"})
        canonical_href = canonical.get("href") if canonical else None
        if not structured:
            body_text = soup.get_text("\n", strip=True)
            archived = "Oferta archiwalna" in body_text
            h1 = soup.find("h1")
            title = norm_text(h1.get_text(" ", strip=True) if h1 else None)
            company_link = soup.select_one(".company_all_offers_link")
            company = norm_text(company_link.get_text(" ", strip=True) if company_link else None)
            company = re.sub(r"^Praca\s+", "", company, flags=re.I).strip()
            if not archived or not title or not company:
                raise ValueError("PARSER_DRIFT: RocketJobs JobPosting JSON-LD missing")
            return ParsedPosting(
                source=self.code,
                source_posting_id=ref.source_posting_id,
                url=canonical_url(canonical_href or ref.url),
                title=title,
                company_mention=company,
                body_text=body_text,
                source_specific={
                    "hiring_organization": {"name": company},
                    "date_posted": None,
                    "valid_through": None,
                    "employment_type": None,
                    "observation_provenance": "DIRECT",
                    "parse_mode": "HTML_FALLBACK",
                    "archived": True,
                },
                revision_projection={
                    "html_fallback": {
                        "title": title,
                        "company": company,
                        "archived": True,
                    },
                    "stable_sections": _stable_sections(soup),
                },
            )
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
            url=canonical_url(canonical_href or ref.url),
            title=norm_text(title),
            company_mention=norm_text(company) or None,
            body_text=soup.get_text("\n", strip=True),
            source_specific={
                "hiring_organization": hiring,
                "date_posted": structured.get("datePosted"),
                "valid_through": structured.get("validThrough"),
                "employment_type": structured.get("employmentType"),
                "observation_provenance": "DIRECT",
                "parse_mode": "JSON_LD",
                "archived": False,
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


class SolidJobsSource:
    code = "solidjobs"

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        response = client.get(SOLID_JOBS_SITEMAP)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        refs = []
        seen = set()
        for node in root.iter():
            if not node.tag.endswith("loc") or not node.text:
                continue
            url = canonical_url(node.text.strip())
            match = re.search(r"/offer/(\d+)(?:/|$)", url)
            if not match:
                continue
            sid = match.group(1)
            if sid in seen:
                continue
            seen.add(sid)
            refs.append(PostingRef(self.code, url, sid))
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
        if structured:
            identifier = structured.get("identifier") or {}
            sid = str(identifier.get("value") or ref.source_posting_id)
            title = norm_text(structured.get("title"))
            hiring = structured.get("hiringOrganization") or {}
            company = hiring.get("name") if isinstance(hiring, dict) else None
            if not title:
                raise ValueError("PARSER_DRIFT: SOLID.Jobs title missing")
            source_specific = {
                "identifier": identifier,
                "hiring_organization": hiring,
                "date_posted": structured.get("datePosted"),
                "date_modified": structured.get("dateModified"),
                "valid_through": structured.get("validThrough"),
                "employment_type": structured.get("employmentType"),
                "base_salary": structured.get("baseSalary"),
                "skills": structured.get("skills"),
                "direct_apply": structured.get("directApply"),
                "observation_provenance": "DIRECT",
                "parse_mode": "JSON_LD",
            }
            revision_projection = {
                "jobposting_json_ld": structured,
                "stable_sections": _stable_sections(soup),
            }
            url = canonical_url(structured.get("url") or ref.url)
        else:
            h1 = soup.find("h1")
            title = norm_text(h1.get_text(" ", strip=True) if h1 else None)
            if not title:
                page_title = norm_text(soup.title.get_text(" ", strip=True) if soup.title else None)
                if page_title == "SOLID.Jobs – Platforma rekrutacyjna dla specjalistów":
                    raise SourceGoneError("SOLID.Jobs generic app shell: posting detail no longer exposed")
                raise ValueError("PARSER_DRIFT: SOLID.Jobs title missing")
            canonical = soup.find("link", attrs={"rel": "canonical"})
            canonical_href = canonical.get("href") if canonical else None
            url = canonical_url(canonical_href or ref.url)
            match = re.search(r"/offer/(\d+)(?:/|$)", url)
            sid = match.group(1) if match else ref.source_posting_id
            og_site = soup.find("meta", attrs={"property": "og:site_name"})
            og_desc = soup.find("meta", attrs={"property": "og:description"})
            company_meta = soup.find("meta", attrs={"name": "author"})
            company = company_meta.get("content") if company_meta else None
            source_specific = {
                "identifier": {"value": sid},
                "hiring_organization": {"name": company} if company else {},
                "meta_description": og_desc.get("content") if og_desc else None,
                "site_name": og_site.get("content") if og_site else None,
                "observation_provenance": "DIRECT",
                "parse_mode": "HTML_FALLBACK",
            }
            revision_projection = {
                "html_fallback": {
                    "title": title,
                    "company": norm_text(company) or None,
                    "meta_description": og_desc.get("content") if og_desc else None,
                },
                "stable_sections": _stable_sections(soup),
            }
        return ParsedPosting(
            source=self.code,
            source_posting_id=str(sid),
            url=url,
            title=title,
            company_mention=norm_text(company) or None,
            body_text=soup.get_text("\n", strip=True),
            source_specific=source_specific,
            revision_projection=revision_projection,
        )


class TeamQuestSource:
    code = "teamquest"

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        response = client.get(TEAMQUEST_JOBS_SITEMAP)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        refs = []
        seen = set()
        for node in root.iter():
            if not node.tag.endswith("loc") or not node.text:
                continue
            url = canonical_url(node.text.strip())
            match = re.search(r"/(?:[^/]+/)?(\d+)-praca-", url)
            if not match:
                continue
            sid = match.group(1)
            if sid in seen:
                continue
            seen.add(sid)
            refs.append(PostingRef(self.code, url, sid))
            if len(refs) >= limit:
                break
        return refs

    def fetch_detail(self, client: httpx.Client, ref: PostingRef):
        response = client.get(ref.url)
        response.raise_for_status()
        return response.text, str(response.url), response.status_code, response.headers.get("content-type", "")

    def parse_detail(self, raw: str, ref: PostingRef) -> ParsedPosting:
        soup = BeautifulSoup(raw, "html.parser")
        h1 = soup.find("h1")
        title = norm_text(h1.get_text(" ", strip=True) if h1 else None)
        if not title:
            raise ValueError("PARSER_DRIFT: TeamQuest title missing")
        job_id = None
        hidden = soup.find("input", attrs={"name": "joborder_id"})
        if hidden:
            job_id = hidden.get("value")
        sid = str(job_id or ref.source_posting_id)
        location_meta = soup.find("meta", attrs={"itemprop": "addressLocality"})
        date_meta = soup.find("meta", attrs={"itemprop": "datePosted"})
        salary = soup.find("span", class_="job-sallary")
        min_meta = salary.find("meta", attrs={"itemprop": "minValue"}) if salary else None
        max_meta = salary.find("meta", attrs={"itemprop": "maxValue"}) if salary else None
        currency_meta = salary.find("meta", attrs={"itemprop": "currency"}) if salary else None
        contract = soup.select_one(".contract__types")
        experience = soup.select_one(".experience__levels")
        tech = [norm_text(x.get_text(" ", strip=True)) for x in soup.select("h3 + .tags a, .tags a, .tag") if norm_text(x.get_text(" ", strip=True))]
        meta_desc = soup.find("meta", attrs={"name": "description"})
        return ParsedPosting(
            source=self.code,
            source_posting_id=sid,
            url=canonical_url(ref.url),
            title=title,
            company_mention="TeamQuest",
            body_text=soup.get_text("\n", strip=True),
            source_specific={
                "advertiser": "TeamQuest",
                "joborder_id": sid,
                "location": location_meta.get("content") if location_meta else None,
                "date_posted": date_meta.get("content") if date_meta else None,
                "salary": {
                    "min": min_meta.get("content") if min_meta else None,
                    "max": max_meta.get("content") if max_meta else None,
                    "currency": currency_meta.get("content") if currency_meta else None,
                },
                "contract": norm_text(contract.get_text(" ", strip=True)) if contract else None,
                "experience": norm_text(experience.get_text(" ", strip=True)) if experience else None,
                "technologies": sorted(set(tech)),
                "meta_description": meta_desc.get("content") if meta_desc else None,
                "observation_provenance": "DIRECT",
            },
            revision_projection={
                "title": title,
                "source_specific": {
                    "location": location_meta.get("content") if location_meta else None,
                    "date_posted": date_meta.get("content") if date_meta else None,
                    "salary_min": min_meta.get("content") if min_meta else None,
                    "salary_max": max_meta.get("content") if max_meta else None,
                    "salary_currency": currency_meta.get("content") if currency_meta else None,
                    "contract": norm_text(contract.get_text(" ", strip=True)) if contract else None,
                    "experience": norm_text(experience.get_text(" ", strip=True)) if experience else None,
                    "technologies": sorted(set(tech)),
                },
                "stable_sections": _stable_sections(soup),
            },
        )


class AplikujSource:
    code = "aplikuj"

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        from .aplikuj_it_scope import is_it_listing_candidate

        # The full offer sitemap includes all professions, not just IT.
        # The category listing still contains promoted/unrelated cards, hence
        # the additional conservative job-title check.
        refs = []
        seen = set()
        for page in range(1, 101):
            page_url = "https://www.aplikuj.pl/praca/it-informatyka"
            if page > 1:
                page_url += f"/strona-{page}"
            response = client.get(page_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select("li.offer-card a.offer-title[href]")
            if not cards:
                break
            new_ids = 0
            for link in cards:
                title = norm_text(link.get_text(" ", strip=True))
                target = canonical_url(link.get("href", ""))
                match = re.search(r"/oferta/(\d+)(?:/|$)", target)
                if not match or not is_it_listing_candidate(title):
                    continue
                sid = match.group(1)
                if sid in seen:
                    continue
                seen.add(sid)
                new_ids += 1
                refs.append(PostingRef(self.code, target, sid))
                if len(refs) >= limit:
                    return refs
            if not soup.select(f'a[href$="strona-{page + 1}"]'):
                break
        return refs

    def fetch_detail(self, client: httpx.Client, ref: PostingRef):
        response = client.get(ref.url)
        response.raise_for_status()
        return response.text, str(response.url), response.status_code, response.headers.get("content-type", "")

    def parse_detail(self, raw: str, ref: PostingRef) -> ParsedPosting:
        soup = BeautifulSoup(raw, "html.parser")
        structured = _jobposting_json_ld(soup)
        title_tag = norm_text(soup.title.get_text(" ", strip=True) if soup.title else None)
        if not structured and "Strona nie została znaleziona" in title_tag:
            raise SourceGoneError("Aplikuj.pl offer no longer exposed")
        canonical = soup.find("link", attrs={"rel": "canonical"})
        canonical_href = canonical.get("href") if canonical else None
        if not structured:
            h1 = soup.find("h1")
            title = norm_text(h1.get_text(" ", strip=True) if h1 else None)
            if not title:
                raise ValueError("PARSER_DRIFT: Aplikuj title missing")
            employer = soup.select_one(".offer-employer-header__company")
            company = norm_text(employer.get_text(" ", strip=True) if employer else None)
            company = re.sub(r"^Pracodawca\s*-\s*", "", company, flags=re.I).strip()
            meta_desc_tag = soup.find("meta", attrs={"name": "description"})
            meta_description = norm_text(meta_desc_tag.get("content") if meta_desc_tag else None)
            if not company and meta_description:
                match = re.search(r"Pracownika poszukuje firma\s+(.+?)\.\s*Aplikuj", meta_description, re.I)
                company = norm_text(match.group(1)) if match else ""
            return ParsedPosting(
                source=self.code,
                source_posting_id=ref.source_posting_id,
                url=canonical_url(canonical_href or ref.url),
                title=title,
                company_mention=company or None,
                body_text=soup.get_text("\n", strip=True),
                source_specific={
                    "hiring_organization": {"name": company} if company else {},
                    "date_posted": None,
                    "valid_through": None,
                    "employment_type": None,
                    "industry": None,
                    "occupational_category": None,
                    "job_location": None,
                    "salary_currency": None,
                    "direct_apply": None,
                    "observation_provenance": "DIRECT",
                    "discovery_scope": "it-category-listing-filtered",
                    "parse_mode": "HTML_FALLBACK",
                    "meta_description": meta_description or None,
                },
                revision_projection={
                    "html_fallback": {
                        "title": title,
                        "company": company or None,
                        "meta_description": meta_description or None,
                    },
                    "stable_sections": _stable_sections(soup),
                },
            )
        title = norm_text(structured.get("title"))
        hiring = structured.get("hiringOrganization") or {}
        company = hiring.get("name") if isinstance(hiring, dict) else None
        if not title:
            raise ValueError("PARSER_DRIFT: Aplikuj title missing")
        return ParsedPosting(
            source=self.code,
            source_posting_id=ref.source_posting_id,
            url=canonical_url(canonical_href or ref.url),
            title=title,
            company_mention=norm_text(company) or None,
            body_text=soup.get_text("\n", strip=True),
            source_specific={
                "hiring_organization": hiring,
                "date_posted": structured.get("datePosted"),
                "valid_through": structured.get("validThrough"),
                "employment_type": structured.get("employmentType"),
                "industry": structured.get("industry"),
                "occupational_category": structured.get("occupationalCategory"),
                "job_location": structured.get("jobLocation"),
                "salary_currency": structured.get("salaryCurrency"),
                "direct_apply": structured.get("directApply"),
                "observation_provenance": "DIRECT",
                "discovery_scope": "it-category-listing-filtered",
                "parse_mode": "JSON_LD",
            },
            revision_projection={
                "jobposting_json_ld": structured,
                "stable_sections": _stable_sections(soup),
            },
        )


class ITLeadersSource:
    code = "itleaders"

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        response = client.get(ITLEADERS_LISTING_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        refs = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href") or ""
            if "/oferta-pracy/" not in href:
                continue
            url = canonical_url(urljoin(str(response.url), href))
            match = re.search(r"-(\d+)(?:/)?$", url)
            if not match:
                continue
            sid = match.group(1)
            if sid in seen:
                continue
            seen.add(sid)
            refs.append(PostingRef(self.code, url, sid))
            if len(refs) >= limit:
                break
        return refs

    def fetch_detail(self, client: httpx.Client, ref: PostingRef):
        response = client.get(ref.url)
        response.raise_for_status()
        return response.text, str(response.url), response.status_code, response.headers.get("content-type", "")

    def parse_detail(self, raw: str, ref: PostingRef) -> ParsedPosting:
        soup = BeautifulSoup(raw, "html.parser")
        desc = soup.find("meta", attrs={"name": "description"})
        og_title = soup.find("meta", attrs={"property": "og:title"})
        description = norm_text(desc.get("content") if desc else None)
        role = norm_text(description.split(",", 1)[0] if description else None)
        og = norm_text(og_title.get("content") if og_title else None)
        if not role:
            raise ValueError("PARSER_DRIFT: IT-Leaders role missing")
        company = None
        suffix = f" - {role}"
        if og.endswith(suffix):
            company = norm_text(og[:-len(suffix)])
        return ParsedPosting(
            source=self.code,
            source_posting_id=ref.source_posting_id,
            url=canonical_url(ref.url),
            title=role,
            company_mention=company or None,
            body_text=soup.get_text("\n", strip=True),
            source_specific={
                "og_title": og or None,
                "meta_description": description or None,
                "observation_provenance": "DIRECT",
            },
            revision_projection={
                "title": role,
                "company": company,
                "meta_description": description,
                "stable_sections": _stable_sections(soup),
            },
        )


class MichaelPageSource:
    code = "michaelpage"

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        refs = []
        seen = set()
        page = 0
        while len(refs) < limit:
            response = client.get(MICHAELPAGE_LISTING_URL, params={"page": page})
            if response.status_code == 404:
                break
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            before = len(refs)
            for a in soup.find_all("a", href=True):
                href = a.get("href") or ""
                match = re.search(r"/job-detail/[^?]+/ref/(jn-[0-9-]+)", href, re.I)
                if not match:
                    continue
                sid = match.group(1).lower()
                if sid in seen:
                    continue
                seen.add(sid)
                refs.append(PostingRef(self.code, canonical_url(urljoin(str(response.url), href.split("?", 1)[0])), sid))
                if len(refs) >= limit:
                    return refs
            if len(refs) == before:
                break
            page += 1
        return refs

    def fetch_detail(self, client: httpx.Client, ref: PostingRef):
        response = client.get(ref.url)
        response.raise_for_status()
        return response.text, str(response.url), response.status_code, response.headers.get("content-type", "")

    def parse_detail(self, raw: str, ref: PostingRef) -> ParsedPosting:
        soup = BeautifulSoup(raw, "html.parser")
        structured = _jobposting_json_ld(soup)
        if not structured:
            title_tag = norm_text(soup.title.get_text(" ", strip=True) if soup.title else None)
            if "Page not found" in title_tag or "404" in title_tag:
                raise SourceGoneError("Michael Page offer no longer exposed")
            raise ValueError("PARSER_DRIFT: Michael Page JobPosting JSON-LD missing")
        title = norm_text(structured.get("title"))
        hiring = structured.get("hiringOrganization") or {}
        advertiser = hiring.get("name") if isinstance(hiring, dict) else None
        if not title:
            raise ValueError("PARSER_DRIFT: Michael Page title missing")
        canonical = soup.find("link", attrs={"rel": "canonical"})
        canonical_href = canonical.get("href") if canonical else None
        return ParsedPosting(
            source=self.code,
            source_posting_id=ref.source_posting_id,
            url=canonical_url(canonical_href or ref.url),
            title=title,
            company_mention=norm_text(advertiser) or None,
            body_text=soup.get_text("\n", strip=True),
            source_specific={
                "advertiser": norm_text(advertiser) or None,
                "date_posted": structured.get("datePosted"),
                "employment_type": structured.get("employmentType"),
                "industry": structured.get("industry"),
                "job_location": structured.get("jobLocation"),
                "observation_provenance": "DIRECT_RECRUITER",
            },
            revision_projection={
                "jobposting_json_ld": structured,
                "stable_sections": _stable_sections(soup),
            },
        )


class EuroTechJobsSource:
    code = "eurotechjobs"

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        response = client.get(EUROTECHJOBS_SITEMAP)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        refs = []
        seen = set()
        for node in root.iter():
            if not node.tag.endswith("loc") or not node.text:
                continue
            url = canonical_url(node.text.strip())
            match = re.search(r"/job_display/(\d+)(?:/|$)", url)
            if not match:
                continue
            sid = match.group(1)
            if sid in seen:
                continue
            seen.add(sid)
            refs.append(PostingRef(self.code, url, sid))
            if len(refs) >= limit:
                break
        return refs

    def fetch_detail(self, client: httpx.Client, ref: PostingRef):
        response = client.get(ref.url)
        response.raise_for_status()
        return response.text, str(response.url), response.status_code, response.headers.get("content-type", "")

    def parse_detail(self, raw: str, ref: PostingRef) -> ParsedPosting:
        soup = BeautifulSoup(raw, "html.parser")
        h1 = soup.find("h1")
        title = norm_text(h1.get_text(" ", strip=True) if h1 else None)
        if not title:
            page_title = norm_text(soup.title.get_text(" ", strip=True) if soup.title else None)
            if "Page not found" in page_title or "404" in page_title:
                raise SourceGoneError("EuroTechJobs offer no longer exposed")
            raise ValueError("PARSER_DRIFT: EuroTechJobs title missing")
        container = soup.select_one(".jobDisplay")
        h2s = container.find_all("h2") if container else []
        company = norm_text(h2s[0].get_text(" ", strip=True)) if len(h2s) >= 1 else None
        location = norm_text(h2s[1].get_text(" ", strip=True)) if len(h2s) >= 2 else None
        og_title = soup.find("meta", attrs={"property": "og:title"})
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        canonical = soup.find("link", attrs={"rel": "canonical"})
        canonical_href = canonical.get("href") if canonical else None
        return ParsedPosting(
            source=self.code,
            source_posting_id=ref.source_posting_id,
            url=canonical_url(canonical_href or ref.url),
            title=title,
            company_mention=company or None,
            body_text=(container or soup).get_text("\n", strip=True),
            source_specific={
                "company": company or None,
                "location": location or None,
                "og_title": og_title.get("content") if og_title else None,
                "og_description": og_desc.get("content") if og_desc else None,
                "observation_provenance": "DIRECT",
                "discovery_scope": "public-sitemap",
            },
            revision_projection={
                "title": title,
                "company": company or None,
                "location": location or None,
                "og_description": og_desc.get("content") if og_desc else None,
            },
        )


class HNWhoIsHiringSource:
    code = "hnwhoishiring"

    def discover(self, client: httpx.Client, limit: int) -> list[PostingRef]:
        thread = client.get(HN_API_ITEM.format(item_id=HN_WHOISHIRING_THREAD_ID))
        thread.raise_for_status()
        data = thread.json()
        refs = []
        for cid in data.get("kids") or []:
            refs.append(PostingRef(
                self.code,
                f"https://news.ycombinator.com/item?id={cid}",
                str(cid),
            ))
            if len(refs) >= limit:
                break
        return refs

    def fetch_detail(self, client: httpx.Client, ref: PostingRef):
        response = client.get(HN_API_ITEM.format(item_id=ref.source_posting_id))
        response.raise_for_status()
        return response.text, str(response.url), response.status_code, response.headers.get("content-type", "")

    def parse_detail(self, raw: str, ref: PostingRef) -> ParsedPosting:
        item = json.loads(raw)
        if item.get("deleted") or item.get("dead") or not item.get("text"):
            raise SourceGoneError("HN top-level hiring comment deleted/dead/empty")
        soup = BeautifulSoup(item.get("text") or "", "html.parser")
        raw_plain = soup.get_text("\n", strip=True)
        plain = norm_text(raw_plain)
        if not plain:
            raise SourceGoneError("HN top-level hiring comment has no text")
        first_line = norm_text(raw_plain.split("\n", 1)[0])
        first_segment = first_line.split("|", 1)[0].strip()
        company = first_segment if 1 <= len(first_segment) <= 120 else None
        title = first_line[:180]
        comment_id = str(item.get("id") or ref.source_posting_id)
        return ParsedPosting(
            source=self.code,
            source_posting_id=comment_id,
            url=f"https://news.ycombinator.com/item?id={comment_id}",
            title=title,
            company_mention=company,
            body_text=plain,
            source_specific={
                "thread_id": HN_WHOISHIRING_THREAD_ID,
                "comment_id": item.get("id"),
                "author": item.get("by"),
                "unix_time": item.get("time"),
                "parent": item.get("parent"),
                "observation_provenance": "COMMUNITY_DIRECT",
                "discovery_scope": "current-thread-top-level-comments",
            },
            revision_projection={
                "thread_id": HN_WHOISHIRING_THREAD_ID,
                "comment_id": item.get("id"),
                "author": item.get("by"),
                "text": plain,
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
    "solidjobs": SolidJobsSource(),
    "teamquest": TeamQuestSource(),
    "aplikuj": AplikujSource(),
    "itleaders": ITLeadersSource(),
    "michaelpage": MichaelPageSource(),
    "eurotechjobs": EuroTechJobsSource(),
    "hnwhoishiring": HNWhoIsHiringSource(),
    "pracuj": PracujSecondarySource(),
}
