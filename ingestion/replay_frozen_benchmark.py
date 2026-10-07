from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_LABELS={
    "SAME_OPPORTUNITY":1,
    "DISTINCT_OPPORTUNITY":4,
    "UNRESOLVED":14,
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def replay(root: Path) -> dict:
    manifest_path=root/"manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("snapshot manifest missing")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    failures=[]

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

    labels={}
    for pair in pairs:
        for side in ("a","b"):
            key=(pair[side]["source"],pair[side]["source_posting_id"])
            if key not in postings:
                failures.append(f"pair references missing posting: {key}")
        if not pair.get("features"):
            failures.append(f"pair {pair['pair_id']} missing features")
        if pair.get("candidate_evidence") is None:
            failures.append(f"pair {pair['pair_id']} missing candidate evidence")
        if not pair.get("rationale"):
            failures.append(f"pair {pair['pair_id']} missing rationale")
        labels[pair["label"]]=labels.get(pair["label"],0)+1

    if len(postings)!=26:
        failures.append(f"expected 26 postings, got {len(postings)}")
    if len(pairs)!=19:
        failures.append(f"expected 19 pairs, got {len(pairs)}")
    if labels!=EXPECTED_LABELS:
        failures.append(f"label distribution mismatch: {labels} != {EXPECTED_LABELS}")

    result={
        "pass":not failures,
        "failures":failures,
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
