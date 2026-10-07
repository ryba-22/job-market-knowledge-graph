from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import threading

from .acquire_file_backed import acquire


LIMITS = {"aplikuj": 4, "rocketjobs": 3, "solidjobs": 3, "justjoinit": 2, "nofluffjobs": 2, "michaelpage": 2, "eurotechjobs": 2, "bulldogjob": 1, "teamquest": 1, "itleaders": 1, "theprotocol": 1, "pracuj": 1, "hnwhoishiring": 4}
DELAYS = {"aplikuj": 0.25, "rocketjobs": 0.30, "solidjobs": 0.30, "justjoinit": 0.35, "nofluffjobs": 0.35, "michaelpage": 0.30, "eurotechjobs": 0.30, "bulldogjob": 0.50, "teamquest": 0.50, "itleaders": 0.50, "theprotocol": 0.50, "pracuj": 0.50, "hnwhoishiring": 0.05}


def _atomic_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _schedule_jobs(jobs: list[dict]) -> list[dict]:
    # Inventory plans are grouped by source. Round-robin by chunk index so one
    # high-volume source cannot occupy the entire worker pool while waiting on
    # its per-source semaphore.
    return sorted(jobs, key=lambda c: (int(c["chunk_index"]), c["source"]))


def _manifest_ok(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return (
        not m.get("errors")
        and int(m.get("planned", 0)) == int(m.get("postings", 0)) + int(m.get("source_gone", 0))
        and int((m.get("raw_archive") or {}).get("rows", 0)) == int(m.get("planned", 0))
    )


def build_status(plan: dict, sources: set[str], out_root: Path) -> dict:
    by_source = {}
    for source in sorted(sources):
        chunks = [c for c in plan["chunks"] if c["source"] == source]
        d = {
            "planned": sum(c["count"] for c in chunks),
            "chunks_total": len(chunks),
            "chunks_done": 0,
            "postings": 0,
            "source_gone": 0,
            "errors": 0,
        }
        for c in chunks:
            mp = out_root / source / str(c["chunk_index"]) / "manifest.json"
            if not mp.exists():
                continue
            try:
                m = json.loads(mp.read_text(encoding="utf-8"))
            except Exception:
                d["errors"] += 1
                continue
            d["postings"] += int(m.get("postings", 0))
            d["source_gone"] += int(m.get("source_gone", 0))
            d["errors"] += len(m.get("errors") or [])
            if _manifest_ok(mp):
                d["chunks_done"] += 1
        d["accounted"] = d["postings"] + d["source_gone"]
        d["pct"] = round(100 * d["accounted"] / d["planned"], 2) if d["planned"] else 100.0
        by_source[source] = d
    total = {
        "planned": sum(x["planned"] for x in by_source.values()),
        "postings": sum(x["postings"] for x in by_source.values()),
        "source_gone": sum(x["source_gone"] for x in by_source.values()),
        "errors": sum(x["errors"] for x in by_source.values()),
        "chunks_done": sum(x["chunks_done"] for x in by_source.values()),
        "chunks_total": sum(x["chunks_total"] for x in by_source.values()),
    }
    total["accounted"] = total["postings"] + total["source_gone"]
    total["pct"] = round(100 * total["accounted"] / total["planned"], 2) if total["planned"] else 100.0
    return {"updated_at": datetime.now(timezone.utc).isoformat(), "sources": by_source, "total": total}


def run(plan_path: str, sources: list[str], out_root: str, raw_root: str, status_path: str, max_attempts: int):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    selected = set(sources)
    out = Path(out_root)
    raw = Path(raw_root)
    status = Path(status_path)
    jobs = []
    for c in plan["chunks"]:
        if c["source"] not in selected:
            continue
        mp = out / c["source"] / str(c["chunk_index"]) / "manifest.json"
        if not _manifest_ok(mp):
            jobs.append(c)
    jobs = _schedule_jobs(jobs)

    lock = threading.Lock()
    current = build_status(plan, selected, out)
    _atomic_json(status, current)
    print(json.dumps(current, ensure_ascii=False), flush=True)

    sem = {s: threading.Semaphore(LIMITS.get(s, 1)) for s in selected}

    def work(c):
        source = c["source"]
        idx = int(c["chunk_index"])
        with sem[source]:
            manifest = acquire(
                plan_path,
                source,
                idx,
                str(out / source / str(idx)),
                str(raw / source / str(idx)),
                DELAYS.get(source, 0.30),
                max_attempts,
            )
            return source, idx, manifest

    max_workers = max(1, sum(LIMITS.get(s, 1) for s in selected))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(work, c) for c in jobs]
        for future in as_completed(futures):
            try:
                source, idx, manifest = future.result()
                event = {
                    "source": source,
                    "chunk_index": idx,
                    "postings": manifest["postings"],
                    "source_gone": manifest["source_gone"],
                    "errors": len(manifest["errors"]),
                }
            except Exception as exc:
                event = {"worker_error": f"{type(exc).__name__}: {exc}"}
            with lock:
                current = build_status(plan, selected, out)
                _atomic_json(status, current)
                print(json.dumps({"event": event, "status": current["total"]}, ensure_ascii=False), flush=True)

    final = build_status(plan, selected, out)
    _atomic_json(status, final)
    print(json.dumps(final, ensure_ascii=False, indent=2), flush=True)
    return final


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--sources", nargs="+", required=True)
    p.add_argument("--out-root", default=".local-crawl/scale-04")
    p.add_argument("--raw-root", default=".local-evidence/scale-04")
    p.add_argument("--status", default=".local-crawl/scale-04/status.json")
    p.add_argument("--max-attempts", type=int, default=4)
    args = p.parse_args()
    run(args.plan, args.sources, args.out_root, args.raw_root, args.status, args.max_attempts)


if __name__ == "__main__":
    main()
