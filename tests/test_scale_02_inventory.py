from __future__ import annotations

import gzip
import json
from pathlib import Path

from ingestion.plan_inventory_chunks import plan


def test_chunk_plan_covers_unknown_once(tmp_path):
    rows=[
        {"source":"a","source_posting_id":"1","url":"u1","known":False},
        {"source":"a","source_posting_id":"2","url":"u2","known":True},
        {"source":"a","source_posting_id":"3","url":"u3","known":False},
        {"source":"b","source_posting_id":"1","url":"u4","known":False},
    ]
    raw=("\n".join(json.dumps(r) for r in rows)+"\n").encode()
    inv=tmp_path/"inventory.jsonl.gz"
    inv.write_bytes(gzip.compress(raw,mtime=0))
    out=tmp_path/"plan.json"
    result=plan(str(inv),str(out),1)
    assert result["unknown_total"]==3
    flattened=[r["source"]+":"+r["source_posting_id"] for c in result["chunks"] for r in c["rows"]]
    assert sorted(flattened)==["a:1","a:3","b:1"]
    assert result["chunks_by_source"]=={"a":2,"b":1}
