import json

from ingestion.run_file_backed_plan import _manifest_ok, build_status


def test_manifest_ok_requires_full_accounting_and_raw(tmp_path):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps({
        "planned": 10,
        "postings": 8,
        "source_gone": 2,
        "errors": [],
        "raw_archive": {"rows": 10},
    }))
    assert _manifest_ok(p)
    p.write_text(json.dumps({
        "planned": 10,
        "postings": 8,
        "source_gone": 1,
        "errors": [],
        "raw_archive": {"rows": 9},
    }))
    assert not _manifest_ok(p)


def test_status_counts_completed_chunks(tmp_path):
    plan = {"chunks": [
        {"source": "x", "chunk_index": 0, "count": 2, "rows": []},
        {"source": "x", "chunk_index": 1, "count": 3, "rows": []},
    ]}
    d = tmp_path / "x" / "0"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({
        "planned": 2,
        "postings": 1,
        "source_gone": 1,
        "errors": [],
        "raw_archive": {"rows": 2},
    }))
    s = build_status(plan, {"x"}, tmp_path)
    assert s["sources"]["x"]["planned"] == 5
    assert s["sources"]["x"]["accounted"] == 2
    assert s["sources"]["x"]["chunks_done"] == 1
    assert s["sources"]["x"]["pct"] == 40.0
