"""Cached tiled OCR and conservative local-cover screening for CAD drawings.

OCR proposes regions; a translator must inspect source pixels before approving
a text-only white-background cover. Geometry screening alone is not approval.
"""
from pathlib import Path
import hashlib
import json
import time

import pymupdf


def overlap(a, b):
    a, b = pymupdf.Rect(a), pymupdf.Rect(b)
    return (a & b).get_area() / max(1e-6, min(a.get_area(), b.get_area()))


def drawing_index(page):
    """Index path extents once; avoid millions of Rect allocations per sheet."""
    import numpy as np
    paths = page.get_drawings()
    bounds = []
    for path in paths:
        pad = max(.15, float(path.get('width') or 0) / 2)
        bounds.append(list(pymupdf.Rect(path['rect']) + (-pad, -pad, pad, pad)))
    return {'paths': paths, 'bounds': np.asarray(bounds).reshape((-1, 4))}


def segment_intersects(a, b, rect):
    lo, hi = 0., 1.
    for start, delta, lower, upper in ((a.x, b.x-a.x, rect.x0, rect.x1), (a.y, b.y-a.y, rect.y0, rect.y1)):
        if abs(delta) < 1e-9:
            if start < lower or start > upper:
                return False
        else:
            t0, t1 = sorted(((lower-start)/delta, (upper-start)/delta))
            lo, hi = max(lo, t0), min(hi, t1)
            if lo > hi:
                return False
    return True


def cover_conflicts(page, box, drawings=None):
    rect = pymupdf.Rect(box)
    if rect.is_empty or not page.rect.contains(rect):
        return ['outside_page']
    conflicts = []
    if isinstance(drawings, dict):
        bounds = drawings['bounds']
        selected = ((bounds[:, 0] < rect.x1) & (bounds[:, 2] > rect.x0) &
                    (bounds[:, 1] < rect.y1) & (bounds[:, 3] > rect.y0)).nonzero()[0]
        paths = ((int(i), drawings['paths'][i]) for i in selected)
    else:
        paths = enumerate(drawings if drawings is not None else page.get_drawings())
    for index, path in paths:
        bounds = pymupdf.Rect(path['rect'])
        # Include zero-height pipe segments and stroke width in the intersection.
        pad = max(.15, float(path.get('width') or 0) / 2)
        ink = bounds + (-pad, -pad, pad, pad)
        if not rect.intersects(ink):
            continue
        if path.get('fill') is not None and tuple(path['fill']) != (1., 1., 1.):
            conflicts.append(f'filled_region:{index}')
            continue
        expanded = rect + (-pad, -pad, pad, pad)
        for item in path['items']:
            if item[0] == 'l':
                segments = [(item[1], item[2])]
            elif item[0] in ('re', 'qu'):
                shape = item[1]
                corners = [shape.tl, shape.tr, shape.br, shape.bl] if item[0] == 're' else [shape.ul, shape.ur, shape.lr, shape.ll]
                if rect.contains(pymupdf.Rect(min(p.x for p in corners), min(p.y for p in corners), max(p.x for p in corners), max(p.y for p in corners))):
                    continue
                segments = list(zip(corners, corners[1:] + corners[:1]))
            else:
                # Curves may be symbols or font outlines; require a smaller
                # isolated box rather than guessing which curve is text.
                curve = pymupdf.Rect(min(p.x for p in item[1:]), min(p.y for p in item[1:]), max(p.x for p in item[1:]), max(p.y for p in item[1:]))
                if expanded.intersects(curve):
                    conflicts.append(f'curve:{index}')
                continue
            for a, b in segments:
                if not segment_intersects(a, b, expanded):
                    continue
                if item[0] != 'l':
                    conflicts.append(f'symbol_or_frame:{index}')
                elif not rect.contains(a) or not rect.contains(b):
                    conflicts.append(f'crossing_path:{index}')
    for info in page.get_image_info():
        if rect.intersects(pymupdf.Rect(info['bbox'])):
            conflicts.append('image')
    return conflicts


def extract_outline_records(document, job_dir, source_hash, native, engine=None, dpi=150):
    """Render bounded tiles, checkpoint each OCR result, and deduplicate overlaps."""
    import numpy as np
    from PIL import Image

    cache = Path(job_dir) / 'ocr-cache'
    cache.mkdir(exist_ok=True)
    started = time.perf_counter()
    output, hits, misses = [], 0, 0
    scale, tile_pixels, overlap_pixels = dpi / 72, 1536, 128
    step = (tile_pixels - overlap_pixels) / scale
    for page_index, page in enumerate(document):
        proposals = []
        for row in range(max(1, int((page.rect.height * scale - overlap_pixels - 1) // (tile_pixels - overlap_pixels)) + 1)):
            for col in range(max(1, int((page.rect.width * scale - overlap_pixels - 1) // (tile_pixels - overlap_pixels)) + 1)):
                clip = pymupdf.Rect(col * step, row * step, col * step + tile_pixels / scale, row * step + tile_pixels / scale) & page.rect
                key = hashlib.sha256(f'{source_hash}:ocr-v1:{page_index}:{dpi}:{list(clip)}'.encode()).hexdigest()
                path = cache / f'{key}.json'
                records = None
                if path.exists():
                    try:
                        records = json.loads(path.read_text(encoding='utf-8'))
                    except (ValueError, OSError):
                        pass
                if records is not None:
                    hits += 1
                else:
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
                    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                    # Darken faint CAD strokes without blurring fine labels.
                    image = image.point([round(255 * (v / 255) ** 2) for v in range(256)] * 3)
                    if engine is None:
                        from rapidocr_onnxruntime import RapidOCR
                        engine = RapidOCR()
                    result, _ = engine(np.asarray(image))
                    records = []
                    for corners, text, score in result or []:
                        xs, ys = zip(*corners)
                        records.append({'source': text, 'confidence': float(score),
                                        'bbox': [(min(xs) + pix.x) / scale, (min(ys) + pix.y) / scale,
                                                 (max(xs) + pix.x) / scale, (max(ys) + pix.y) / scale]})
                    temporary = path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
                    temporary.replace(path)
                    misses += 1
                    print(json.dumps({'stage': 'ocr-tile', 'page': page_index + 1, 'row': row, 'column': col}), flush=True)
                proposals.extend(records)
        retained = []
        for item in sorted(proposals, key=lambda v: -v['confidence']):
            # A small native motor token must not hide an entire OCR label.
            area = max(1e-6, pymupdf.Rect(item['bbox']).get_area())
            if any((pymupdf.Rect(item['bbox']) & pymupdf.Rect(r['bbox'])).get_area() / area > .7 for r in native if r['page'] == page_index):
                continue
            if any(overlap(item['bbox'], r['bbox']) > .6 for r in retained):
                continue
            retained.append(item)
        for index, item in enumerate(sorted(retained, key=lambda v: (v['bbox'][1], v['bbox'][0])), 1):
            item.update(id=f'p{page_index+1:04d}-o{index:05d}', page=page_index,
                        kind='outline', status='pending', color=0, rotation=0,
                        font_size=round(max(4, (item['bbox'][3] - item['bbox'][1]) * .8), 3))
            output.append(item)
        print(json.dumps({'stage': 'ocr', 'page': page_index + 1, 'regions': len(retained), 'cache_hits': hits, 'tiles_run': misses}), flush=True)
    return output, {'seconds': round(time.perf_counter() - started, 3), 'cache_hits': hits, 'tiles_run': misses}
