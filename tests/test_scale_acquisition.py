from __future__ import annotations

import gzip
import json
from pathlib import Path

from ingestion.assemble_corpus_version import assemble
from ingestion.scale_acquisition import load_known_ids


def _write(path: Path, rows):
    raw = (
        "\n".join(
            json.dumps(r, sort_keys=True, separators=(",", ":"))
            for r in rows
        )
        + "\n"
    ).encode()
    path.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))


def test_load_known_ids_is_source_scoped(tmp_path):
    p = tmp_path / "base.gz"
    _write(
        p,
        [
            {"source": "a", "source_posting_id": "1"},
            {"source": "a", "source_posting_id": "2"},
            {"source": "b", "source_posting_id": "1"},
        ],
    )

    assert load_known_ids(str(p), "a") == {"1", "2"}
    assert load_known_ids(str(p), "b") == {"1"}


def test_assemble_many_slices_is_deterministic(tmp_path):
    base = tmp_path / "base.gz"
    s1 = tmp_path / "s1.gz"
    s2 = tmp_path / "s2.gz"

    _write(base, [{"source": "a", "source_posting_id": "1"}])
    _write(s1, [{"source": "a", "source_posting_id": "2"}])
    _write(s2, [{"source": "b", "source_posting_id": "1"}])

    out = tmp_path / "out"
    m = assemble(str(base), [str(s2), str(s1)], str(out), "X")
    first = (out / "corpus.jsonl.gz").read_bytes()

    m2 = assemble(str(base), [str(s1), str(s2)], str(out), "X")

    assert m["postings"] == 3
    assert m["by_source"] == {"a": 2, "b": 1}
    assert first == (out / "corpus.jsonl.gz").read_bytes()
    assert m["compressed_sha256"] == m2["compressed_sha256"]


def test_assemble_rejects_conflicting_existing_identity(tmp_path):
    base = tmp_path / "base.gz"
    s1 = tmp_path / "s1.gz"

    _write(base, [{"source": "a", "source_posting_id": "1", "title": "old"}])
    _write(s1, [{"source": "a", "source_posting_id": "1", "title": "new"}])

    try:
        assemble(str(base), [str(s1)], str(tmp_path / "out"), "X")
    except RuntimeError as exc:
        assert "conflicting duplicate" in str(exc)
    else:
        raise AssertionError("expected conflict")
