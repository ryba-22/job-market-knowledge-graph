import gzip
import json

import pytest

from ingestion.assemble_local_crawl import assemble


def _write_gz(path, rows):
    raw = ("\n".join(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rows) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(raw, mtime=0))


def _manifest(path, planned, postings, source_gone):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "planned": planned,
        "postings": postings,
        "source_gone": source_gone,
        "errors": [],
        "raw_archive": {"rows": planned},
        "corpus": {"compressed_sha256": "abc"},
    }))


def test_assemble_requires_every_chunk_and_merges(tmp_path):
    base = tmp_path / "base.jsonl.gz"
    _write_gz(base, [{"source": "x", "source_posting_id": "1", "title": "old"}])
    plan = tmp_path / "chunks.json"
    plan.write_text(json.dumps({
        "unknown_total": 2,
        "chunks": [
            {"source": "x", "chunk_index": 0, "count": 1},
            {"source": "y", "chunk_index": 0, "count": 1},
        ],
    }))
    x = tmp_path / "crawl" / "x" / "0"
    y = tmp_path / "crawl" / "y" / "0"
    _write_gz(x / "corpus.jsonl.gz", [{"source": "x", "source_posting_id": "2", "title": "new"}])
    _write_gz(y / "corpus.jsonl.gz", [])
    _manifest(x / "manifest.json", 1, 1, 0)
    _manifest(y / "manifest.json", 1, 0, 1)

    result = assemble(str(base), str(plan), str(tmp_path / "crawl"), str(tmp_path / "out"), "CORPUS-X")
    assert result["postings"] == 2
    assert result["base_postings"] == 1
    assert result["new_postings"] == 1
    assert result["source_gone"] == 1
    assert result["planned_unknown"] == 2


def test_assemble_rejects_incomplete_chunk(tmp_path):
    base = tmp_path / "base.jsonl.gz"
    _write_gz(base, [])
    plan = tmp_path / "chunks.json"
    plan.write_text(json.dumps({
        "unknown_total": 1,
        "chunks": [{"source": "x", "chunk_index": 0, "count": 1}],
    }))
    with pytest.raises(RuntimeError, match="incomplete crawl"):
        assemble(str(base), str(plan), str(tmp_path / "crawl"), str(tmp_path / "out"), "CORPUS-X")
