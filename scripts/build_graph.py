#!/usr/bin/env python3
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
jobs = []
for p in sorted((ROOT / "data/jobs").glob("*.json")):
    jobs.append(json.loads(p.read_text(encoding="utf-8")))

nodes = {}
edges = []
tech = Counter()
processes = Counter()
keywords = Counter()

for job in jobs:
    offer = f"OFFER:{job['id']}"
    nodes[offer] = {"id": offer, "type": "OFFER", "label": job["role"], "company": job["company"]}
    for item in job.get("technologies", []):
        nid = f"TECHNOLOGY:{item['name']}"
        nodes.setdefault(nid, {"id":nid,"type":"TECHNOLOGY","label":item["name"]})
        tech[item["name"]] += 1
        edges.append({"from":offer,"relation":"OFFER_MENTIONS_NODE","to":nid})
    for name in job.get("processes", []):
        nid = f"PROCESS:{name}"
        nodes.setdefault(nid, {"id":nid,"type":"PROCESS","label":name})
        processes[name] += 1
        edges.append({"from":offer,"relation":"OFFER_MENTIONS_NODE","to":nid})
    for kw in job.get("keywords", []):
        keywords[kw] += 1
    for e in job.get("graph_edges", []):
        edges.append(e)
        for endpoint in ("from","to"):
            nid=e[endpoint]
            typ=nid.split(":",1)[0] if ":" in nid else "CONCEPT"
            label=nid.split(":",1)[1] if ":" in nid else nid
            nodes.setdefault(nid, {"id":nid,"type":typ,"label":label})

(ROOT/"knowledge/nodes.jsonl").write_text(
    "\n".join(json.dumps(v,ensure_ascii=False) for v in sorted(nodes.values(), key=lambda x:x["id"]))+"\n",
    encoding="utf-8"
)
(ROOT/"knowledge/edges.jsonl").write_text(
    "\n".join(json.dumps(v,ensure_ascii=False) for v in edges)+"\n",
    encoding="utf-8"
)
(ROOT/"reports/graph.json").write_text(
    json.dumps({"nodes":list(nodes.values()),"edges":edges},ensure_ascii=False,indent=2)+"\n",
    encoding="utf-8"
)

lines = [
    "# Market snapshot",
    "",
    f"Analyzed offers: **{len(jobs)}**",
    "",
    "## Technologies",
]
lines += [f"- {name}: {count}" for name,count in tech.most_common()]
lines += ["", "## Processes"]
lines += [f"- {name}: {count}" for name,count in processes.most_common()]
lines += ["", "## Keywords"]
lines += [f"- {name}: {count}" for name,count in keywords.most_common()]
(ROOT/"reports/market-snapshot.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
print(f"built graph: {len(nodes)} nodes, {len(edges)} edges from {len(jobs)} offers")
