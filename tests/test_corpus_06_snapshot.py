from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import unittest


ROOT=Path(__file__).resolve().parents[1]
CORPUS=ROOT/"data"/"corpora"/"corpus-06"


class Corpus06SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.manifest=json.loads((CORPUS/"manifest.json").read_text(encoding="utf-8"))
        compressed=(CORPUS/"corpus.jsonl.gz").read_bytes()
        self.raw=gzip.decompress(compressed)
        self.assertEqual(
            hashlib.sha256(compressed).hexdigest(),
            "9abf08c4fc3259fbf79dca6ec32c9ba58d271b9f3a55a1f1d7577d9b31f06852",
        )
        self.assertEqual(
            hashlib.sha256(self.raw).hexdigest(),
            "162c8c50221e45e679f22d11c8605b020088a41e0f07bda2070fe2c44269d309",
        )
        self.rows=[json.loads(x) for x in self.raw.decode("utf-8").splitlines() if x]

    def test_exact_1583_contract(self):
        expected={
            "justjoinit":400,
            "theprotocol":50,
            "nofluffjobs":400,
            "rocketjobs":400,
            "bulldogjob":213,
            "pracuj":120,
        }
        counts={}
        seen=set()
        for row in self.rows:
            counts[row["source"]]=counts.get(row["source"],0)+1
            key=(row["source"],row["source_posting_id"])
            self.assertNotIn(key,seen)
            seen.add(key)
            self.assertTrue(row["raw_payload_sha256"])
            self.assertTrue(row["normalized_projection_hash"])
        self.assertEqual(len(self.rows),1583)
        self.assertEqual(counts,expected)
        self.assertEqual(self.manifest["postings"],1583)
        self.assertEqual(self.manifest["by_source"],expected)

    def test_scale_provenance_conserves_growth(self):
        p=json.loads((CORPUS/"acquisition-provenance.json").read_text(encoding="utf-8"))
        successes=sum(
            x.get("successes",0)
            for x in p["source_batches"].values()
        )
        self.assertEqual(successes,1015)
        self.assertEqual(p["base_corpus"]["postings"]+successes,1583)
        self.assertEqual(p["result"]["new_postings"],1015)
        self.assertEqual(p["result"]["postings"],1583)

    def test_pracuj_remains_secondary(self):
        quality=json.loads((CORPUS/"source-quality.json").read_text(encoding="utf-8"))
        self.assertEqual(
            quality["sources"]["pracuj"]["provenance_class"],
            "SECONDARY_PUBLIC_INDEX",
        )
        self.assertFalse(quality["sources"]["pracuj"]["direct_source_access"])
        pracuj=[r for r in self.rows if r["source"]=="pracuj"]
        self.assertEqual(len(pracuj),120)
        self.assertTrue(all(
            r["transport_version"]=="public-mirror-isitfair-v1"
            for r in pracuj
        ))

    def test_protocol_growth_block_is_explicit(self):
        quality=json.loads((CORPUS/"source-quality.json").read_text(encoding="utf-8"))
        self.assertEqual(quality["sources"]["theprotocol"]["count"],50)
        self.assertTrue(quality["sources"]["theprotocol"]["growth_blocked"])


if __name__=="__main__":
    unittest.main()
