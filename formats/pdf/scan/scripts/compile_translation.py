"""Expand model-authored region decisions into the existing raster manifest.

No translation, grouping or passing review is inferred by this utility.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from contracts import validate_manifest


def compile_translation(extraction: dict, draft: dict, decisions: dict) -> dict:
    if draft['source_sha256'] != extraction['source_sha256']:
        raise ValueError('Draft does not match extraction')
    if decisions['source_sha256'] != extraction['source_sha256']:
        raise ValueError('Translation decisions do not match extraction')
    manifest = {k: copy.deepcopy(extraction[k]) for k in
                ('source', 'source_sha256', 'selected_pages', 'pages', 'source_lines')}
    manifest['target_language'] = decisions['target_language']
    manifest['source_lines'].extend(copy.deepcopy(decisions.get('supplements', [])))
    lines = {line['id']: line for line in manifest['source_lines']}
    groups = {group['id']: group for group in draft['groups']}
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
            block['clean_boxes'] = item.get('clean_boxes', boxes)
            block['background'] = item.get('background', 'sample')
        blocks.append(block)
    if len({b['id'] for b in blocks}) != len(blocks):
        raise ValueError('Duplicate region IDs')
    manifest['blocks'] = blocks
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
