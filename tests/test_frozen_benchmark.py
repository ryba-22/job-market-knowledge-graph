from pathlib import Path
import json

from ingestion.replay_frozen_benchmark import replay


def test_replay_frozen_snapshot_without_network_or_database(tmp_path):
    root=tmp_path/"snapshot"
    postings=root/"postings"
    postings.mkdir(parents=True)
    payload="hello"
    record={
        "source":"a","source_posting_id":"1","payload_text":payload,
        "payload_sha256":__import__("hashlib").sha256(payload.encode()).hexdigest()
    }
    text=json.dumps(record,sort_keys=True,indent=2)+"\n"
    sha=__import__("hashlib").sha256(text.encode()).hexdigest()
    (postings/"a__1.json").write_text(text)
    pairs=""
    (root/"pairs.jsonl").write_text(pairs)
    manifest={
        "postings":[{"source":"a","source_posting_id":"1","file":"postings/a__1.json","file_sha256":sha}],
        "pairs_file":"pairs.jsonl",
        "pairs_file_sha256":__import__("hashlib").sha256(pairs.encode()).hexdigest()
    }
    (root/"manifest.json").write_text(json.dumps(manifest))
    try:
        replay(root)
    except RuntimeError as exc:
        msg=str(exc)
        assert "expected 26 postings" in msg
        assert "expected 19 pairs" in msg
    else:
        raise AssertionError("fixture should fail cardinality guard")
