#!/usr/bin/env python3
"""RI-01 offline, read-only extraction checkpoint.

Usage: python3 scripts/ri01.py --corpus data/corpora/corpus-10/corpus.jsonl.gz
All generated job-text evidence stays in ignored .local-evidence/ri01.
"""
import argparse
import gzip
import html
import json
from collections import Counter
from pathlib import Path

from ingestion.ri01_review_ui import reviewer_html
from ingestion.requirement_intelligence import (
    VERSION, candidate_text, classify_title, concepts, extract, identity,
    language_candidate, sample_corpus, seniority, stable_hash, summarize,
)

ROOT = Path(__file__).resolve().parents[1]
QUOTA = {
    "bulldogjob": 20, "itleaders": 10, "justjoinit": 20,
    "michaelpage": 20, "nofluffjobs": 25, "pracuj": 20,
    "rocketjobs": 25, "solidjobs": 25, "teamquest": 20,
    "theprotocol": 15,
}
assert sum(QUOTA.values()) == 200


def write_jsonl(path, items):
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def make_explorer(assertions, summary):
    e = lambda v: html.escape(str(v or ""), quote=True)
    doc_counts = {}
    for name in sorted({n for a in assertions for n in a["concept_candidates"]}):
        doc_counts[name] = len({a["posting_id"] for a in assertions if name in a["concept_candidates"]})
    chips = "".join(f'<button type="button" class="chip" data-concept="{e(name)}">{e(name)} ({n})</button>' for name, n in sorted(doc_counts.items(), key=lambda x: (-x[1], x[0]))[:35])
    trs = []
    for a in assertions:
        search = " ".join([a.get("title") or "", a.get("source") or "",
                           a.get("company") or "", a["quote"], " ".join(a["concept_candidates"])]).lower()
        link = a.get("url") or ""
        url = f'<a href="{e(link)}" target="_blank" rel="noopener noreferrer">Otwórz ofertę</a>' if link.startswith("https://") else ""
        quote = (a["quote"][:280] + ("..." if len(a["quote"]) > 280 else ""))
        trs.append(f'<tr data-search="{e(search)}" data-source="{e(a["source"])}" data-family="{e(a["family_candidate"])}" data-modality="{e(a["modality_candidate"])}" data-concepts="{e("|".join(a["concept_candidates"]))}"><td><b>{e(a["title"])}</b><small>{e(a["source"])} · {e(a["company"])} · {e(a["seniority_candidate"])}</small>{url}</td><td><span class="tag">{e(a["modality_candidate"])}</span><small>{e(a["category_candidate"])}</small></td><td>{e(quote)}<small>JSON: <code>{e(a["source_path"])}</code></small></td><td>{e(", ".join(a["concept_candidates"]))}</td></tr>')
    options = lambda values: "".join(f'<option value="{e(x)}">{e(x)}</option>' for x in sorted(values))
    html_doc = """<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RI-01 · Evidence-backed Role Capability Explorer (candidate-only)</title>
<style>
:root{font-family:system-ui,sans-serif;color:#172031;background:#f5f7fb}*{box-sizing:border-box}
body{margin:0 auto;padding:24px;max-width:1440px}h1{margin:0 0 6px}p{max-width:850px;color:#475569}
.notice{border-left:4px solid #b45309;padding:12px 16px;background:#fff7ed;margin:16px 0}
.metric{display:inline-block;padding:16px 24px;background:white;border:1px solid #d8dee8;border-radius:12px;margin:0 10px 12px 0}
.metric b{font-size:26px;display:block}.filters{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}
input,select{padding:9px 12px;border:1px solid #bfc8d6;border-radius:8px;background:white;min-width:140px}
input{min-width:300px;flex:1}.chip{cursor:pointer;border:1px solid #bdcfe0;background:white;padding:6px 11px;border-radius:50px;margin:3px;font-size:12px}
table{width:100%;border-collapse:collapse;background:white;font-size:13px}td,th{padding:12px;border-bottom:1px solid #e6ebf2;vertical-align:top;text-align:left}
th{background:#e9eef7;position:sticky;top:0}td:first-child{min-width:230px}td:nth-child(3){width:47%}
small{color:#64748b;display:block;margin-top:6px;overflow-wrap:anywhere}code{font-size:11px}
.tag{background:#e8edf8;border-radius:6px;padding:3px 6px}a{color:#1155bb;display:block;margin-top:7px}
@media(max-width:800px){body{padding:10px}table{display:block;overflow-x:auto}input{min-width:100%}}
</style></head><body>
<h1>Role Capability Explorer · RI-01</h1>
<p>Eksplorator propozycji ekstrakcji z istniejącego korpusu. Statystyki dotyczą tylko 200 celowo dobranych rekordów, nie całego rynku pracy IT.</p>
<div class="notice"><strong>NIEWERYFIKOWANE:</strong> to są kandydaci wyodrębnieni algorytmem. Nie ma jeszcze zatwierdzonego goldsetu, a MUST/NICE z portali nie zawsze są zgodne z pełnym opisem. Nie interpretuj częstości jako popytu rynku.</div>
"""
    html_doc += f'<div class="metric"><b>{summary["sample_size"]}</b>Wybrane oferty</div><div class="metric"><b>{summary["candidate_assertions"]}</b>Kandydaci na stwierdzenia</div><div class="metric"><b>{summary["postings_with_assertions"]}</b>Oferty z ekstrakcją</div>'
    html_doc += '<h2>Pojęcia (liczba różnych ofert w próbce)</h2>' + chips
    html_doc += f'<h2 id="assertions">Dowody źródłowe <small id="visibleCount"></small></h2><div class="filters"><input id="query" type="search" placeholder="Szukaj treści, roli, firmy, technologii..."><select id="source"><option value="">Wszystkie portale</option>{options({a["source"] for a in assertions})}</select><select id="family"><option value="">Wszystkie rodziny ról</option>{options({a["family_candidate"] for a in assertions})}</select><select id="modality"><option value="">Wszystkie modalności</option>{options({a["modality_candidate"] for a in assertions})}</select><button type="button" id="clear">Wyczyść filtry</button></div>'
    html_doc += '<table><thead><tr><th>Oferta i źródło</th><th>Klasyfikacja</th><th>Dokładny fragment i pochodzenie</th><th>Pojęcia</th></tr></thead><tbody>' + "".join(trs) + '</tbody></table>'
    html_doc += """<script>
const rows=[...document.querySelectorAll('tbody tr')];
const query=document.querySelector('#query'),source=document.querySelector('#source'),
family=document.querySelector('#family'),modality=document.querySelector('#modality');
let concept='';
function filter(){let n=0;
for(const row of rows){let ok=(!query.value||row.dataset.search.includes(query.value.toLowerCase()))
&&(!source.value||row.dataset.source===source.value)
&&(!family.value||row.dataset.family===family.value)
&&(!modality.value||row.dataset.modality===modality.value)
&&(!concept||row.dataset.concepts.split('|').includes(concept));
row.hidden=!ok;if(ok)n++;}
document.querySelector('#visibleCount').textContent=n+' / '+rows.length+' wierszy';}
[query,source,family,modality].forEach(x=>x.addEventListener('input',filter));
document.querySelectorAll('[data-concept]').forEach(x=>x.addEventListener('click',()=>{concept=x.dataset.concept;filter();location.hash='assertions';}));
document.querySelector('#clear').addEventListener('click',()=>{query.value='';source.value='';family.value='';modality.value='';concept='';filter();});
filter();
</script></body></html>"""
    return html_doc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="data/corpora/corpus-10/corpus.jsonl.gz")
    parser.add_argument("--out", default=".local-evidence/ri01")
    args = parser.parse_args()
    corpus = ROOT / args.corpus
    out = ROOT / args.out
    if not corpus.is_file():
        raise SystemExit(f"No frozen corpus at {corpus}")
    with gzip.open(corpus, "rt", encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    selected = sample_corpus(records, QUOTA)
    if len(selected) != 200 or len({identity(r) for r in selected}) != 200:
        raise SystemExit("Sampling integrity failure: expected 200 unique source posting IDs")
    out.mkdir(parents=True, exist_ok=True)
    packets, assertions = [], []
    for r in selected:
        post_id = identity(r)
        split = "holdout" if int(stable_hash(post_id), 16) % 5 == 0 else "development"
        packets.append({
            "posting_id": post_id, "source": r["source"], "title": r.get("title"),
            "company": r.get("organization_mention"),
            "url": r.get("url"), "revision_id": r.get("revision_id"),
            "family_candidate": classify_title(r.get("title") or ""),
            "seniority_candidate": seniority(r), "language_candidate": language_candidate(r), "split": split,
            "text_preview": candidate_text(r)[:650],
            "review_status": "UNREVIEWED",
            "reviewer": None, "gold_assertions": None,
        })
        assertions.extend(extract(r))
    summary = summarize(selected, assertions)
    summary["split_counts"] = dict(Counter(p["split"] for p in packets))
    summary["language_candidates"] = dict(Counter(p["language_candidate"] for p in packets))
    summary["role_families"] = dict(Counter(p["family_candidate"] for p in packets))
    summary["seniority_candidates"] = dict(Counter(p["seniority_candidate"] for p in packets))
    summary["selection_quota"] = QUOTA
    summary["corpus_path"] = args.corpus
    summary["corpus_postings"] = len(records)
    write_jsonl(out / "review-packets.jsonl", packets)
    write_jsonl(out / "assertion-candidates.jsonl", assertions)
    (out / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "explorer.html").write_text(make_explorer(assertions, summary), encoding="utf-8")
    (out / "reviewer.html").write_text(reviewer_html(
        packets, assertions, {identity(r): candidate_text(r) for r in selected}
    ), encoding="utf-8")
    # Public-safe manifest: identifiers only, no entire descriptions or raw evidence.
    (out / "sample-ids.json").write_text(json.dumps({
        "extractor_version": VERSION,
        "source": args.corpus,
        "ids": [{"posting_id": p["posting_id"], "split": p["split"]} for p in packets],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
