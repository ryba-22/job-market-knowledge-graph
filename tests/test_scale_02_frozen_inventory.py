from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INV = ROOT / "data" / "inventories" / "scale-02"


class Scale02FrozenInventoryTest(unittest.TestCase):
    def test_frozen_inventory_contract(self):
        manifest=json.loads((INV/"manifest.json").read_text(encoding="utf-8"))
        compressed=(INV/"inventory.jsonl.gz").read_bytes()
        raw=gzip.decompress(compressed)
        self.assertEqual(hashlib.sha256(compressed).hexdigest(),manifest["compressed_sha256"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest["uncompressed_sha256"])
        rows=[json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
        self.assertEqual(len(rows),20359)
        self.assertEqual(manifest["discoverable_total"],20359)
        self.assertEqual(manifest["unknown_total"],18966)
        self.assertEqual(
            manifest["sources"],
            {
                "justjoinit":{"discoverable":1405,"known":381,"unknown":1024},
                "nofluffjobs":{"discoverable":2616,"known":399,"unknown":2217},
                "rocketjobs":{"discoverable":15468,"known":400,"unknown":15068},
                "bulldogjob":{"discoverable":870,"known":213,"unknown":657},
            },
        )

    def test_chunk_plan_covers_every_unknown_identity_once(self):
        plan=json.loads((INV/"chunks.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["chunk_size"],250)
        self.assertEqual(plan["unknown_total"],18966)
        self.assertEqual(
            plan["chunks_by_source"],
            {"bulldogjob":3,"justjoinit":5,"nofluffjobs":9,"rocketjobs":61},
        )
        self.assertEqual(len(plan["chunks"]),78)
        seen=set()
        for chunk in plan["chunks"]:
            self.assertLessEqual(chunk["count"],250)
            self.assertEqual(chunk["count"],len(chunk["rows"]))
            for row in chunk["rows"]:
                key=(row["source"],row["source_posting_id"])
                self.assertNotIn(key,seen)
                self.assertFalse(row["known"])
                seen.add(key)
        self.assertEqual(len(seen),18966)


if __name__=="__main__":
    unittest.main()
