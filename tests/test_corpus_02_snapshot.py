from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpora" / "corpus-02"


class Corpus02SnapshotTest(unittest.TestCase):
    def test_frozen_real200_contract(self):
        manifest=json.loads((CORPUS/"manifest.json").read_text(encoding="utf-8"))
        compressed=(CORPUS/"corpus.jsonl.gz").read_bytes()
        raw=gzip.decompress(compressed)
        self.assertEqual(hashlib.sha256(compressed).hexdigest(),manifest["compressed_sha256"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest["uncompressed_sha256"])
        rows=[json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
        self.assertEqual(len(rows),200)
        by_source={}
        for row in rows:
            by_source[row["source"]]=by_source.get(row["source"],0)+1
            self.assertTrue(row["source_posting_id"])
            self.assertTrue(row["raw_payload_sha256"])
            self.assertTrue(row["normalized_projection_hash"])
        self.assertEqual(by_source,{"justjoinit":150,"theprotocol":50})

    def test_source_identity_manifests_match_contract(self):
        tp=json.loads((CORPUS/"theprotocol-manifest.json").read_text(encoding="utf-8"))
        jj=json.loads((CORPUS/"justjoinit-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(tp["sources"]["theprotocol"]),50)
        self.assertEqual(len(jj["sources"]["justjoinit"]),150)
        self.assertEqual(
            len({x["source_posting_id"] for x in tp["sources"]["theprotocol"]}),50
        )
        self.assertEqual(
            len({x["source_posting_id"] for x in jj["sources"]["justjoinit"]}),150
        )


if __name__ == "__main__":
    unittest.main()
