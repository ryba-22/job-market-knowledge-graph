"""Read-only integrity verification for lossless Aplikuj IT-category-v2 batches."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

from .clean_aplikuj_cache import read_gz
from .run_file_backed_plan import _manifest_ok
from .aplikuj_policy import APLIKUJ_SCOPE, STATUSES


def verify(root: Path) -> dict:
    result = {"scope": APLIKUJ_SCOPE, "v2_chunks": 0, "postings": 0, "assessment_counts": dict.fromkeys(STATUSES, 0),
              "legacy_chunks_ignored": 0, "errors": []}
    for path in sorted((root / "aplikuj").glob("*/manifest.json")):
        m = json.loads(path.read_text(encoding="utf-8"))
        if m.get("scope") != APLIKUJ_SCOPE:
            result["legacy_chunks_ignored"] += 1
            continue
        try:
            if not _manifest_ok(path, expected_scope=APLIKUJ_SCOPE):
                raise ValueError("manifest accounting or assessment count mismatch")
            corpus_path = path.with_name("corpus.jsonl.gz")
            raw_path = Path(m["raw_archive_location"])
            assessment_path = path.with_name("assessments.jsonl.gz")
            for f, meta in ((corpus_path, m["corpus"]),
                            (raw_path, m["raw_archive"]),
                            (assessment_path, m["assessment_archive"])):
                packed = f.read_bytes()
                unpacked = gzip.decompress(packed)
                if hashlib.sha256(packed).hexdigest() != meta["compressed_sha256"]:
                    raise ValueError(f"compressed checksum mismatch: {f}")
                if hashlib.sha256(unpacked).hexdigest() != meta["uncompressed_sha256"]:
                    raise ValueError(f"uncompressed checksum mismatch: {f}")
            corpus = read_gz(corpus_path)
            raw = read_gz(raw_path)
            assessments = read_gz(assessment_path)
            ids = [str(r["source_posting_id"]) for r in corpus]
            assessed_ids = [str(r["source_posting_id"]) for r in assessments]
            raw_ids = [str(r["source_posting_id"]) for r in raw]
            if len(ids) != len(set(ids)) or set(ids) != set(assessed_ids) or len(assessed_ids) != len(set(assessed_ids)):
                raise ValueError("corpus / assessment ID mismatch or duplicates")
            if not set(ids).issubset(set(raw_ids)) or len(raw_ids) != len(set(raw_ids)):
                raise ValueError("missing or duplicated source raw observation")
            if len(ids) != m["postings"] or len(raw) != m["raw_archive"]["rows"]:
                raise ValueError("row count mismatch")
            raw_by_id = {str(r["source_posting_id"]): r for r in raw}
            for r in assessments:
                if r["raw_payload_sha256"] != raw_by_id[str(r["source_posting_id"])]["payload_sha256"]:
                    raise ValueError("assessment points to different raw revision")
            counts = Counter(a["assessment"]["status"] for a in assessments)
            if any(key not in STATUSES for key in counts) or any(counts[k] != m["assessment_counts"][k] for k in STATUSES):
                raise ValueError("classifier counts mismatch")
            result["v2_chunks"] += 1
            result["postings"] += len(ids)
            for k in STATUSES:
                result["assessment_counts"][k] += counts[k]
        except Exception as exc:
            result["errors"].append({"chunk": path.parent.name, "error": str(exc)})
    result["status"] = "PASS" if result["v2_chunks"] and not result["errors"] else ("NOT_RUN" if not result["v2_chunks"] and not result["errors"] else "FAIL")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".local-crawl/scale-04-it-v2")
    args = p.parse_args()
    result = verify(Path(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
