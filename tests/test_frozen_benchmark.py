from pathlib import Path
import json
import socket

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


def test_repo_frozen_benchmark_replays_with_socket_blocked(monkeypatch):
    def deny_network(*args,**kwargs):
        raise AssertionError("network access attempted during frozen benchmark replay")

    monkeypatch.setattr(socket.socket,"connect",deny_network)
    root=Path(__file__).resolve().parents[1]/"data"/"evals"/"er-eval-02"/"snapshot"
    result=replay(root)
    assert result["pass"] is True
    assert result["mode"]=="compact-repo-snapshot"
    assert result["postings"]==26
    assert result["pairs"]==19
    assert result["labels"]=={
        "SAME_OPPORTUNITY":1,
        "DISTINCT_OPPORTUNITY":4,
        "UNRESOLVED":14,
    }
    assert result["network_used"] is False
    assert result["database_used"] is False
