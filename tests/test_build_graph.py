import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(ROOT/"scripts/build_graph.py")], check=True)

graph = json.loads((ROOT/"reports/graph.json").read_text(encoding="utf-8"))
ids = {n["id"] for n in graph["nodes"]}
assert "TECHNOLOGY:vLLM" in ids
assert "TECHNOLOGY:Kubernetes" in ids
assert any(e["relation"] == "ROLE_REQUIRES_CAPABILITY" for e in graph["edges"])
print("PASS")
