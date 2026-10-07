from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.aplikuj_it_scope import is_technical_it
from ingestion.clean_aplikuj_cache import clean, compressed_rows, read_gz
from ingestion.expansion_sources import AplikujSource
from ingestion.run_file_backed_plan import _manifest_ok, run


@pytest.mark.parametrize("title", [
    "Junior Front-end Developer",
    "Specjalista ds. Wsparcia IT - Informatyk",
    "Senior IT Analyst Business Systems",
    "Administrator Infrastruktury Teleinformatycznej",
    "Programista Unity C#",
    "Wdrożeniowiec / Konsultant oprogramowania enova365",
    "Frontend Developer (React/TypeScript)",
    "Data Engineer",
])
def test_accepts_technical_it(title):
    assert is_technical_it(title)


@pytest.mark.parametrize("title", [
    "Nauczyciel Edukacji Wczesnoszkolnej",
    "Specjalista ds. ITAR / Export Compliance",
    "Programista Robotów Przemysłowych",
    "Programista CNC tokarki i frezarki",
    "Programista Maszyn do Wykrawania i Cięcia",
    "Specjalista ds. Sprzedaży Systemów IT",
    "Przedstawiciel Handlowy D2D w branży IT",
    "Tester Produktów Spożywczych",
    "Nauczyciel informatyki",
    "Automatyk / Programista",
])
def test_rejects_non_it_titles(title):
    assert not is_technical_it(title)


def test_listing_discovery_uses_it_category_and_rejects_promoted_roles():
    class FakeResponse:
        def __init__(self, html):
            self.text = html
        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self):
            self.urls = []
        def get(self, url):
            self.urls.append(url)
            if url.endswith("strona-2"):
                return FakeResponse('<li class="offer-card"><a class="offer-title" href="https://www.aplikuj.pl/oferta/3/data-engineer">Data Engineer</a></li>')
            return FakeResponse('<li class="offer-card"><a class="offer-title" href="https://www.aplikuj.pl/oferta/1/frontend-developer">Frontend Developer</a></li>'
                '<li class="offer-card"><a class="offer-title" href="https://www.aplikuj.pl/oferta/2/operator-cnc">Programista CNC</a></li>'
                '<a href="/praca/it-informatyka/strona-2">Następna</a>')

    client = FakeClient()
    refs = AplikujSource().discover(client, 100)
    assert [r.source_posting_id for r in refs] == ["1", "3"]
    assert client.urls == ["https://www.aplikuj.pl/praca/it-informatyka", "https://www.aplikuj.pl/praca/it-informatyka/strona-2"]


def test_unscoped_plan_is_rejected_before_fetch(tmp_path):
    plan = tmp_path / "legacy.json"
    plan.write_text(json.dumps({"chunks": [], "aplikuj_scope": None}))
    with pytest.raises(RuntimeError, match="unscoped Aplikuj"):
        run(str(plan), ["aplikuj"], str(tmp_path / "crawl"), str(tmp_path / "raw"), str(tmp_path / "status.json"), 1)


def test_local_cache_prunes_non_it_raw_and_manifest_is_reconciled(tmp_path):
    crawl = tmp_path / "crawl" / "aplikuj" / "0"
    raw = tmp_path / "raw" / "aplikuj" / "0"
    crawl.mkdir(parents=True)
    raw.mkdir(parents=True)
    rows = [
        {"source_posting_id": "1", "title": "Python Developer", "source_projection": {"industry": "Informatyk"}},
        {"source_posting_id": "2", "title": "Kierowca C+E", "source_projection": {"industry": "Kierowca"}},
    ]
    corpus_bytes, corpus_meta = compressed_rows(rows)
    raw_bytes, raw_meta = compressed_rows([{"source_posting_id": r["source_posting_id"], "payload_text": r["title"]} for r in rows])
    (crawl / "corpus.jsonl.gz").write_bytes(corpus_bytes)
    (raw / "raw-observations.jsonl.gz").write_bytes(raw_bytes)
    (crawl / "manifest.json").write_text(json.dumps({"planned": 2, "postings": 2, "source_gone": 0, "errors": [], "corpus": corpus_meta, "raw_archive": raw_meta}))
    report = clean(tmp_path / "crawl", tmp_path / "raw", apply=True)
    assert report["removed"] == 1 and not report["failures"]
    assert [r["source_posting_id"] for r in read_gz(crawl / "corpus.jsonl.gz")] == ["1"]
    assert [r["source_posting_id"] for r in read_gz(raw / "raw-observations.jsonl.gz")] == ["1"]
    assert _manifest_ok(crawl / "manifest.json")
    assert clean(tmp_path / "crawl", tmp_path / "raw", apply=True)["removed"] == 0


def test_scoped_inventory_propagates_into_chunk_plan(tmp_path):
    from ingestion.plan_inventory_chunks import plan
    inventory = tmp_path / "inventory.jsonl.gz"
    data, _ = compressed_rows([{"source": "aplikuj", "source_posting_id": "77", "url": "https://www.aplikuj.pl/oferta/77/python-developer", "known": False}])
    inventory.write_bytes(data)
    (tmp_path / "manifest.json").write_text(json.dumps({"aplikuj_scope": "technical-it-v1"}))
    result = plan(str(inventory), str(tmp_path / "chunks.json"), chunk_size=250)
    assert result["aplikuj_scope"] == "technical-it-v1"
    assert result["unknown_total"] == 1
    assert result["chunks"][0]["rows"][0]["source_posting_id"] == "77"
