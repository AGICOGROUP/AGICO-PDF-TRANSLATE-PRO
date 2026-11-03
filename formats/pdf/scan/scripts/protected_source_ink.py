"""Verify unchanged, visually classified numeric/formula/code ink without fake OCR.

Classification remains a source-review judgment. Pixel identity proves preservation,
not whether prose was correctly classified; ordinary language still needs translation.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageChops


def protection_note_errors(note):
    errors = []
    if note.get('content_kind') not in {'numeric', 'formula', 'code', 'symbol', 'proper_name'}:
        errors.append('protected ink must be numeric, formula, code, symbol or justified proper name; prose is not eligible')
    if not isinstance(note.get('reason'), str) or not note['reason'].strip():
        errors.append('protected ink requires an actual source-based classification reason')
    return errors


def compare_ink(source, target, box):
    if source.size != target.size:
        return ['protected ink page geometry differs']
    if (not isinstance(box, (list, tuple)) or len(box) != 4
            or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in box)):
        return ['invalid protected ink box']
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= source.width and 0 <= y0 < y1 <= source.height):
        return ['protected ink box is outside the page']
    crop = (math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1))
    # Convert the small reviewed region, not two complete scan pages per note.
    difference = ImageChops.difference(source.crop(crop).convert('RGB'), target.crop(crop).convert('RGB'))
    return ['protected source ink was modified'] if difference.getbbox() else []


def validate_protected_ink(review, manifest, source_pdf, target_pdf, output_dir,
                           output_page_map=None):
    """CLI-owned pixel checks, never trust a review's claimed pixel-pass field.

    output_page_map optionally maps one-based output pages to source pages. Repeated
    source pages (continuations) need explicit output_page in each protection note.
    """
    from extract_scan import find_pdftoppm
    from pypdf import PdfReader

    errors = []
    notes = []
    candidates = {c['id']: (p, c) for p in manifest['pages']
                  for c in p.get('ocr_review_candidates', [])}
    for entry in (review or {}).get('pages', []):
        for note in entry.get('corrections', []) + entry.get('source_limitations', []):
            if note.get('disposition') == 'preserved_ink':
                notes.append(note)
    if not notes:
        return errors
    notes.sort(key=lambda note: (candidates.get(note.get('source_id'), ({'source_page': -1},))[0]['source_page'],
                                 note.get('output_page') or 0))
    if output_page_map is None:
        if len(PdfReader(str(target_pdf)).pages) != len(manifest['selected_pages']):
            return ['protected ink needs explicit output page mapping after pagination']
        output_page_map = dict(enumerate(manifest['selected_pages'], 1))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered = {}
    renderer = find_pdftoppm()
    for note in notes:
        cid = note.get('source_id')
        prefix = f'candidate {cid}: '
        errors.extend(prefix + e for e in protection_note_errors(note))
        if cid not in candidates:
            errors.append(prefix + 'source candidate missing')
            continue
        page, candidate = candidates[cid]
        eligible = [int(k) for k, v in output_page_map.items() if v == page['source_page']]
        output_page = note.get('output_page', eligible[0] if len(eligible) == 1 else None)
        if output_page not in eligible:
            errors.append(prefix + 'ambiguous or mismatched output page')
            continue
        dpi = page.get('dpi')
        expected_size = (page.get('pixel_width'), page.get('pixel_height'))
        if (not isinstance(dpi, (int, float)) or isinstance(dpi, bool)
                or not math.isfinite(dpi) or dpi <= 0
                or any(not isinstance(v, int) or isinstance(v, bool) or v <= 0
                       for v in expected_size)):
            errors.append(prefix + 'invalid manifest pixel dimensions or DPI')
            continue
        key = (page['source_page'], output_page, dpi)
        if key not in rendered:
            rendered.clear()  # Retain one rendered page pair, not an entire large manual.
            pair = []
            for label, pdf, number in [('source', source_pdf, page['source_page']),
                                       ('target', target_pdf, output_page)]:
                stem = output_dir / f'{label}-{number:04}-{dpi}'
                # Render both current PDFs with identical media-box settings. Do not
                # accept externally supplied crops or unverifiable cached pass flags.
                subprocess.run([renderer, '-f', str(number), '-l', str(number), '-r', str(dpi),
                                '-png', '-singlefile', str(pdf), str(stem)],
                               check=True, capture_output=True)
                with Image.open(Path(str(stem) + '.png')) as im:
                    pair.append(im.convert('RGB').copy())
            rendered[key] = pair
        if any(image.size != expected_size for image in rendered[key]):
            errors.append(prefix + 'rendered source/target size differs from manifest pixel dimensions at declared DPI')
            continue
        errors.extend(prefix + e for e in compare_ink(*rendered[key], candidate['box']))
    return errors
