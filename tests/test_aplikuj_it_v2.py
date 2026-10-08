"""Adversarial regression: acquisition completeness is independent of title judgment."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re

import pytest

from ingestion.acquire_file_backed import acquire
from ingestion.aplikuj_policy import assess, APLIKUJ_SCOPE, IT_CONFIRMED, NON_IT_CONFIRMED, REVIEW_REQUIRED
from ingestion.clean_aplikuj_cache import read_gz
from ingestion.expansion_sources import AplikujSource
from ingestion.model import ParsedPosting
from ingestion.run_file_backed_plan import _manifest_ok, run

ROOT = Path(__file__).resolve().parents[1]


def parsed(title, industry=None, description=None):
    return ParsedPosting("aplikuj", "7", "https://www.aplikuj.pl/oferta/7/example", title,
        "Example", "body page", {"industry": industry},
        {"jobposting_json_ld": {"description": description}} if description is not None else {})


def test_assessment_requires_more_than_title_and_keeps_ambiguity():
    assert assess(parsed("Frontend Developer", "Informatyk", "Tworzenie aplikacji webowych w React"))["status"] == IT_CONFIRMED
    assert assess(parsed("Kierowca C+E", "Kierowca", "Prowadzenie pojazdu i przewóz towarów"))["status"] == NON_IT_CONFIRMED
    assert assess(parsed("Administrator Infrastruktury Teleinformatycznej"))["status"] == REVIEW_REQUIRED
    assert assess(parsed("Programista CNC", "Informatyk", "Programowanie maszyn CNC"))["status"] == REVIEW_REQUIRED
    assert assess(parsed("Specjalista ds. ITAR", "Inny"))["status"] == REVIEW_REQUIRED
    assert assess(parsed("Senior Python Developer", "Informatyk"))["status"] == REVIEW_REQUIRED


def test_all_509_historic_listing_ids_are_discoverable_without_title_gate():
    fixture = ROOT / "reports/discovery-2026-10-08/aplikuj-listing-ids.jsonl"
    entries = [json.loads(line) for line in fixture.read_text(encoding="utf-8").splitlines() if line]
    assert len(entries) == 509 and len({r["id"] for r in entries}) == 509
    class Response:
        def __init__(self, text): self.text = text
        def raise_for_status(self): pass
    class Client:
        def __init__(self): self.calls = []
        def get(self, url):
            self.calls.append(url)
            m = re.search(r"/strona-(\d+)$", url)
            p = int(m.group(1)) if m else 1
            chunk = entries[(p-1)*50:p*50]
            cards = ''.join(f'<li class="offer-card"><a class="offer-title" href="{escape(r["url"])}">{escape(r["title"])}</a></li>' for r in chunk)
            next_link = f'<a href="/praca/it-informatyka/strona-{p+1}">Next</a>' if p*50 < len(entries) else ''
            return Response(cards + next_link)
    client = Client()
    discovered = AplikujSource().discover(client, 1000)
    assert len(discovered) == len({r.source_posting_id for r in discovered}) == 509
    assert {r.source_posting_id for r in discovered} == {r["id"] for r in entries}
    assert len(client.calls) == 11
    assert any(not r["conservative_it"] and r["id"] in {x.source_posting_id for x in discovered} for r in entries)


def test_old_or_pruned_manifests_are_never_accepted_as_v2(tmp_path):
    path = tmp_path / "manifest.json"
    basis = {"planned": 3, "postings": 3, "source_gone": 0, "errors": [], "raw_archive": {"rows": 3},
             "scope": "it-category-v2", "excluded_non_it": 0,
             "assessment_counts": {"IT_CONFIRMED": 1, "NON_IT_CONFIRMED": 1, "REVIEW_REQUIRED": 1},
             "assessment_archive": {"rows": 3}}
    path.write_text(json.dumps(basis))
    assert _manifest_ok(path, expected_scope=APLIKUJ_SCOPE)
    for change in ({"scope":"technical-it-v1"}, {"excluded_non_it":1},
                   {"assessment_counts":{"IT_CONFIRMED":1,"REVIEW_REQUIRED":1}},
                   {"assessment_counts":{"IT_CONFIRMED":3,"NON_IT_CONFIRMED":0,"REVIEW_REQUIRED":1}}):
        path.write_text(json.dumps(basis|change))
        assert not _manifest_ok(path, expected_scope=APLIKUJ_SCOPE)


def test_old_plan_is_rejected_before_writing_or_fetching(tmp_path):
    plan = tmp_path / "old.json"
    plan.write_text(json.dumps({"aplikuj_scope":"technical-it-v1","chunks":[]}))
    with pytest.raises(RuntimeError, match="requires new lossless"):
        run(str(plan), ["aplikuj"], str(tmp_path / "out"), str(tmp_path / "raw"), str(tmp_path / "status.json"), 1)
    assert not (tmp_path / "status.json").exists()


def test_lossless_acquisition_three_different_statuses(tmp_path, monkeypatch):
    from ingestion import acquire_file_backed as module
    postings = {
        "1": ("Frontend Developer", "Informatyk", "Tworzenie aplikacji webowych w React"),
        "2": ("Administrator Infrastruktury Teleinformatycznej", "Informatyk", "Współpraca z zespołem"),
        "3": ("Kierowca C+E", "Kierowca", "Prowadzenie pojazdu i przewóz towarów"),
    }
    class Response:
        status_code = 200
        headers = {"content-type":"text/html"}
        def __init__(self, url):
            self.url = url
            code = re.search(r"/oferta/(\d+)",url).group(1)
            title, industry, description = postings[code]
            data = {"@type":"JobPosting","title":title,"industry":industry,"description":description,
                    "hiringOrganization":{"@type":"Organization","name":"Example"}}
            self.text = '<html><head><script type="application/ld+json">'+json.dumps(data)+'</script></head><body><h1>'+title+'</h1></body></html>'
        def raise_for_status(self): pass
    class Client:
        def __init__(self,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def get(self,url): return Response(url)
    monkeypatch.setattr(module.httpx, "Client", Client)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    plan = tmp_path / "chunks.json"
    plan.write_text(json.dumps({"aplikuj_scope":APLIKUJ_SCOPE,"chunks":[{"source":"aplikuj","chunk_index":0,
        "rows":[{"url":f"https://www.aplikuj.pl/oferta/{i}/candidate","source_posting_id":i} for i in postings]}]}))
    out = tmp_path / "crawl" / "aplikuj" / "0"
    raw = tmp_path / "raw" / "aplikuj" / "0"
    manifest = acquire(str(plan),"aplikuj",0,str(out),str(raw),delay=0,max_attempts=1)
    rows = read_gz(out / "corpus.jsonl.gz")
    observations = read_gz(raw / "raw-observations.jsonl.gz")
    assessments = read_gz(out / "assessments.jsonl.gz")
    assert manifest["postings"] == 3 and manifest["excluded_non_it"] == 0
    assert manifest["assessment_counts"] == {"IT_CONFIRMED":1,"NON_IT_CONFIRMED":1,"REVIEW_REQUIRED":1}
    assert _manifest_ok(out / "manifest.json", expected_scope=APLIKUJ_SCOPE)
    assert {r["source_posting_id"] for r in rows} == {"1","2","3"}
    assert {r["source_posting_id"] for r in observations} == {"1","2","3"}
    assert all("it_assessment" not in row for row in rows)
    assert {r["source_posting_id"] for r in assessments} == {"1","2","3"}
    assert {r["assessment"]["status"] for r in assessments} == {IT_CONFIRMED,NON_IT_CONFIRMED,REVIEW_REQUIRED}
    from ingestion.verify_aplikuj_v2 import verify
    assert verify(tmp_path / "crawl")["status"] == "PASS"
    from ingestion import aplikuj_policy
    def broken_classifier(posting):
        raise ValueError("unexpected policy error")
    monkeypatch.setattr(aplikuj_policy, "assess", broken_classifier)
    failed_out = tmp_path / "retry" / "aplikuj" / "0"
    failed_raw = tmp_path / "retry-raw" / "aplikuj" / "0"
    failed = acquire(str(plan),"aplikuj",0,str(failed_out),str(failed_raw),delay=0,max_attempts=1)
    assert failed["postings"] == 3
    assert failed["assessment_counts"]["REVIEW_REQUIRED"] == 3
    assert all("ASSESSMENT_ERROR" in r["assessment"]["evidence_codes"] for r in read_gz(failed_out / "assessments.jsonl.gz"))
    assert verify(tmp_path / "retry")["status"] == "PASS"


def test_v2_verifier_rejects_corrupted_assessment_archive(tmp_path, monkeypatch):
    from ingestion.verify_aplikuj_v2 import verify
    root = tmp_path / "crawl" / "aplikuj" / "0"
    raw = tmp_path / "raw" / "aplikuj" / "0"
    root.mkdir(parents=True)
    raw.mkdir(parents=True)
    from ingestion.clean_aplikuj_cache import compressed_rows
    posting = {"source":"aplikuj","source_posting_id":"9","title":"Developer", "raw_payload_sha256":"abc"}
    observation = {"source":"aplikuj","source_posting_id":"9", "payload_sha256":"abc"}
    decision = {"source":"aplikuj","source_posting_id":"9", "raw_payload_sha256":"abc",
                "assessment":{"status":REVIEW_REQUIRED,"policy_version":"aplikuj-evidence-v1","evidence_codes":["INSUFFICIENT_OR_CONFLICTING_EVIDENCE"]}}
    cb, cm = compressed_rows([posting]); rb, rm = compressed_rows([observation]); ab, am = compressed_rows([decision])
    (root / "corpus.jsonl.gz").write_bytes(cb)
    (raw / "raw-observations.jsonl.gz").write_bytes(rb)
    (root / "assessments.jsonl.gz").write_bytes(ab)
    m = {"scope":APLIKUJ_SCOPE,"planned":1,"postings":1,"excluded_non_it":0,"source_gone":0,"errors":[],
         "corpus":cm,"raw_archive":rm,"assessment_archive":am,"raw_archive_location":str(raw / "raw-observations.jsonl.gz"),
         "assessment_counts":{"IT_CONFIRMED":0,"NON_IT_CONFIRMED":0,"REVIEW_REQUIRED":1}}
    (root / "manifest.json").write_text(json.dumps(m))
    assert verify(tmp_path / "crawl")["status"] == "PASS"
    (root / "assessments.jsonl.gz").write_bytes(b"corrupted")
    assert verify(tmp_path / "crawl")["status"] == "FAIL"


def test_no_overwrite_of_old_title_pruned_chunk(tmp_path):
    plan = tmp_path / "new.json"
    plan.write_text(json.dumps({"aplikuj_scope":APLIKUJ_SCOPE,"chunks":[{"source":"aplikuj","chunk_index":0,"rows":[]}]}))
    output = tmp_path / "historic"
    output.mkdir()
    (output / "manifest.json").write_text(json.dumps({"scope":"technical-it-v1","postings":33}))
    with pytest.raises(RuntimeError, match="cannot overwrite legacy"):
        acquire(str(plan), "aplikuj", 0, str(output), str(tmp_path / "raw"), delay=0, max_attempts=1)
    assert json.loads((output / "manifest.json").read_text())["postings"] == 33


def test_inventory_does_not_reuse_title_pruned_v1_as_known(tmp_path, monkeypatch):
    import gzip
    from ingestion import build_scale04_inventory as inventory
    from ingestion.model import PostingRef
    class Client:
        def __init__(self,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
    class Source:
        def __init__(self,name): self.name=name
        def discover(self,client,limit):
            if self.name != "aplikuj": return []
            return [PostingRef("aplikuj",f"https://www.aplikuj.pl/oferta/{i}/example",str(i)) for i in (1,2)]
    from ingestion.clean_aplikuj_cache import compressed_rows
    old = tmp_path / ".local-crawl" / "scale-04" / "aplikuj" / "0"
    old.mkdir(parents=True)
    old_blob,_ = compressed_rows([{"source_posting_id":"1","title":"Python Developer"}])
    (old / "corpus.jsonl.gz").write_bytes(old_blob)
    (old / "manifest.json").write_text(json.dumps({"scope":"technical-it-v1","postings":1}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(inventory.httpx,"Client",Client)
    monkeypatch.setattr(inventory,"load_known_ids",lambda *args: {"1","2"})
    monkeypatch.setattr(inventory,"SOURCES", {n:Source(n) for n in inventory.SOURCES_SCOPE})
    result = inventory.build("ignored-base",str(tmp_path / "new"))
    assert result["sources"]["aplikuj"]["discoverable"] == 2
    assert result["sources"]["aplikuj"]["known"] == 0
    assert result["sources"]["aplikuj"]["unknown"] == 2
    assert result["aplikuj_scope"] == "it-category-v2"
