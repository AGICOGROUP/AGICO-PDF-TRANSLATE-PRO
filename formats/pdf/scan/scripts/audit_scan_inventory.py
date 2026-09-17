"""Audit all selected source rasters against an existing inventory, without OCR."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from PIL import Image

from extract_scan import candidate_is_covered, sha256_file, uncovered_text_candidates


def audit_inventory(manifest: dict) -> tuple[dict, list[dict]]:
    updated = deepcopy(manifest)
    additions = []
    selected = set(manifest['selected_pages'])
    pages = {p['source_page']: p for p in updated['pages']}
    if not selected.issubset(pages):
        raise ValueError('missing selected source page in inventory audit')
    for number in manifest['selected_pages']:
        page = pages[number]
        path = Path(page['render_path'])
        digest = sha256_file(path)
        if page.get('render_sha256') and page['render_sha256'].lower() != digest:
            raise ValueError(f'source render hash mismatch on page {number}')
        boxes = [line['box'] for line in manifest['source_lines'] if line['page'] == number]
        candidates = page.setdefault('ocr_review_candidates', [])
        with Image.open(path) as image:
            gaps = uncovered_text_candidates(image, boxes)
        for box in gaps:
            if any(candidate_is_covered(box, old['box']) for old in candidates):
                continue
            # Geometry and source pixels bind the ID; changing the sort order
            # must not transfer a previous non-text decision to a new region.
            key = hashlib.sha256(json.dumps([number, digest, box]).encode()).hexdigest()[:16]
            candidate = {'id': f'p{number:02d}-ink-{key}', 'box': box,
                         'reason': 'uncovered_ink', 'ocr_attempts': 0}
            candidates.append(candidate)
            additions.append({'page': number, **candidate})
    return updated, additions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True, help='Enriched manifest JSON; may replace input')
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    updated, additions = audit_inventory(manifest)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.audit.tmp.json')
    temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(output)
    print(json.dumps({'selected_pages': len(manifest['selected_pages']),
                      'new_candidates': len(additions), 'output': str(output.resolve())}))


if __name__ == '__main__':
    main()
