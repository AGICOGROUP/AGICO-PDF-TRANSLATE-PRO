"""Expand model-authored region decisions into the existing raster manifest.

No translation, grouping or passing review is inferred by this utility.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from contracts import validate_manifest


def default_cleanup_box(box: list, page: dict, image: Image.Image | None,
                        protected: list[list] = ()) -> list:
    """Cover clipped OCR edge pixels without extending across a nearby rule.

    Two pixels at 200 dpi is a physical 0.72 pt margin. Explicit visual cleanup
    geometry remains authoritative; this helper only supplies the OCR default.
    """
    if image is None:
        # Without actual pixels, a safe margin cannot be checked against nearby
        # rules/graphics. Retain the legacy envelope for carrier/metadata jobs.
        return list(box)
    margin = max(1, math.ceil(float(page.get('dpi', 200)) / 100))
    width, height = int(page['pixel_width']), int(page['pixel_height'])
    x0, y0, x1, y1 = map(float, box)
    left, top = max(0, math.floor(x0) - margin), max(0, math.floor(y0) - margin)
    right, bottom = min(width, math.ceil(x1) + margin), min(height, math.ceil(y1) + margin)
    if image is not None:
        ink = np.asarray(image.crop((left, top, right, bottom)))
        if ink.size and np.median(np.concatenate((ink[0], ink[-1], ink[:, 0], ink[:, -1]))) >= 180:
            # A rule must span the padded crop, not merely the glyph envelope:
            # the latter would mistake a solid glyph stroke for a table border.
            horizontal = np.flatnonzero((ink < 150).mean(axis=1) >= .9) + top
            vertical = np.flatnonzero((ink < 150).mean(axis=0) >= .9) + left
            above = horizontal[horizontal < y0]
            below = horizontal[horizontal >= y1]
            before = vertical[vertical < x0]
            after = vertical[vertical >= x1]
            if len(above): top = max(top, int(above[-1]) + 1)
            if len(below): bottom = min(bottom, int(below[0]))
            if len(before): left = max(left, int(before[-1]) + 1)
            if len(after): right = min(right, int(after[0]))
    for px0, py0, px1, py1 in protected:
        if min(right, px1) <= max(left, px0) or min(bottom, py1) <= max(top, py0):
            continue
        # Only constrain the added margin. Existing overlapping OCR envelopes
        # still need source-based, explicit cleanup; do not guess glyph ownership.
        if x1 <= px0: right = min(right, px0)
        elif x0 >= px1: left = max(left, px1)
        elif y1 <= py0: bottom = min(bottom, py0)
        elif y0 >= py1: top = max(top, py1)
    return [left, top, right, bottom]


def compile_translation(extraction: dict, draft: dict, decisions: dict) -> dict:
    if draft['source_sha256'] != extraction['source_sha256']:
        raise ValueError('Draft does not match extraction')
    if decisions['source_sha256'] != extraction['source_sha256']:
        raise ValueError('Translation decisions do not match extraction')
    manifest = {k: copy.deepcopy(extraction[k]) for k in
                ('source', 'source_sha256', 'selected_pages', 'pages', 'source_lines')}
    manifest['target_language'] = decisions['target_language']
    recorded_languages = [value for value in (extraction.get('source_language'),
                                               decisions.get('source_language')) if value is not None]
    if any(not isinstance(value, str) or not value.strip() for value in recorded_languages):
        raise ValueError('Invalid source language; use a nonempty language code')
    if len({value.strip().lower().replace('_', '-').split('-')[0] for value in recorded_languages}) > 1:
        raise ValueError('Conflicting source language in extraction and decisions')
    if recorded_languages:
        manifest['source_language'] = recorded_languages[-1].strip()
    manifest['source_lines'].extend(copy.deepcopy(decisions.get('supplements', [])))
    lines = {line['id']: line for line in manifest['source_lines']}
    groups = {group['id']: group for group in draft['groups']}
    pages = {page['source_page']: page for page in manifest['pages']}
    protected_by_page = {number: list(page.get('protected_boxes', [])) for number, page in pages.items()}
    dispositions = decisions.get('candidate_dispositions', {})
    for number, page in pages.items():
        for candidate in page.get('ocr_review_candidates', []):
            if dispositions.get(candidate.get('id'), {}).get('disposition') == 'preserved_ink':
                protected_by_page[number].append(candidate['box'])
    for item in decisions['regions']:
        if 'preserve_reason' in item:
            group = groups[item['group']] if 'group' in item else {}
            for line_id in item.get('ids', group.get('line_ids', [])):
                line = lines[line_id]
                protected_by_page[line['page']].append(line['box'])
    cleanup_images: dict[int, Image.Image | None] = {}
    blocks = []
    for index, item in enumerate(decisions['regions'], 1):
        # A draft group is optional; explicit IDs allow corrected merges/splits.
        group = groups[item['group']] if 'group' in item else {}
        ids = item.get('ids', group.get('line_ids'))
        if not ids:
            raise ValueError('Each region needs group or ids')
        owned = [lines[i] for i in ids]
        if len({line['page'] for line in owned}) != 1:
            raise ValueError('A region cannot span source pages')
        boxes = [line['box'] for line in owned]
        union = [min(b[0] for b in boxes), min(b[1] for b in boxes),
                 max(b[2] for b in boxes), max(b[3] for b in boxes)]
        preserve = 'preserve_reason' in item
        role = item.get('role', group.get('role', 'body'))
        style = {**decisions.get('styles', {}).get(role, {}), **item.get('style', {})}
        if set(style) - {'max_font', 'min_font', 'leading_ratio', 'bold', 'align', 'valign', 'color'}:
            raise ValueError('Style may contain only typography fields')
        block = {
            'id': item.get('id', group.get('id', f'region-{index:04d}')),
            'page': owned[0]['page'], 'source_line_ids': ids,
            'source': item.get('source', ' '.join(line['text'] for line in owned)),
            'translation': item['preserve_reason'] if preserve else item['translation'],
            'role': role, 'status': 'preserve_confirm' if preserve else 'translated',
            'action': 'preserve' if preserve else 'replace',
            'box': item.get('box', group.get('box') if 'ids' not in item else None) or union,
            'rotation': owned[0].get('rotation', 0),
            'max_font': 12, 'min_font': 6, 'leading_ratio': 1.12,
            'bold': role in ('title', 'heading', 'subheading'),
            'align': 'left', 'valign': 'top', 'color': [0, 0, 0], **style,
        }
        if not str(block['translation']).strip():
            raise ValueError('Translation or preservation reason cannot be empty')
        if not preserve:
            if 'preserve_colored_ink' in item:
                block['preserve_colored_ink'] = item['preserve_colored_ink']
            if 'clean_boxes' in item:
                block['clean_boxes'] = item['clean_boxes']
            else:
                page_number = owned[0]['page']
                page = pages[page_number]
                if page_number not in cleanup_images:
                    render = Path(page.get('render_path', ''))
                    if render.is_file():
                        with Image.open(render) as opened:
                            cleanup_images[page_number] = opened.convert('L')
                    else:
                        cleanup_images[page_number] = None
                block['clean_boxes'] = [
                    list(line['box']) if line.get('origin') == 'visual_supplement' else
                    default_cleanup_box(line['box'], page, cleanup_images[page_number],
                                        protected_by_page[page_number])
                    for line in owned]
            block['background'] = item.get('background', 'sample')
        blocks.append(block)
    if len({b['id'] for b in blocks}) != len(blocks):
        raise ValueError('Duplicate region IDs')
    manifest['blocks'] = blocks
    for image in cleanup_images.values():
        if image is not None:
            image.close()
    # The manifest is rebuilt from the extraction, so candidate dispositions recorded earlier
    # (resolve_scan_candidates --apply) have to be carried over or the build gate would fire on
    # candidates that were already inspected.
    if decisions.get('candidate_dispositions'):
        manifest['candidate_dispositions'] = copy.deepcopy(decisions['candidate_dispositions'])
    validate_manifest(manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extraction', required=True, type=Path)
    parser.add_argument('--draft', required=True, type=Path)
    parser.add_argument('--decisions', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    manifest = compile_translation(read(args.extraction), read(args.draft), read(args.decisions))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'blocks': len(manifest['blocks']), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
