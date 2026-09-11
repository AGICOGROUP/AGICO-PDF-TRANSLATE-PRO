"""Batch CAD placement proposals and source/candidate review artifacts.

Geometry and OCR propose work; neither grants visual or semantic approval.
"""
import hashlib
import html
import json
import time
from pathlib import Path

import pymupdf
from cad_cache import LazyOCR, ocr_identity, page_fingerprint

# Bump when review rendering or interpretation changes; OCR has its own version.
REVIEW_CACHE_VERSION = 4


def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def cell_proposals(page, records):
    horizontal, vertical = [], []
    for path in page.get_drawings():
        for item in path['items']:
            segments = []
            if item[0] == 'l':
                segments = [(item[1], item[2])]
            elif item[0] == 're':
                rect = item[1]
                segments = [(rect.tl, rect.tr), (rect.tr, rect.br),
                            (rect.br, rect.bl), (rect.bl, rect.tl)]
            for a, b in segments:
                if abs(a.y-b.y) < .15 and abs(a.x-b.x) > 20:
                    horizontal.append((a.y, min(a.x,b.x), max(a.x,b.x)))
                if abs(a.x-b.x) < .15 and abs(a.y-b.y) > 12:
                    vertical.append((a.x, min(a.y,b.y), max(a.y,b.y)))
    result = {}
    for record in records:
        rect = pymupdf.Rect(record['bbox'])
        cx, cy = (rect.x0+rect.x1)/2, (rect.y0+rect.y1)/2
        top = sorted((v for v in horizontal if v[0] < cy and v[1] <= cx <= v[2]), reverse=True)
        bottom = sorted(v for v in horizontal if v[0] > cy and v[1] <= cx <= v[2])
        if not top or not bottom:
            continue
        y0, y1 = top[0][0], bottom[0][0]
        sides = [v for v in vertical if v[1] <= y0+.3 and v[2] >= y1-.3]
        left = [v[0] for v in sides if v[0] < cx]
        right = [v[0] for v in sides if v[0] > cx]
        if not left or not right:
            continue
        x0, x1 = max(left), min(right)
        if any(v[1] > x0+.3 or v[2] < x1-.3 for v in (top[0], bottom[0])):
            continue
        # Exclude the sheet frame / large process equipment enclosure.
        if y1-y0 > max(100, rect.height*6) or x1-x0 > max(600, rect.width*6):
            continue
        cell = pymupdf.Rect(x0,y0,x1,y1)
        members = [r['id'] for r in records if cell.contains((pymupdf.Rect(r['bbox']).tl + pymupdf.Rect(r['bbox']).br)/2)]
        inset = min(1.5, cell.height*.08, cell.width*.08)
        result[record['id']] = {'cell_bbox': list(cell),
            'layout_box': list(cell + (inset,inset,-inset,-inset)),
            'members': members, 'source_overflows_cell': not cell.contains(rect)}
        inner = cell + (inset,inset,-inset,-inset)
        if len(members) > 1:
            # Separate fields share a cell, not a text origin. Reserve neighbours'
            # source extents; overlapping OCR fragments need contextual review.
            layout = pymupdf.Rect(inner)
            for other in records:
                if other['id'] not in members or other['id'] == record['id']:
                    continue
                neighbour = pymupdf.Rect(other['bbox'])
                if rect.intersects(neighbour):
                    layout = rect & inner
                    break
                if neighbour.y1 <= rect.y0:
                    layout.y0 = max(layout.y0, (neighbour.y1 + rect.y0) / 2)
                elif neighbour.y0 >= rect.y1:
                    layout.y1 = min(layout.y1, (neighbour.y0 + rect.y1) / 2)
                elif neighbour.x1 <= rect.x0:
                    layout.x0 = max(layout.x0, (neighbour.x1 + rect.x0) / 2)
                elif neighbour.x0 >= rect.x1:
                    layout.x1 = min(layout.x1, (neighbour.x0 + rect.x1) / 2)
            if not layout.is_empty:
                result[record['id']]['layout_box'] = list(layout)
        if len(members) == 1 and inner.contains(rect):
            result[record['id']]['cover_boxes'] = [list(inner)]
    return result


def merge_supplement(existing, proposals, native, page_index):
    added = []
    for item in sorted(proposals, key=lambda r: (r['bbox'][1], r['bbox'][0])):
        rect = pymupdf.Rect(item['bbox'])
        # Coverage must be relative to the new label, not the smaller box:
        # a tiny equipment tag cannot account for a whole description.
        if any((rect & pymupdf.Rect(r['bbox'])).get_area()/max(rect.get_area(),1e-6) > .6
               for r in existing+added if r.get('page',page_index) == page_index):
            continue
        if any((rect & pymupdf.Rect(r['bbox'])).get_area()/max(rect.get_area(),1e-6) > .7
               for r in native if r['page'] == page_index):
            continue
        box = item['bbox']
        added.append(dict(item, id=f'p{page_index+1:04d}-u{len(added)+1:05d}',
            page=page_index, kind='outline', status='pending', color=0,
            rotation=0, font_size=round(max(4,(box[3]-box[1])*.8),3)))
    return added


def page_ocr(page, source_hash, cache, engine=None):
    """Different-scale full-page pass complements tile boundaries; bounded at 7200px."""
    import numpy as np
    cache.mkdir(parents=True, exist_ok=True)
    scale = min(2., 7200/max(page.rect.width, page.rect.height))
    key = hashlib.sha256(f'{page_fingerprint(page)}:{ocr_identity()}:full-page-v2:{scale}'.encode()).hexdigest()
    path = cache / (key+'.json')
    if path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8')), True
        except (ValueError, OSError):
            pass
    if engine is None:
        engine = LazyOCR()
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale,scale), alpha=False)
    pixels = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
    found, _ = engine(pixels)
    records = []
    for corners, text, score in found or []:
        xs, ys = zip(*corners)
        rect = pymupdf.Rect((min(xs)+pix.x)/scale,(min(ys)+pix.y)/scale,
                           (max(xs)+pix.x)/scale,(max(ys)+pix.y)/scale)
        records.append(dict(source=text, confidence=float(score),
                            bbox=list(rect * page.derotation_matrix)))
    save_json(path, records)
    return records, False


def _valid_artifacts(destination, artifacts):
    return isinstance(artifacts, dict) and bool(artifacts) and all(
        Path(name).name == name and (destination/name).is_file() and
        hashlib.sha256((destination/name).read_bytes()).hexdigest() == digest
        for name, digest in artifacts.items())


def review_bundle(source, destination, records, candidate=None, candidate_hash=None, residual_script=None):
    """One HTML index: complete pages and side-by-side crops, plus bound OCR findings."""
    destination.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    source_hash = hashlib.sha256(Path(source).read_bytes()).hexdigest()
    actual_candidate_hash = hashlib.sha256(Path(candidate).read_bytes()).hexdigest() if candidate else None
    binding = hashlib.sha256(json.dumps([REVIEW_CACHE_VERSION, source_hash, actual_candidate_hash, candidate_hash,
                                        records, residual_script, ocr_identity() if residual_script else None,
                                        pymupdf.VersionBind], sort_keys=True).encode()).hexdigest()
    report_path = destination/'review-report.json'
    if report_path.exists():
        try:
            cached = json.loads(report_path.read_text(encoding='utf-8'))
            if cached.get('binding') == binding and _valid_artifacts(destination, cached.get('artifacts')):
                return dict(cached, cache_hit=True, reused_pages=cached['pages'], rebuilt_pages=[],
                            seconds=round(time.perf_counter()-started,3))
        except (ValueError, OSError, TypeError, KeyError):
            pass
    report = {'candidate_sha256': candidate_hash, 'residual_script': residual_script,
              'residual_candidates': [], 'pages': [], 'regions': [],
              'reused_pages': [], 'rebuilt_pages': []}
    artifacts = {}
    body = ['<!doctype html><meta charset="utf-8"><title>CAD review</title>',
            '<style>body{font-family:sans-serif} img{max-width:48%;vertical-align:top} section{border-bottom:1px solid #aaa;padding:12px} code{white-space:pre-wrap}</style>']
    with pymupdf.open(source) as original:
        translated = pymupdf.open(candidate) if candidate else None
        try:
            engine = LazyOCR()
            if translated is not None and len(translated) != len(original):
                raise ValueError('Source and candidate page counts differ')
            for page_index, page in enumerate(original):
                local_records = [(i, r) for i, r in enumerate(records) if r.get('page',0) == page_index]
                page_binding = hashlib.sha256(json.dumps([
                    REVIEW_CACHE_VERSION, pymupdf.VersionBind, page_fingerprint(page),
                    page_fingerprint(translated[page_index]) if translated else None,
                    local_records, residual_script, ocr_identity() if residual_script else None
                ], sort_keys=True).encode()).hexdigest()
                page_report_path = destination/f'review-page-{page_index+1}.json'
                try:
                    envelope = json.loads(page_report_path.read_text(encoding='utf-8'))
                    saved = envelope['payload']
                    digest = hashlib.sha256(json.dumps(saved, sort_keys=True).encode()).hexdigest()
                    if envelope.get('sha256') == digest and saved.get('binding') == page_binding and _valid_artifacts(destination, saved.get('artifacts')):
                        body.extend(saved['body'])
                        report['pages'].append(page_index)
                        report['regions'].extend(saved['regions'])
                        report['residual_candidates'].extend(saved['residual_candidates'])
                        report['reused_pages'].append(page_index)
                        artifacts.update(saved['artifacts'])
                        artifacts[page_report_path.name] = hashlib.sha256(page_report_path.read_bytes()).hexdigest()
                        continue
                except (ValueError, OSError, KeyError, TypeError):
                    pass
                body_start, region_start, residual_start = len(body), len(report['regions']), len(report['residual_candidates'])
                page_artifacts = []
                report['rebuilt_pages'].append(page_index)
                # Parse each vector-heavy CAD page once, then render all crops.
                source_display = page.get_displaylist()
                target_display = translated[page_index].get_displaylist() if translated else None
                source_png = destination/f'source-{page_index+1}.png'
                source_display.get_pixmap(matrix=pymupdf.Matrix(1,1),alpha=False).save(source_png)
                page_artifacts.append(source_png)
                body.append(f'<h2>Page {page_index+1}</h2><a href="{source_png.name}"><img src="{source_png.name}"></a>')
                report['pages'].append(page_index)
                if translated:
                    target_png = destination/f'candidate-{page_index+1}.png'
                    target_display.get_pixmap(matrix=pymupdf.Matrix(1,1),alpha=False).save(target_png)
                    page_artifacts.append(target_png)
                    body.append(f'<a href="{target_png.name}"><img src="{target_png.name}"></a>')
                    if residual_script:
                        found, _ = page_ocr(translated[page_index], candidate_hash, destination/'ocr-cache', engine)
                        for r in found:
                            match = any('\u4e00' <= c <= '\u9fff' for c in r['source']) if residual_script == 'cjk' else any(c.isascii() and c.isalpha() for c in r['source'])
                            if match:
                                report['residual_candidates'].append(dict(r,page=page_index))
                for number, record in local_records:
                    rect = pymupdf.Rect(record['bbox'])
                    if record.get('layout_box'):
                        rect |= pymupdf.Rect(record['layout_box'])
                    for box in record.get('cover_boxes',[]):
                        rect |= pymupdf.Rect(box)
                    rect = ((rect+(-8,-8,8,8)) * page.rotation_matrix) & page.rect
                    if rect.is_empty:
                        continue
                    name=f'region-{number}'
                    source_display.get_pixmap(matrix=pymupdf.Matrix(2,2),clip=rect,alpha=False).save(destination/(name+'-source.png'))
                    page_artifacts.append(destination/(name+'-source.png'))
                    body.append('<section><b>'+html.escape(str(record['id']))+'</b><br><code>'+html.escape(record.get('source',''))+' → '+html.escape(record.get('translation',''))+'</code><br>')
                    body.append(f'<img loading="lazy" src="{name}-source.png">')
                    if translated:
                        target_display.get_pixmap(matrix=pymupdf.Matrix(2,2),clip=rect,alpha=False).save(destination/(name+'-candidate.png'))
                        page_artifacts.append(destination/(name+'-candidate.png'))
                        body.append(f'<img loading="lazy" src="{name}-candidate.png">')
                    body.append('</section>')
                    report['regions'].append(record['id'])
                page_hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in page_artifacts}
                saved = dict(binding=page_binding, body=body[body_start:],
                    regions=report['regions'][region_start:],
                    residual_candidates=report['residual_candidates'][residual_start:], artifacts=page_hashes)
                save_json(page_report_path, dict(payload=saved,
                    sha256=hashlib.sha256(json.dumps(saved, sort_keys=True).encode()).hexdigest()))
                artifacts.update(page_hashes)
                artifacts[page_report_path.name] = hashlib.sha256(page_report_path.read_bytes()).hexdigest()
        finally:
            if translated:
                translated.close()
    report.update(source_sha256=source_hash, seconds=round(time.perf_counter()-started,3))
    summary = '<h2>Residual candidates (review required)</h2><ul>'
    for item in report['residual_candidates']:
        summary += '<li>'+html.escape(f"Page {item['page']+1}: {item['source']} — {item['bbox']}")+'</li>'
    summary += '</ul><a href="review-report.json">Review data</a>'
    if candidate:
        summary += ' | <a href="../apply-report.json">Fit and font report</a>'
    body.insert(2,summary)
    (destination/'index.html').write_text('\n'.join(body),encoding='utf-8')
    artifacts['index.html'] = hashlib.sha256((destination/'index.html').read_bytes()).hexdigest()
    report.update(binding=binding, cache_hit=False,
                  artifacts=artifacts)
    save_json(report_path,report)
    return report
