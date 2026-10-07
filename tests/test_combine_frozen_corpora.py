from __future__ import annotations

import gzip
import json
from pathlib import Path

from ingestion.combine_frozen_corpora import combine


def _write(path: Path, rows):
    raw=("\n".join(json.dumps(r,sort_keys=True,separators=(",",":")) for r in rows)+"\n").encode()
    path.write_bytes(gzip.compress(raw,compresslevel=9,mtime=0))


def test_combine_is_deterministic_and_source_identity_scoped(tmp_path):
    a=tmp_path/"a.gz"; b=tmp_path/"b.gz"; out=tmp_path/"out"
    _write(a,[{"source":"a","source_posting_id":"2"},{"source":"a","source_posting_id":"1"}])
    _write(b,[{"source":"b","source_posting_id":"1"}])
    m=combine(str(a),str(b),str(out),"TEST")
    assert m["postings"]==3
    assert m["by_source"]=={"a":2,"b":1}
    first=(out/"corpus.jsonl.gz").read_bytes()
    m2=combine(str(a),str(b),str(out),"TEST")
    assert first==(out/"corpus.jsonl.gz").read_bytes()
    assert m["compressed_sha256"]==m2["compressed_sha256"]


def test_combine_rejects_conflicting_duplicate(tmp_path):
    a=tmp_path/"a.gz"; b=tmp_path/"b.gz"
    _write(a,[{"source":"a","source_posting_id":"1","title":"A"}])
    _write(b,[{"source":"a","source_posting_id":"1","title":"B"}])
    try:
        combine(str(a),str(b),str(tmp_path/"out"),"TEST")
    except RuntimeError as exc:
        assert "conflicting duplicate" in str(exc)
    else:
        raise AssertionError("expected duplicate conflict")
