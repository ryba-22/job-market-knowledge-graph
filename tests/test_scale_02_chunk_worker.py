import json

from ingestion.process_inventory_chunk import _load_chunk


def test_load_chunk_uses_frozen_source_and_index(tmp_path):
    plan = {
        "chunks": [
            {"source": "a", "chunk_index": 0, "count": 1, "rows": [{"source_posting_id": "1", "url": "u"}]},
            {"source": "a", "chunk_index": 1, "count": 1, "rows": [{"source_posting_id": "2", "url": "v"}]},
        ]
    }
    path = tmp_path / "chunks.json"
    path.write_text(json.dumps(plan))
    assert _load_chunk(str(path), "a", 1)["rows"][0]["source_posting_id"] == "2"
