from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpora" / "source-expansion-01"


class SourceExpansion01SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.manifest=json.loads((CORPUS/"manifest.json").read_text(encoding="utf-8"))
        self.quality=json.loads((CORPUS/"source-quality.json").read_text(encoding="utf-8"))
        compressed=(CORPUS/"corpus.jsonl.gz").read_bytes()
        self.raw=gzip.decompress(compressed)
        self.assertEqual(hashlib.sha256(compressed).hexdigest(),self.manifest["compressed_sha256"])
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(),self.manifest["uncompressed_sha256"])
        self.rows=[json.loads(line) for line in self.raw.decode("utf-8").splitlines() if line]

    def test_exact_market500_contract(self):
        expected={
            "justjoinit":150,
            "theprotocol":50,
            "nofluffjobs":75,
            "rocketjobs":75,
            "bulldogjob":75,
            "pracuj":75,
        }
        counts={}
        for row in self.rows:
            counts[row["source"]]=counts.get(row["source"],0)+1
            self.assertTrue(row["source_posting_id"])
            self.assertTrue(row["normalized_projection_hash"])
            self.assertTrue(row["raw_payload_sha256"])
        self.assertEqual(len(self.rows),500)
        self.assertEqual(counts,expected)
        self.assertEqual(self.manifest["postings"],500)
        self.assertEqual(self.manifest["by_source"],expected)

    def test_source_identities_are_unique_per_source(self):
        seen=set()
        for row in self.rows:
            key=(row["source"],row["source_posting_id"])
            self.assertNotIn(key,seen)
            seen.add(key)
        self.assertEqual(len(seen),500)

    def test_pracuj_provenance_is_secondary(self):
        pracuj=[row for row in self.rows if row["source"]=="pracuj"]
        self.assertEqual(len(pracuj),75)
        self.assertTrue(all(
            row["source_projection"].get("observation_provenance")=="SECONDARY_PUBLIC_INDEX"
            for row in pracuj
        ))
        q=self.quality["sources"]["pracuj"]
        self.assertEqual(q["provenance_class"],"SECONDARY_PUBLIC_INDEX")
        self.assertFalse(q["direct_source_access"])

    def test_other_new_sources_are_direct(self):
        for source in ("nofluffjobs","rocketjobs","bulldogjob"):
            self.assertEqual(self.quality["sources"][source]["provenance_class"],"DIRECT")
            rows=[r for r in self.rows if r["source"]==source]
            self.assertEqual(len(rows),75)
            self.assertTrue(all(
                r["source_projection"].get("observation_provenance","").startswith("DIRECT")
                for r in rows
            ))


if __name__ == "__main__":
    unittest.main()
