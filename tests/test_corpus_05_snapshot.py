from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import unittest


ROOT=Path(__file__).resolve().parents[1]
CORPUS=ROOT/"data"/"corpora"/"corpus-05"
PRACUJ=ROOT/"data"/"corpora"/"source-expansion-03-pracuj"


class Corpus05SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.manifest=json.loads((CORPUS/"manifest.json").read_text(encoding="utf-8"))
        compressed=(CORPUS/"corpus.jsonl.gz").read_bytes()
        self.raw=gzip.decompress(compressed)
        self.assertEqual(
            hashlib.sha256(compressed).hexdigest(),
            "db92dd6b1a5560e815db3220b3604573f46ac349bd64eeb682bca9bd276ea013",
        )
        self.assertEqual(
            hashlib.sha256(self.raw).hexdigest(),
            "d6342dcc11625a831c3a9f24ca36b3df3d1edbfe5bd59e6df4f740a81b0c86dd",
        )
        self.rows=[json.loads(x) for x in self.raw.decode("utf-8").splitlines() if x]

    def test_exact_568_six_source_contract(self):
        expected={
            "justjoinit":150,
            "theprotocol":50,
            "nofluffjobs":100,
            "rocketjobs":100,
            "bulldogjob":93,
            "pracuj":75,
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
        self.assertEqual(len(self.rows),568)
        self.assertEqual(counts,expected)
        self.assertEqual(self.manifest["postings"],568)
        self.assertEqual(self.manifest["by_source"],expected)

    def test_pracuj_is_secondary_public_index_only(self):
        rows=[r for r in self.rows if r["source"]=="pracuj"]
        self.assertEqual(len(rows),75)
        self.assertTrue(all(
            r["transport_version"]=="public-mirror-isitfair-v1"
            for r in rows
        ))
        self.assertTrue(all(
            r["source_projection"].get("observation_provenance")=="SECONDARY_PUBLIC_INDEX"
            for r in rows
        ))
        q=json.loads((CORPUS/"source-quality.json").read_text(encoding="utf-8"))
        self.assertFalse(q["sources"]["pracuj"]["direct_source_access"])
        self.assertEqual(q["sources"]["pracuj"]["provenance_class"],"SECONDARY_PUBLIC_INDEX")

    def test_pracuj_source_manifest_preserves_original_ids(self):
        manifest=json.loads((PRACUJ/"source-manifest.json").read_text(encoding="utf-8"))
        rows=manifest["sources"]["pracuj"]
        self.assertEqual(len(rows),75)
        self.assertEqual(len({x["source_posting_id"] for x in rows}),75)
        self.assertTrue(all("pracuj.pl" in x["url"] for x in rows))
        self.assertTrue(all(x["observation_provenance"]=="SECONDARY_PUBLIC_INDEX" for x in rows))


if __name__=="__main__":
    unittest.main()
