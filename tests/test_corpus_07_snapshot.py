from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'data' / 'corpora' / 'corpus-07'


class Corpus07SnapshotTest(unittest.TestCase):
    def test_frozen_pilot_contract(self):
        manifest = json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8'))
        compressed = (CORPUS / 'corpus.jsonl.gz').read_bytes()
        raw = gzip.decompress(compressed)
        self.assertEqual(hashlib.sha256(compressed).hexdigest(), manifest['compressed_sha256'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest['uncompressed_sha256'])
        rows = [json.loads(line) for line in raw.decode('utf-8').split('\n') if line]
        self.assertEqual(len(rows), 2583)
        self.assertEqual(manifest['by_source'], {
            'bulldogjob': 463,
            'justjoinit': 650,
            'nofluffjobs': 650,
            'pracuj': 120,
            'rocketjobs': 650,
            'theprotocol': 50,
        })


if __name__ == '__main__':
    unittest.main()
