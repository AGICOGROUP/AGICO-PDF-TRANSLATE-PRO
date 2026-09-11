"""Conservative translation units; proposals never approve source cleanup."""
import copy
import hashlib
import json
import math

import pymupdf


def inventory_binding(inventory):
    content = {k: inventory.get(k) for k in ('source_sha256', 'request', 'pages', 'records', 'placements')}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def propose_units(inventory):
    records = inventory['records']
    placements = inventory.get('placements', {})
    pages, groups = [], []
    for page in sorted({r['page'] for r in records}):
        rows = sorted((r for r in records if r['page'] == page),
                      key=lambda r: (r['bbox'][1], r['bbox'][0], r['id']))
        pages.append({'page': page, 'text': '\n'.join(r['source'] for r in rows),
                      'source_ids': [r['id'] for r in rows]})
        group = []
        for record in rows:
            if record['status'] != 'pending':
                group = []
                continue
            join = False
            if group and record.get('kind', 'native') == 'native' and not record.get('rotation', 0):
                previous = group[-1]
                a, b = pymupdf.Rect(previous['bbox']), pymupdf.Rect(record['bbox'])
                h = min(a.height, b.height)
                ca = placements.get(previous['id'], {}).get('cell_bbox')
                cb = placements.get(record['id'], {}).get('cell_bbox')
                union = pymupdf.Rect(group[0]['bbox'])
                for member in group[1:] + [record]:
                    union |= pymupdf.Rect(member['bbox'])
                member_ids = {r['id'] for r in group} | {record['id']}
                join = (previous.get('kind', 'native') == 'native'
                        and not previous.get('rotation', 0) and ca == cb
                        and previous.get('color', 0) == record.get('color', 0)
                        and h > 0 and max(a.height, b.height) <= h * 1.4
                        and abs((a.y0 + a.y1 - b.y0 - b.y1) / 2) <= .25 * h
                        and -.1 * h <= b.x0 - a.x1 <= 3 * h
                        and not any(union.intersects(pymupdf.Rect(other['bbox']))
                                    for other in rows if other['id'] not in member_ids))
            if join:
                group.append(record)
            else:
                group = [record]
                groups.append(group)
    units = []
    for group in groups:
        first = group[0]
        ids = [r['id'] for r in group]
        box = pymupdf.Rect(first['bbox'])
        for r in group[1:]:
            box |= pymupdf.Rect(r['bbox'])
        cell = placements.get(first['id'], {}).get('cell_bbox')
        # The source envelope is the conservative proposal. Wider reflow is an
        # explicit reviewed adjustment, not automatic use of a shared cell.
        units.append({'id': 'u-' + hashlib.sha256('|'.join(ids).encode()).hexdigest()[:12],
                      'page': first['page'], 'member_ids': ids,
                      'source': ' '.join(r['source'] for r in group),
                      'translation': '', 'review_note': '',
                      'kind': first.get('kind', 'native'),
                      'rotation': first.get('rotation', 0), 'layout_box': list(box),
                      **({'cell_bbox': cell} if cell else {})})
    return {'schema_version': 1, 'source_sha256': inventory['source_sha256'],
            'request': inventory.get('request'), 'inventory_sha256': inventory_binding(inventory),
            'pages': pages, 'units': units}


def merge_unit_translations(inventory, packet, submitted):
    if (submitted.get('inventory_sha256') != inventory_binding(inventory)
            or submitted.get('source_sha256') != inventory['source_sha256']
            or submitted.get('request') != inventory.get('request')):
        raise ValueError('translation units are stale or belong to another request; export again')
    definitions = {u['id']: u for u in propose_units(inventory)['units']}
    result = copy.deepcopy(packet)
    targets = {r['id']: r for r in result['records']}
    seen = set()
    changes = submitted.get('units')
    if not isinstance(changes, list) or not changes:
        raise ValueError('submit a nonempty units list')
    for change in changes:
        definition = definitions.get(change.get('id'))
        if (not definition or any(change.get(k) != definition[k] for k in ('source', 'member_ids', 'page'))
                or seen.intersection(definition['member_ids'])):
            raise ValueError('unknown, changed or duplicate translation unit')
        ids = definition['member_ids']
        seen.update(ids)
        translation = change.get('translation')
        note = change.get('review_note', '')
        if not isinstance(translation, str) or not translation.strip():
            raise ValueError('unit translation is blank; submit only completed units')
        if len(ids) > 1 and (not isinstance(note, str) or not note.strip()):
            raise ValueError('review_note must confirm the grouped phrase context')
        box = change.get('layout_box', definition['layout_box'])
        if (not isinstance(box, list) or len(box) != 4
                or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in box)
                or box[2] <= box[0] or box[3] <= box[1]):
            raise ValueError('invalid unit layout_box')
        if definition.get('cell_bbox') and not pymupdf.Rect(definition['cell_bbox']).contains(pymupdf.Rect(box)):
            raise ValueError('unit layout crosses its table cell; review the placement')
        for index, record_id in enumerate(ids):
            target = targets.get(record_id)
            if target is None or (target.get('status') != 'pending' and target.get('unit_id') != change['id']):
                raise ValueError('unit conflicts with existing packet decisions; retain or edit that packet explicitly')
            target['unit_id'] = change['id']
            target['review_note'] = note
            if index == 0:
                for key in ('role', 'cover_boxes', 'cover_review', 'rotation'):
                    if key in change:
                        target[key] = copy.deepcopy(change[key])
                target.update(status='translated', translation=translation.strip(), layout_box=box)
            else:
                target.update(status='merged', translation='', merged_into=ids[0])
    return result, len(changes)
