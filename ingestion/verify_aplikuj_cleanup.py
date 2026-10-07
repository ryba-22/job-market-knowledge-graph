"""Verify on-disk Aplikuj local cache scope and manifest provenance."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from .aplikuj_it_scope import is_technical_it
from .clean_aplikuj_cache import read_gz
from .run_file_backed_plan import _manifest_ok


def verify(root: Path = Path('.local-crawl/scale-04')) -> dict:
    checked = 0
    retained = 0
    excluded = 0
    invalid = []
    for path in sorted((root / 'aplikuj').glob('*/manifest.json')):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        corpus_path = path.with_name('corpus.jsonl.gz')
        raw_path = Path(manifest['raw_archive_location'])
        if not _manifest_ok(path):
            invalid.append(f'{path}: manifest accounting')
            continue
        for file, field in ((corpus_path, 'corpus'), (raw_path, 'raw_archive')):
            packed = file.read_bytes()
            unpacked = gzip.decompress(packed)
            if hashlib.sha256(packed).hexdigest() != manifest[field]['compressed_sha256']:
                invalid.append(f'{file}: compressed hash')
            if hashlib.sha256(unpacked).hexdigest() != manifest[field]['uncompressed_sha256']:
                invalid.append(f'{file}: uncompressed hash')
        rows = read_gz(corpus_path)
        raw = read_gz(raw_path)
        if len(rows) != manifest['postings'] or len(raw) != manifest['raw_archive']['rows']:
            invalid.append(f'{path}: row count')
        if any(not is_technical_it(r['title'], (r.get('source_projection') or {}).get('industry')) for r in rows):
            invalid.append(f'{path}: non-IT in corpus')
        if {str(x['source_posting_id']) for x in rows} != {str(x['source_posting_id']) for x in raw}:
            invalid.append(f'{path}: corpus/raw identity mismatch')
        checked += 1
        retained += len(rows)
        excluded += int(manifest.get('excluded_non_it', 0))
    result = {'verified_chunks': checked, 'retained_it': retained, 'excluded_non_it': excluded, 'errors': invalid}
    return result


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
