"""RI-01: reproducible evidence extraction from a frozen, mixed-market corpus.

This module deliberately does NOT produce human-verified gold labels. Extracted
assertions are candidates with exact anchors and conservative modality.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

VERSION = "ri01-extractor-v1"
TECH = {
    "python": r"\bpython\b", "java": r"\bjava\b", "javascript": r"\bjavascript\b",
    "typescript": r"\btypescript\b", "go": r"\bgolang\b|\bgo language\b",
    "rust": r"\brust\b", "c#": r"\bc#", "php": r"\bphp\b",
    "react": r"\breact\b", "angular": r"\bangular\b", "vue": r"\bvue(?:\.js)?\b",
    "node.js": r"\bnode(?:\.js)?\b", "spring boot": r"\bspring\s+boot\b",
    "django": r"\bdjango\b", "fastapi": r"\bfastapi\b",
    "postgresql": r"\bpostgres(?:ql)?\b", "mysql": r"\bmysql\b",
    "mongodb": r"\bmongodb\b", "redis": r"\bredis\b", "kafka": r"\bkafka\b",
    "docker": r"\bdocker\b", "kubernetes": r"\bkubernetes\b|\bk8s\b",
    "terraform": r"\bterraform\b", "ansible": r"\bansible\b",
    "aws": r"\baws\b|\bamazon web services\b", "azure": r"\bazure\b",
    "gcp": r"\bgcp\b|\bgoogle cloud\b", "linux": r"\blinux\b",
    "git": r"\bgit\b", "github actions": r"\bgithub actions\b",
    "gitlab ci": r"\bgitlab ci\b", "jenkins": r"\bjenkins\b",
    "prometheus": r"\bprometheus\b", "grafana": r"\bgrafana\b",
    "opentelemetry": r"\bopentelemetry\b|\botel\b",
    "rest api": r"\brest(?:ful)?\s+api\b", "api": r"\bapi\b",
    "microservices": r"\bmicroservices?\b|\bmikroserwis\w*\b",
    "distributed systems": r"\bdistributed systems?\b|\bsystem\w* rozproszon\w*\b",
    "ci/cd": r"\bci\s*/\s*cd\b", "testing": r"\btesting\b|\btest(?:y|ów|owanie)\b",
    "security": r"\bsecurity\b|\bbezpiecze\w*\b",
    "observability": r"\bobservability\b",
    "ai": r"\bartificial intelligence\b|\bsztuczn\w+ inteligencj\w+\b",
}
PATTERNS = {k: re.compile(v, re.I) for k, v in TECH.items()}
FAMILY = [
    ("ai_ml", r"\bai\b|\bml\b|machine learning|llm|data scientist|sztuczn"),
    ("security", r"security|cyber|bezpiecze|soc analyst"),
    ("platform_devops", r"devops|platform|sre|site reliability|cloud engineer|infrastrukt"),
    ("architecture", r"architect|architekt"),
    ("data", r"data engineer|data analyst|big data|analytics|bigquery"),
    ("qa", r"\bqa\b|tester|testing|quality assurance"),
    ("frontend_mobile", r"frontend|front.end|react|android|ios|mobile|mobiln"),
    ("backend_fullstack", r"backend|back.end|full.stack|developer|programist|software engineer"),
    ("product_management", r"product owner|product manager|project manager|scrum master"),
    ("nontechnical", r"sales|sprzedaż|recruit|rekruter|księgow|marketing|assistant|asystent|hr specialist"),
]
FAMILY = [(k, re.compile(v, re.I)) for k, v in FAMILY]
REQ_HEADERS = re.compile(r"^(requirements?|must.have|wymagania|oczekujemy|czego oczekujemy|nasze oczekiwania|you (?:should|need)|what you (?:need|bring)|qualification|kompetencje wymagane)", re.I)
NICE_HEADERS = re.compile(r"^(nice.to.have|preferred|mile widziane|dodatkow[ey] atut|bonus points|would be (?:a )?plus)", re.I)
TASK_HEADERS = re.compile(r"^(responsibilit|duties|tasks|what you.ll do|your role|obowi.zki|zadania|zakres obowi.zk.w|czym b.dziesz)", re.I)
OTHER_HEADERS = re.compile(r"^(benefit|oferujemy|we offer|about us|o nas|perks|our company|co oferujemy)", re.I)


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def get_sem(record: dict) -> dict:
    return (record.get("normalized_projection") or {}).get("semantic_content") or {}


def identity(record: dict) -> str:
    return f"{record['source']}:{record['source_posting_id']}"


def classify_title(title: str) -> str:
    # Negative controls: a marketing "platform" is not Platform Engineering.
    if re.search(r"\b(?:PPC|SEO|SEM|marketing|marketer|sales|sprzedaż|account manager)\b", title, re.I) and not re.search(
        r"\b(?:software engineer|developer|architect|architekt|programist)\b", title, re.I
    ):
        return "nontechnical"
    for family, pattern in FAMILY:
        if pattern.search(title):
            return family
    return "ambiguous_other"


def seniority(record: dict) -> str:
    sem = get_sem(record)
    explicit = (sem.get("basics") or {}).get("seniority") or []
    if isinstance(explicit, list) and explicit:
        return str(explicit[0]).lower()
    title = record.get("title", "")
    for label, pattern in [("junior", r"\bjunior\b|\bm.odszy\b|\bsta.ysta\b"),
                           ("staff_lead", r"\bstaff\b|\bprincipal\b|\blead\b|\bhead\b"),
                           ("senior", r"\bsenior\b|\bstarszy\b"), ("mid", r"\bmid\b|\bmiddle\b")]:
        if re.search(pattern, title, re.I):
            return label
    return "unspecified"


def candidate_text(record: dict) -> str:
    sem = get_sem(record)
    parts = []
    j = sem.get("jobposting_json_ld") or {}
    if isinstance(j, dict) and isinstance(j.get("description"), str):
        parts.append(j["description"])
    for path in ((sem.get("requirements") or {}).get("description"),
                 (sem.get("details") or {}).get("description"),
                 sem.get("meta_description")):
        if isinstance(path, str):
            parts.append(path)
    for value in (sem.get("stable_sections") or {}).values():
        if isinstance(value, list):
            parts.extend(x for x in value if isinstance(x, str))
        elif isinstance(value, str):
            parts.append(value)
    bt = (record.get("normalized_projection") or {}).get("body_text")
    if isinstance(bt, str):
        try:
            details = json.loads(bt)
            if isinstance(details, dict) and isinstance(details.get("textSections"), list):
                parts.extend(f"{section.get('type', '')}: {section.get('plainText', '')}"
                             for section in details["textSections"] if isinstance(section, dict))
            else:
                parts.append(bt)
        except (ValueError, TypeError):
            parts.append(bt)
    elif isinstance(bt, dict):
        parts.extend(x for x in bt.values() if isinstance(x, str))
    return BeautifulSoup(" ".join(parts), "html.parser").get_text(" ", strip=True)


def language_candidate(record: dict) -> str:
    """Heuristic sampling stratum only; NOT a verified language requirement."""
    sem = get_sem(record)
    explicit = sem.get("language")
    if isinstance(explicit, str) and explicit.lower() in ("pl", "en"):
        return explicit.lower()
    body = (record.get("normalized_projection") or {}).get("body_text")
    if isinstance(body, str) and record.get("source") == "theprotocol":
        try:
            explicit = json.loads(body).get("language")
            if isinstance(explicit, str) and explicit.lower() in ("pl", "en"):
                return explicit.lower()
        except (ValueError, TypeError):
            pass
    # Sampling needs a cheap stratum guess over all source records. Do not
    # parse the complete HTML 6,320 times before picking the 200 review rows.
    source_text = (
        (sem.get("jobposting_json_ld") or {}).get("description")
        or (sem.get("requirements") or {}).get("description")
        or (sem.get("details") or {}).get("description")
        or sem.get("meta_description")
        or record.get("title")
        or ""
    )
    text = str(source_text)[:2800].lower()
    pl = len(re.findall(r"\b(?:wymagania|doświadczenie|poszukujemy|znajomość|obowiązki|oferujemy|pracę|umiejętność|będziesz)\b", text))
    en = len(re.findall(r"\b(?:requirements|experience|we are looking|responsibilities|we offer|you will|skills|our team)\b", text))
    if pl >= 2 and en >= 2:
        return "mixed"
    if pl >= 2:
        return "pl"
    if en >= 2:
        return "en"
    return "pl" if len(re.findall("[ąćęłńóśźż]", text)) >= 3 else "unknown"


def reviewer_source_text(record: dict) -> str:
    """Complete available archived evidence projection, with typed source rows.

    This is still a projection, NOT a claim that the original page was complete.
    """
    base = candidate_text(record)
    sem = get_sem(record)
    req = sem.get("requirements") or {}
    specs = sem.get("specs") or {}
    sections = []
    for field, heading in (("musts", "SOURCE STRUCTURED MUSTS"), ("nices", "SOURCE STRUCTURED NICE-TO-HAVES")):
        vals = [x.get("value") for x in req.get(field) or [] if isinstance(x, dict) and x.get("value")]
        if vals:
            sections.append(f"[{heading}]\n" + "\n".join("- " + str(v) for v in vals))
    tasks = [v for v in specs.get("dailyTasks") or [] if isinstance(v, str)]
    if tasks:
        sections.append("[SOURCE DAILY TASKS]\n" + "\n".join("- " + v for v in tasks))
    return base + ("\n\n" + "\n\n".join(sections) if sections else "")


def sample_corpus(records: list[dict], quota: dict[str, int]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["source"]].append(record)
    result = []
    for source, target in quota.items():
        pool = grouped.get(source, [])
        buckets: dict[tuple, list] = defaultdict(list)
        for r in pool:
            b = (classify_title(r.get("title", "")), seniority(r), language_candidate(r))
            buckets[b].append(r)
        for rows in buckets.values():
            rows.sort(key=lambda r: stable_hash(identity(r)))
        selected = []
        while len(selected) < min(target, len(pool)):
            eligible = [(len(rows), stable_hash(str(k)), k) for k, rows in buckets.items() if rows]
            if not eligible:
                break
            # Rotate strata to avoid taking every result from the majority family.
            _, _, bucket = min(eligible, key=lambda x: (x[0] == 0, -x[0], x[1]))
            # The round-robin proceeds over stable bucket order, rather than exhaustion.
            if len(selected) == 0:
                order = sorted(buckets, key=lambda b: stable_hash(str(b)))
            else:
                order = sorted(buckets, key=lambda b: stable_hash(str(b)))
            changed = False
            for b in order:
                if buckets[b] and len(selected) < target:
                    selected.append(buckets[b].pop(0))
                    changed = True
            if not changed:
                break
        result.extend(selected[:target])
    return sorted(result, key=lambda x: (x["source"], stable_hash(identity(x))))


def source_segments(record: dict) -> list[tuple[str, str, str, str]]:
    """Return (json_path, text, modality, category) segments, without inferred musts."""
    sem = get_sem(record)
    segments = []
    req = sem.get("requirements") or {}
    for attr, modality in (("musts", "MUST"), ("nices", "NICE")):
        for i, item in enumerate(req.get(attr) or []):
            if isinstance(item, dict) and isinstance(item.get("value"), str):
                text = item["value"].strip()
                if text:
                    segments.append((f"$.normalized_projection.semantic_content.requirements.{attr}[{i}].value", text, modality, "REQUIREMENT"))
    specs = sem.get("specs") or {}
    for i, text in enumerate(specs.get("dailyTasks") or []):
        if isinstance(text, str) and text.strip():
            segments.append((f"$.normalized_projection.semantic_content.specs.dailyTasks[{i}]", text.strip(), "TASK", "RESPONSIBILITY"))
    reqdesc = req.get("description")
    if isinstance(reqdesc, str) and reqdesc.strip():
        segments.extend(html_segments(reqdesc, "$.normalized_projection.semantic_content.requirements.description"))
    j = sem.get("jobposting_json_ld") or {}
    if isinstance(j, dict) and isinstance(j.get("description"), str):
        desc = j["description"]
        desc_path = "$.normalized_projection.semantic_content.jobposting_json_ld.description"
        segments.extend(html_segments(desc, desc_path))
        if not any(item[0] == desc_path for item in segments):
            # Plain-text portals often concatenate paragraphs; keep UNKNOWN when headings are lost.
            segments.extend(plain_segments(desc, desc_path))
    body = (record.get("normalized_projection") or {}).get("body_text")
    if record["source"] == "theprotocol" and isinstance(body, str):
        try:
            details = json.loads(body)
        except (ValueError, TypeError):
            details = {}
        for i, section in enumerate(details.get("textSections", [])):
            typ = section.get("type", "")
            mode = {"technologies-expected": "MUST", "technologies-optional": "NICE",
                    "requirements-expected": "MUST", "requirements-optional": "NICE",
                    "responsibilities": "TASK"}.get(typ, "UNKNOWN")
            if mode == "UNKNOWN":
                continue
            category = "RESPONSIBILITY" if mode == "TASK" else "REQUIREMENT"
            for jdx, part in enumerate(section.get("elements") or []):
                if isinstance(part, str) and part.strip():
                    segments.append((f"$.normalized_projection.body_text.textSections[{i}].elements[{jdx}]", part.strip(), mode, category))
    # No Fluff Jobs details are mostly marketing prose; do not classify as requirements.
    if not segments:
        sec = sem.get("stable_sections") or {}
        for key, value in sec.items():
            if isinstance(value, list):
                for i, v in enumerate(value):
                    if isinstance(v, str) and v.strip():
                        segments.append((f"$.normalized_projection.semantic_content.stable_sections.{json.dumps(key)}[{i}]", v.strip(), "UNKNOWN", "CONTEXT"))
    return segments


def plain_segments(markup: str, path: str) -> list[tuple[str, str, str, str]]:
    """Fallback for flattened description: evidence fragments with UNKNOWN modality."""
    clean = BeautifulSoup(markup, "html.parser").get_text(" ", strip=True)
    clean = re.sub(r"\s+", " ", clean).strip()
    chunks = re.split(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])", clean)
    result = []
    for chunk in chunks:
        chunk = chunk.strip()
        # Very long marketing paragraphs are split into searchable but unclassified fragments.
        while len(chunk) > 700:
            split = chunk.rfind(" ", 300, 680)
            if split < 0:
                split = 680
            part, chunk = chunk[:split].strip(), chunk[split:].strip()
            if len(part) >= 12:
                result.append((path, part, "UNKNOWN", "UNCLASSIFIED"))
        if len(chunk) >= 12:
            result.append((path, chunk, "UNKNOWN", "UNCLASSIFIED"))
    return result[:150]


def html_segments(markup: str, path: str) -> list[tuple[str, str, str, str]]:
    soup = BeautifulSoup(html.unescape(markup), "html.parser")
    out = []
    section = "UNKNOWN"
    # Only an explicit, recognized section title establishes modality.
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "b", "li", "p"]):
        if tag.find_parent("li") and tag.name != "li":
            continue
        if tag.find_parent("p") and tag.name in ("strong", "b"):
            text = tag.get_text(" ", strip=True)
            if len(text) <= 85 and any(p.search(text) for p in (REQ_HEADERS, NICE_HEADERS, TASK_HEADERS, OTHER_HEADERS)):
                section = header_mode(text)
            continue
        text = tag.get_text(" ", strip=True)
        if not text:
            continue
        if tag.name.startswith("h") or (tag.name in ("strong", "b") and len(text) <= 85):
            section = header_mode(text)
            continue
        if tag.name == "p" and tag.find("li"):
            continue
        if tag.name not in ("p", "li"):
            continue
        # Avoid complete marketing descriptions presented as one large paragraph.
        if len(text) > 700 or len(text) < 8:
            continue
        category = "RESPONSIBILITY" if section == "TASK" else "REQUIREMENT" if section in ("MUST", "NICE") else "UNCLASSIFIED"
        out.append((path, text, section, category))
    return out


def header_mode(text: str) -> str:
    text = text.strip(" :\u00a0\n")
    if NICE_HEADERS.search(text):
        return "NICE"
    if REQ_HEADERS.search(text):
        return "MUST"
    if TASK_HEADERS.search(text):
        return "TASK"
    return "UNKNOWN"


def concepts(quote: str) -> list[str]:
    # Technological mentions are annotations on source assertions, not inferred MUSTs.
    return sorted(name for name, pattern in PATTERNS.items() if pattern.search(quote))


def extract(record: dict) -> list[dict]:
    rows = []
    seen = set()
    language = language_candidate(record)
    projection_cache: dict[str, str | None] = {}
    for path, quote, modality, category in source_segments(record):
        if len(quote) > 1000:
            continue
        # Path references one original field or array element. Quote is an exact
        # span of the unmodified extracted text, not a paraphrase.
        itemkey = (path, quote, modality)
        if itemkey in seen:
            continue
        seen.add(itemkey)
        # Negated demands are not positive MUST assertions.
        negated = bool(re.search(r"\b(?:not required|no(?:\s+\w+){0,8}\s+experience(?:\s+is)?\s+required|no experience (?:is )?required|not necessary|nie wymagamy|nie jest wymagane|bez wymogu)\b", quote, re.I))
        if negated and modality == "MUST":
            modality = "UNKNOWN"
        if path not in projection_cache:
            projection_cache[path] = source_projection_text(record, path)
        projection = projection_cache[path]
        normalized_quote = re.sub(r"\s+", " ", quote).strip()
        start = projection.find(normalized_quote) if projection is not None else -1
        assertion = {
            "assertion_id": stable_hash(f"{identity(record)}:{record.get('revision_id')}:{path}:{quote}:{modality}"),
            "posting_id": identity(record),
            "source": record["source"],
            "source_posting_id": record["source_posting_id"],
            "revision_id": record.get("revision_id"),
            "url": record.get("url"),
            "title": record.get("title"),
            "company": record.get("organization_mention"),
            "family_candidate": classify_title(record.get("title", "")),
            "seniority_candidate": seniority(record),
            "language_candidate": language,
            "source_path": path,
            "quote": quote,
            "span": {
                "start": start if start >= 0 else None,
                "end": start + len(normalized_quote) if start >= 0 else None,
                "basis": "normalized_source_field_dom_text",
                "found": start >= 0,
            },
            "modality_candidate": modality,
            "category_candidate": category,
            "concept_candidates": concepts(quote),
            "review_status": "UNREVIEWED",
            "negation_detected": negated,
            "extraction_version": VERSION,
        }
        rows.append(assertion)
    return rows


def summarize(sample: list[dict], assertions: list[dict]) -> dict:
    by_source = Counter(r["source"] for r in sample)
    labelled = Counter(a["modality_candidate"] for a in assertions)
    with_text = sum(len(candidate_text(r)) >= 500 for r in sample)
    sampleids = {identity(r) for r in sample}
    covered = {a["posting_id"] for a in assertions}
    return {
        "status": "CANDIDATE_ONLY_NO_GOLD",
        "extractor": VERSION,
        "sample_size": len(sample),
        "sample_sources": dict(sorted(by_source.items())),
        "sample_with_500_text_chars": with_text,
        "postings_with_assertions": len(covered),
        "postings_with_zero_assertions": len(sampleids - covered),
        "candidate_assertions": len(assertions),
        "by_modality": dict(sorted(labelled.items())),
        "quality_metrics": {"precision": None, "recall": None, "must_false_positive_rate": None, "concept_mapping_accuracy": None, "span_grounding_reviewed": None},
        "caution": "Candidates are not verified annotations. Cross-source deduplication and IT-scope validation are pending.",
    }


def anchored_in_source(record: dict, assertion: dict) -> bool:
    """Mechanical check of the cited field, not semantic correctness.

    HTML snippets are resolved against their DOM-text projection because the
    quote may bridge literal tags. Structured source paths are resolved exactly.
    """
    path = assertion["source_path"]
    quote = assertion["quote"]
    sem = get_sem(record)
    original = None
    if path.endswith(".description") and "jobposting_json_ld" in path:
        original = (sem.get("jobposting_json_ld") or {}).get("description")
    elif path.endswith(".description") and "requirements.description" in path:
        original = (sem.get("requirements") or {}).get("description")
    else:
        m = re.search(r"requirements\.(musts|nices)\[(\d+)\]\.value$", path)
        if m:
            arr = (sem.get("requirements") or {}).get(m.group(1)) or []
            if int(m.group(2)) < len(arr):
                original = arr[int(m.group(2))].get("value")
        m = re.search(r"specs\.dailyTasks\[(\d+)\]$", path)
        if m:
            arr = (sem.get("specs") or {}).get("dailyTasks") or []
            if int(m.group(1)) < len(arr):
                original = arr[int(m.group(1))]
        m = re.search(r"body_text\.textSections\[(\d+)\]\.elements\[(\d+)\]$", path)
        if m:
            try:
                body = json.loads((record.get("normalized_projection") or {}).get("body_text") or "{}")
                original = body["textSections"][int(m.group(1))]["elements"][int(m.group(2))]
            except (ValueError, KeyError, TypeError, IndexError):
                return False
        if "stable_sections" in path:
            tail = path.split("stable_sections.", 1)[-1]
            m = re.match(r'("(?:\\.|[^"])*")\[(\d+)\]$', tail)
            if m:
                key = json.loads(m.group(1))
                arr = (sem.get("stable_sections") or {}).get(key) or []
                if isinstance(arr, list) and int(m.group(2)) < len(arr):
                    original = arr[int(m.group(2))]
    if not isinstance(original, str):
        return False
    if original.strip() == quote:
        return True
    # Structural extraction inserts whitespace at DOM boundaries.
    original_clean = BeautifulSoup(html.unescape(original), "html.parser").get_text(" ", strip=True)
    collapse = lambda x: re.sub(r"\s+", " ", x).strip()
    return collapse(quote) in collapse(original_clean)


def source_projection_text(record: dict, path: str) -> str | None:
    """Resolve the field from archived semantic data into normalized DOM text."""
    sem = get_sem(record)
    value = None
    if path.endswith("jobposting_json_ld.description"):
        value = (sem.get("jobposting_json_ld") or {}).get("description")
    elif path.endswith("requirements.description"):
        value = (sem.get("requirements") or {}).get("description")
    else:
        m = re.search(r"requirements\.(musts|nices)\[(\d+)\]\.value$", path)
        if m:
            arr = (sem.get("requirements") or {}).get(m.group(1)) or []
            if int(m.group(2)) < len(arr):
                value = arr[int(m.group(2))].get("value")
        m = re.search(r"specs\.dailyTasks\[(\d+)\]$", path)
        if m:
            arr = (sem.get("specs") or {}).get("dailyTasks") or []
            if int(m.group(1)) < len(arr):
                value = arr[int(m.group(1))]
        m = re.search(r"body_text\.textSections\[(\d+)\]\.elements\[(\d+)\]$", path)
        if m:
            try:
                body = json.loads((record.get("normalized_projection") or {}).get("body_text") or "{}")
                value = body["textSections"][int(m.group(1))]["elements"][int(m.group(2))]
            except (ValueError, KeyError, TypeError, IndexError):
                return None
        if "stable_sections" in path:
            tail = path.split("stable_sections.", 1)[-1]
            m = re.match(r'("(?:\\.|[^"])*")\[(\d+)\]$', tail)
            if m:
                key = json.loads(m.group(1))
                arr = (sem.get("stable_sections") or {}).get(key) or []
                if isinstance(arr, list) and int(m.group(2)) < len(arr):
                    value = arr[int(m.group(2))]
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", BeautifulSoup(html.unescape(value), "html.parser").get_text(" ", strip=True)).strip()
