"""Curated real-offer diagnostic, NOT an independently held-out benchmark."""
from __future__ import annotations
from collections import Counter
import argparse
import json
from pathlib import Path

from .run_classification02 import verify_output


def evaluate(labels_path: Path, source: Path, target: Path) -> dict:
    verify = verify_output(source, target)
    if verify["status"] != "PASS":
        raise ValueError(f"not a valid CLASSIFICATION-02 sidecar: {verify}")
    from .clean_aplikuj_cache import read_gz
    decisions = {r["source_posting_id"]:r for r in read_gz(target / "assessments.jsonl.gz")}
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    cases = labels["cases"]
    if len({r["id"] for r in cases}) != len(cases):
        raise ValueError("duplicate curated IDs")
    if not set(r["id"] for r in cases).issubset(decisions):
        raise ValueError("curated ID outside classified source population")
    confusion = Counter()
    by_split = Counter()
    failures = []
    for case in cases:
        expected = case["expected"]
        actual = decisions[case["id"]]["assessment"]["status"]
        confusion[f"{expected} -> {actual}"] += 1
        by_split[f'{case["split"]}: {expected} -> {actual}'] += 1
        if expected != actual:
            failures.append({"id":case["id"],"expected":expected,"actual":actual})
    dangerous = [r for r in failures if r["actual"] in ("IT_CONFIRMED", "NON_IT_CONFIRMED")
                 and r["expected"] != r["actual"]]
    return {
        "method":"author-curated development/diagnostic set, NOT independent blinded gold",
        "cases":len(cases),"matches":len(cases)-len(failures),
        "abstentions":[r for r in failures if r["actual"]=="REVIEW_REQUIRED"],
        "disagreements":failures,
        "potential_unsafe_decisions":dangerous,
        "confusion":dict(sorted(confusion.items())),
        "by_split":dict(sorted(by_split.items())),
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,default=Path(".local-crawl/scale-04-it-v2"))
    p.add_argument("--classified",type=Path,default=Path(".local-crawl/classification-02"))
    p.add_argument("--labels",type=Path,default=Path("tests/fixtures/classification02_curated_labels.json"))
    p.add_argument("--output",type=Path,default=Path("reports/classification-02/diagnostic-eval.json"))
    args=p.parse_args()
    result=evaluate(args.labels,args.source,args.classified)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
