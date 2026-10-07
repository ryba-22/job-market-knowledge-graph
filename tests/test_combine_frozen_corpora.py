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


def test_jsonl_reader_does_not_split_unicode_line_separator(tmp_path):
    import gzip,json
    from ingestion.assemble_corpus_version import assemble
    row={"source":"x","source_posting_id":"1","title":"before\u2028after"}
    raw=(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8")
    base=tmp_path/"base.gz"
    base.write_bytes(gzip.compress(raw,mtime=0))
    extra=tmp_path/"extra.gz"
    extra.write_bytes(gzip.compress(b"",mtime=0))
    out=tmp_path/"out"
    m=assemble(str(base),[str(extra)],str(out),"TEST")
    assert m["postings"]==1
