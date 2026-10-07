from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
INV=ROOT/'data'/'inventories'/'scale-04'

class Scale04FrozenInventoryTest(unittest.TestCase):
    def test_inventory_contract(self):
        manifest=json.loads((INV/'manifest.json').read_text(encoding='utf-8'))
        compressed=(INV/'inventory.jsonl.gz').read_bytes()
        raw=gzip.decompress(compressed)
        self.assertEqual(hashlib.sha256(compressed).hexdigest(),manifest['compressed_sha256'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest['uncompressed_sha256'])
        rows=[json.loads(line) for line in raw.decode('utf-8').split('\n') if line]
        self.assertEqual(len(rows),618)
        self.assertEqual(manifest['sources'],{
            'aplikuj':{'discoverable':522,'known':0,'unknown':522},
            'itleaders':{'discoverable':10,'known':0,'unknown':10},
            'michaelpage':{'discoverable':86,'known':0,'unknown':86},
        })
        self.assertEqual(manifest['unknown_total'],618)

    def test_chunks_cover_inventory_once(self):
        plan=json.loads((INV/'chunks.json').read_text(encoding='utf-8'))
        self.assertEqual(plan['unknown_total'],618)
        self.assertEqual(plan['chunks_by_source'],{'aplikuj':3,'itleaders':1,'michaelpage':1})
        self.assertEqual(len(plan['chunks']),5)
        seen=set()
        for chunk in plan['chunks']:
            self.assertEqual(chunk['count'],len(chunk['rows']))
            for row in chunk['rows']:
                key=(row['source'],row['source_posting_id'])
                self.assertNotIn(key,seen)
                seen.add(key)
        self.assertEqual(len(seen),618)

if __name__=='__main__':
    unittest.main()
