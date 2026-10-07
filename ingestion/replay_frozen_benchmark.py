from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path


EXPECTED_LABELS={
    "SAME_OPPORTUNITY":1,
    "DISTINCT_OPPORTUNITY":4,
    "UNRESOLVED":14,
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def _validate_pairs(postings: dict, pairs: list[dict], failures: list[str]) -> dict[str,int]:
    labels={}
    for pair in pairs:
        for side in ("a","b"):
            ref=pair[side]
            key=(ref["source"],ref["source_posting_id"])
            if key not in postings:
                failures.append(f"pair references missing posting: {key}")
        if not pair.get("features"):
            failures.append(f"pair {pair.get('pair_id')} missing features")
        if pair.get("candidate_evidence") is None:
            failures.append(f"pair {pair.get('pair_id')} missing candidate evidence")
        if not pair.get("rationale"):
            failures.append(f"pair {pair.get('pair_id')} missing rationale")
        labels[pair["label"]]=labels.get(pair["label"],0)+1
    return labels


def _replay_full(root: Path, manifest: dict, failures: list[str]):
    postings={}
    for item in manifest["postings"]:
        path=root/item["file"]
        text=path.read_text(encoding="utf-8")
        if sha256_text(text)!=item["file_sha256"]:
            failures.append(f"posting file checksum mismatch: {item['file']}")
            continue
        record=json.loads(text)
        if sha256_text(record["payload_text"])!=record["payload_sha256"]:
            failures.append(f"payload checksum mismatch: {item['file']}")
        key=(record["source"],record["source_posting_id"])
        postings[key]=record
    pairs_path=root/manifest["pairs_file"]
    pairs_text=pairs_path.read_text(encoding="utf-8")
    if sha256_text(pairs_text)!=manifest["pairs_file_sha256"]:
        failures.append("pairs.jsonl checksum mismatch")
    pairs=[json.loads(x) for x in pairs_text.splitlines() if x.strip()]
    return postings,pairs


def _replay_compact(root: Path, manifest: dict, failures: list[str]):
    compressed_parts=[]
    for item in manifest["snapshot_chunks"]:
        path=root/item["file"]
        if manifest.get("chunk_encoding")=="base64":
            data=base64.b64decode(path.read_text(encoding="ascii").strip())
        else:
            data=path.read_bytes()
        if len(data)!=item["bytes"]:
            failures.append(f"chunk byte length mismatch: {item['file']}")
        if sha256_bytes(data)!=item["sha256"]:
            failures.append(f"chunk checksum mismatch: {item['file']}")
        compressed_parts.append(data)
    compressed=b"".join(compressed_parts)
    if sha256_bytes(compressed)!=manifest["snapshot_file_sha256"]:
        failures.append("compressed snapshot checksum mismatch")
    try:
        raw=gzip.decompress(compressed)
    except Exception as exc:
        failures.append(f"gzip decompression failed: {type(exc).__name__}: {exc}")
        return {},[]
    expected_raw=manifest.get("snapshot_uncompressed_sha256") or manifest["snapshot_sha256"]
    if sha256_bytes(raw)!=expected_raw:
        failures.append("uncompressed snapshot checksum mismatch")
    records=[json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
    postings={}
    pairs=[]
    for record in records:
        kind=record.get("record_type")
        if kind=="posting":
            key=(record["source"],record["source_posting_id"])
            if not record.get("source_projection"):
                failures.append(f"posting missing source_projection: {key}")
            if not record.get("normalized_projection"):
                failures.append(f"posting missing normalized_projection: {key}")
            if not record.get("payload_sha256"):
                failures.append(f"posting missing raw payload hash: {key}")
            if not isinstance(record.get("raw_payload_bytes"),int) or record["raw_payload_bytes"]<=0:
                failures.append(f"posting missing raw payload byte count: {key}")
            postings[key]=record
        elif kind=="pair":
            pairs.append(record)
        else:
            failures.append(f"unknown snapshot record type: {kind!r}")
    return postings,pairs


def replay(root: Path) -> dict:
    manifest_path=root/"manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("snapshot manifest missing")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    failures=[]
    if manifest.get("snapshot_chunks"):
        postings,pairs=_replay_compact(root,manifest,failures)
        mode="compact-repo-snapshot"
    else:
        postings,pairs=_replay_full(root,manifest,failures)
        mode="full-generated-snapshot"
    labels=_validate_pairs(postings,pairs,failures)
    if len(postings)!=26:
        failures.append(f"expected 26 postings, got {len(postings)}")
    if len(pairs)!=19:
        failures.append(f"expected 19 pairs, got {len(pairs)}")
    if labels!=EXPECTED_LABELS:
        failures.append(f"label distribution mismatch: {labels} != {EXPECTED_LABELS}")
    result={
        "pass":not failures,
        "failures":failures,
        "mode":mode,
        "postings":len(postings),
        "pairs":len(pairs),
        "labels":labels,
        "network_used":False,
        "database_used":False,
    }
    if failures:
        raise RuntimeError(json.dumps(result,ensure_ascii=False))
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",default="data/evals/er-eval-02/snapshot")
    p.add_argument("--report")
    args=p.parse_args()
    result=replay(Path(args.snapshot))
    if args.report:
        out=Path(args.report); out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
