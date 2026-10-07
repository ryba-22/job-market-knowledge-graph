from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import unittest


ROOT=Path(__file__).resolve().parents[1]
CORPUS=ROOT/"data"/"corpora"/"corpus-03"


class Corpus03SnapshotTest(unittest.TestCase):
    def test_frozen_real400_contract(self):
        manifest=json.loads((CORPUS/"manifest.json").read_text(encoding="utf-8"))
        compressed=(CORPUS/"corpus.jsonl.gz").read_bytes()
        raw=gzip.decompress(compressed)
        self.assertEqual(hashlib.sha256(compressed).hexdigest(),manifest["compressed_sha256"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest["uncompressed_sha256"])
        rows=[json.loads(x) for x in raw.decode("utf-8").splitlines() if x]
        self.assertEqual(len(rows),400)
        by_source={}
        keys=set()
        for row in rows:
            key=(row["source"],row["source_posting_id"])
            self.assertNotIn(key,keys)
            keys.add(key)
            by_source[row["source"]]=by_source.get(row["source"],0)+1
            self.assertTrue(row["raw_payload_sha256"])
            self.assertTrue(row["normalized_projection_hash"])
        self.assertEqual(by_source,{
            "justjoinit":150,
            "theprotocol":50,
            "nofluffjobs":100,
            "rocketjobs":100,
        })

    def test_component_contract(self):
        manifest=json.loads((CORPUS/"manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["components"]["CORPUS-02"]["postings"],200)
        self.assertEqual(manifest["components"]["SOURCE-EXPANSION-01"]["postings"],200)


if __name__=="__main__":
    unittest.main()
