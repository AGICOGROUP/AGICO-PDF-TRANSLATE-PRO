#!/usr/bin/env python3
"""Source-bound coordinate replacement pipeline for native CAD PDFs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import time
from statistics import median
from typing import Any
from uuid import uuid4

import pymupdf
from cad_outline import extract_outline_records, cover_conflicts, drawing_index
from cad_batch import cell_proposals, merge_supplement, page_ocr, review_bundle
from cad_cache import LazyOCR
from cad_units import propose_units, merge_unit_translations


SOURCE_NAME = "SOURCE.pdf"
INVENTORY_NAME = "source-inventory.json"
PACKET_NAME = "translation-packet.json"
OUTPUT_NAME = "translated-native-cad.pdf"
APPLY_REPORT_NAME = "apply-report.json"
FINAL_QA_NAME = "final-qa.json"
DEFAULT_FONT = Path(r"C:\Windows\Fonts\simhei.ttf")
PROTECTED_PATTERNS = (
    re.compile(r"^[ØRrMm]?\s*[+\-±]?\d[\d.,/×x°'\s-]*(?:mm|cm|kg|kW|W|V|A)?$", re.I),
    re.compile(r"^(?:ISO|DIN|EN|GB)\s*[-:]?\s*[A-Z0-9./-]+$", re.I),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_protected(text: str) -> bool:
    value = " ".join(text.split())
    if not value:
        return True
    if value in {'M', 'PIT', 'PT', 'TT', 'TE', 'LT', 'LIT', 'PG', 'PS', 'PSL', 'PSH', 'LS', 'LSL', 'LSH', 'FT', 'FIT', 'VT', 'SE', 'DCS', 'PLC'}:
        return True
    return any(pattern.fullmatch(value) for pattern in PROTECTED_PATTERNS)


def cardinal_rotation(direction: tuple[float, float]) -> int:
    angle = round(math.degrees(math.atan2(-direction[1], direction[0]))) % 360
    return min((0, 90, 180, 270), key=lambda value: abs((angle - value + 180) % 360 - 180))


def page_snapshot(page: pymupdf.Page) -> dict[str, object]:
    return {
        "width": round(page.rect.width, 4),
        "height": round(page.rect.height, 4),
        "rotation": int(page.rotation),
        "image_count": len(page.get_images(full=True)),
        "painted_images": sorted([
            {'digest': item['digest'].hex(),
             'transform': [round(float(v), 4) for v in item['transform']]}
            for item in page.get_image_info(hashes=True)
        ], key=lambda item: (item['digest'], item['transform'])),
        "vector_count": len(page.get_drawings()),
    }


def extract_records(document: pymupdf.Document) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for page_index, page in enumerate(document):
        span_index = 0
        blocks = page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                direction = tuple(line.get("dir", (1.0, 0.0)))
                rotation = cardinal_rotation(direction)
                for span in line.get("spans", []):
                    text = " ".join(str(span.get("text", "")).split())
                    if not text:
                        continue
                    span_index += 1
                    protected = is_protected(text)
                    records.append(
                        {
                            "id": f"p{page_index + 1:04d}-s{span_index:05d}",
                            "page": page_index,
                            "source": text,
                            "bbox": [round(float(value), 4) for value in span["bbox"]],
                            "font_size": round(float(span.get("size", 8.0)), 3),
                            "color": int(span.get("color", 0)),
                            "rotation": rotation,
                            "status": "protected" if protected else "pending",
                        }
                    )
    return records


def prepare(source: Path, job_dir: Path, ocr: str = 'auto', *,
            target_language: str | None = None, fresh: bool = False) -> int:
    if not source.is_file():
        print("source file not found", file=sys.stderr)
        return 2
    if fresh:
        job_dir = job_dir.with_name(job_dir.name + '-fresh-' + uuid4().hex[:12])
    job_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    source_hash = sha256(source)
    old_packet = read_json(job_dir / PACKET_NAME) if (job_dir / PACKET_NAME).exists() else {}
    old_inventory = read_json(job_dir / INVENTORY_NAME) if (job_dir / INVENTORY_NAME).exists() else {}
    request = old_inventory.get('request', old_packet.get('request'))
    if target_language is not None:
        language = target_language.strip().replace('_', '-').casefold()
        if not language:
            print('target language must be nonempty', file=sys.stderr)
            return 2
        request = {'target_language': language, 'translation_mode': 'replace', 'pages': 'all'}
    if any(old.get('request') is not None and old.get('request') != request
           for old in (old_inventory, old_packet)):
        print('job target language differs; use --fresh or a new job directory', file=sys.stderr)
        return 2
    if (request is not None and old_packet and old_packet.get('request') is None
            and any(r.get('status') != 'pending' or r.get('translation') for r in old_packet.get('records', []))):
        print('legacy translations have no target binding; use --fresh or resume without rebinding', file=sys.stderr)
        return 2
    if any(old and old.get('source_sha256') != source_hash for old in (old_packet, old_inventory)):
        print('job belongs to another source; use a different job directory', file=sys.stderr)
        return 2
    bound_source = job_dir / SOURCE_NAME
    if source.resolve() != bound_source.resolve():
        shutil.copyfile(source, bound_source)
    try:
        document = pymupdf.open(bound_source)
    except Exception as exc:
        print(f"cannot open source PDF: {exc}", file=sys.stderr)
        return 2
    if document.needs_pass or document.page_count == 0:
        document.close()
        print("source PDF is encrypted or contains no pages", file=sys.stderr)
        return 2
    inventory = {
        "schema_version": 1,
        **({'request': request} if request is not None else {}),
        "source_sha256": sha256(bound_source),
        "page_count": document.page_count,
        "pages": [page_snapshot(page) for page in document],
        "records": extract_records(document),
    }
    needs_ocr = ocr == 'always' or (ocr == 'auto' and any(p['vector_count'] > 100 or p['image_count'] for p in inventory['pages']))
    if needs_ocr:
        try:
            engine = LazyOCR()
            outlines, timing = extract_outline_records(document, job_dir, source_hash, inventory['records'], engine=engine)
            supplement_started = time.perf_counter()
            supplement_count, supplement_hits = 0, 0
            for page_index, page in enumerate(document):
                proposals, hit = page_ocr(page, source_hash, job_dir/'ocr-cache', engine)
                added = merge_supplement(outlines, proposals, inventory['records'], page_index)
                outlines.extend(added)
                supplement_count += len(added)
                supplement_hits += int(hit)
            timing['supplement'] = {'seconds': round(time.perf_counter()-supplement_started,3),
                                    'added': supplement_count, 'cache_hits': supplement_hits}
        except Exception as exc:
            document.close()
            write_json(job_dir / 'prepare-report.json', {'passed': False, 'error': f'OCR failed; rerun to resume cached tiles: {exc}'})
            return 2
        for record in outlines:
            if is_protected(record['source']):
                record['status'] = 'protected'
        inventory['records'].extend(outlines)
        inventory['ocr'] = timing
    # Same-source resume must not erase manually inventoried regions that OCR
    # cannot reproduce. Re-extracted IDs remain authoritative.
    extracted_ids = {r['id'] for r in inventory['records']}
    inventory['records'].extend(r for r in old_inventory.get('records', [])
                                if r['id'] not in extracted_ids)
    placement = {}
    for page_index, page in enumerate(document):
        placement.update(cell_proposals(page, [r for r in inventory['records'] if r['page'] == page_index]))
    inventory['placements'] = placement
    document.close()
    previous = {r['id']: r for r in old_packet.get('records', [])}
    packet = {
        "schema_version": 1,
        **({'request': request} if request is not None else {}),
        "source_sha256": inventory["source_sha256"],
        "records": [
            {
                "id": record["id"],
                "source": record["source"],
                "translation": "",
                "status": "pending",
                "page": record['page'],
                "bbox": record['bbox'],
                "kind": record.get('kind', 'native'),
                "role": 'body',
                **({'placement_proposal': placement[record['id']]} if record['id'] in placement else {}),
                **({'rotation': record['rotation']} if record.get('kind') == 'outline' else {}),
                **({'cover_review': {'approved': False, 'text_only': False, 'white_background': False, 'note': ''}} if record.get('kind') == 'outline' else {}),
            }
            for record in inventory["records"]
            if record["status"] == "pending"
        ],
    }
    for record in packet['records']:
        old = previous.get(record['id'], {})
        if (old.get('source') == record['source']
                and old.get('page') == record['page']
                and old.get('bbox') == record['bbox']):
            record.update({k: v for k, v in old.items() if k not in ('id', 'source', 'page', 'bbox', 'kind')})
    packet['page_context'] = [{'page': page, 'records': [{'id': r['id'], 'source': r['source']} for r in sorted(inventory['records'], key=lambda v: (v['bbox'][1], v['bbox'][0])) if r['page'] == page]} for page in range(inventory['page_count'])]
    inventory['prepare_seconds'] = round(time.perf_counter() - started, 3)
    write_json(job_dir / INVENTORY_NAME, inventory)
    write_json(job_dir / PACKET_NAME, packet)
    write_json(job_dir / 'translation-units.json', propose_units(inventory))
    source_review = review_bundle(bound_source, job_dir/'source-review', packet['records'])
    write_json(job_dir / 'prepare-report.json', {'passed': True, 'seconds': round(time.perf_counter()-started,3), 'ocr': inventory.get('ocr'), 'records': len(inventory['records']), 'cell_proposals': len(placement), 'source_review_seconds': source_review['seconds']})
    print(json.dumps({"stage": "prepared", "job_dir": str(job_dir)}, ensure_ascii=False))
    return 0


def merge_units(job_dir: Path, translations: Path) -> int:
    try:
        inventory = read_json(job_dir / INVENTORY_NAME)
        if sha256(job_dir / SOURCE_NAME) != inventory['source_sha256']:
            raise ValueError('source hash mismatch')
        packet = read_json(job_dir / PACKET_NAME)
        if packet.get('source_sha256') != inventory['source_sha256'] or packet.get('request') != inventory.get('request'):
            raise ValueError('packet source/request mismatch')
        merged, count = merge_unit_translations(inventory, packet, read_json(translations))
        write_json(job_dir / PACKET_NAME, merged)
        print(json.dumps({'stage': 'units_merged', 'units': count, 'packet': str(job_dir / PACKET_NAME)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def validate_packet(
    inventory: dict[str, object], packet: dict[str, object]
) -> tuple[dict[str, dict[str, object]], list[str]]:
    expected = {
        str(record["id"]): record
        for record in inventory["records"]
        if record["status"] == "pending"
    }
    supplied = {str(record.get("id")): record for record in packet.get("records", [])}
    incomplete: list[str] = []
    if len(supplied) != len(packet.get('records', [])):
        incomplete.append('duplicate_packet_ids')
    incomplete.extend(f'unexpected:{key}' for key in supplied.keys() - expected.keys())
    for record_id, source_record in expected.items():
        translated = supplied.get(record_id)
        if translated and translated.get('status') == 'merged':
            leader_id = translated.get('merged_into')
            leader = supplied.get(leader_id, {})
            origin = expected.get(leader_id, {})
            if (translated.get('source') == source_record['source']
                    and source_record.get('kind') != 'outline'
                    and origin.get('kind') != 'outline'
                    and leader.get('status') == 'translated'
                    and str(leader.get('translation', '')).strip()
                    and origin.get('page') == source_record['page']
                    and origin.get('rotation') == source_record.get('rotation')
                    and leader.get('layout_box')
                    and str(translated.get('review_note', '')).strip()):
                continue
            incomplete.append(record_id)
            continue
        if (translated and translated.get('source') == source_record['source']
                and translated.get('status') in ('dismissed', 'preserved')
                and str(translated.get('review_note', '')).strip()
                and (translated['status'] == 'preserved' or source_record.get('kind') == 'outline')):
            continue
        if (translated and translated.get('source') == source_record['source']
                and translated.get('status') == 'cover_only'
                and source_record.get('kind') == 'outline'
                and str(translated.get('target_present', '')).strip()
                and str(translated.get('review_note', '')).strip()):
            continue
        if (
            translated is None
            or translated.get("source") != source_record["source"]
            or translated.get("status") != "translated"
            or not str(translated.get("translation", "")).strip()
        ):
            incomplete.append(record_id)
    return supplied, incomplete


def rgb_from_int(value: int) -> tuple[float, float, float]:
    return (
        ((value >> 16) & 255) / 255,
        ((value >> 8) & 255) / 255,
        (value & 255) / 255,
    )


def insert_fitted_text(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    text: str,
    source_size: float,
    color: tuple[float, float, float],
    rotation: int,
    font_file: Path,
    *, commit: bool = True,
) -> float | None:
    def probe(size):
        shape = page.new_shape()
        spare = shape.insert_textbox(
            rect,
            text,
            fontname="nativecad-cjk",
            fontfile=str(font_file),
            fontsize=size,
            color=color,
            rotate=rotation,
        )
        return shape if spare >= 0 else None
    high, low = max(source_size, 4.0), 4.0
    shape = probe(high)
    if shape is not None:
        if commit:
            shape.commit(overlay=True)
        return high
    best = probe(low)
    if best is None:
        return None
    # Binary search fits the entire paragraph without repeatedly mutating PDF.
    while high - low > .1:
        size = (high + low) / 2
        shape = probe(size)
        if shape is None:
            high = size
        else:
            low, best = size, shape
    if commit:
        best.commit(overlay=True)
    return low


def typography_baselines(records, supplied):
    groups = {}
    for record in records:
        role = supplied[str(record['id'])].get('role', 'body')
        box = pymupdf.Rect(record.get('bbox', (0, 0, 0, 0)))
        rotation = int(record.get('rotation', 0)) % 360
        line_height = box.width if rotation in (90, 270) else box.height
        effective_size = float(record['font_size'])
        if record.get('kind') != 'outline' and line_height > effective_size * 4:
            effective_size = line_height * .7
        groups.setdefault((int(record['page']), role), []).append(effective_size)
    baseline = {key: max(4, median(sizes)) for key, sizes in groups.items()}
    for page, _ in groups:
        body = baseline.get((page, 'body'))
        if body is not None:
            if (page, 'annotation') in baseline:
                body = baseline[(page, 'body')] = max(5., body)
            if (page, 'title') in baseline:
                baseline[(page, 'title')] = max(baseline[(page, 'title')], body * 1.25)
            if (page, 'annotation') in baseline:
                baseline[(page, 'annotation')] = min(baseline[(page, 'annotation')], max(4, body * .8))
    return baseline


def redraw_paths(page: pymupdf.Page, paths: list[dict[str, object]]) -> None:
    for path in paths:
        shape = page.new_shape()
        for item in path['items']:
            if item[0] == 'l':
                shape.draw_line(item[1], item[2])
            elif item[0] == 'c':
                shape.draw_bezier(item[1], item[2], item[3], item[4])
            elif item[0] == 're':
                shape.draw_rect(item[1])
            elif item[0] == 'qu':
                shape.draw_quad(item[1])
        line_cap = path.get('lineCap', 0)
        if isinstance(line_cap, (tuple, list)):
            line_cap = max(line_cap)
        shape.finish(
            color=path.get('color'), fill=path.get('fill'),
            width=float(path.get('width') or 0.1), dashes=path.get('dashes'),
            lineCap=int(line_cap or 0), lineJoin=int(path.get('lineJoin') or 0),
            closePath=bool(path.get('closePath')), even_odd=bool(path.get('even_odd')),
            stroke_opacity=float(path.get('stroke_opacity') or 1),
            fill_opacity=float(path.get('fill_opacity') or 1),
        )
        shape.commit(overlay=True)


def apply(job_dir: Path, packet_path: Path, font_file: Path) -> int:
    started = time.perf_counter()
    inventory_path = job_dir / INVENTORY_NAME
    bound_source = job_dir / SOURCE_NAME
    report_path = job_dir / APPLY_REPORT_NAME
    if not inventory_path.is_file() or not bound_source.is_file() or not packet_path.is_file():
        write_json(report_path, {"passed": False, "error": "missing prepared job or packet"})
        return 2
    inventory = read_json(inventory_path)
    packet = read_json(packet_path)
    failures: list[str] = []
    if sha256(bound_source) != inventory.get("source_sha256"):
        failures.append("source_hash_mismatch")
    if packet.get("source_sha256") != inventory.get("source_sha256"):
        failures.append("packet_source_hash_mismatch")
    if inventory.get('request') is not None and packet.get('request') != inventory['request']:
        failures.append('packet_request_mismatch')
    supplied, incomplete = validate_packet(inventory, packet)
    if incomplete:
        failures.append("incomplete_translations")
    if not font_file.is_file():
        failures.append("font_file_not_found")
    if failures:
        write_json(
            report_path,
            {
                "passed": False,
                "failures": failures,
                "incomplete_records": incomplete,
                "fit_failures": [],
            },
        )
        return 2

    # A box that fits text may still be outside the visible page. Validate
    # native and outline placements before fitting or erasing any source text.
    invalid_layouts = []
    with pymupdf.open(bound_source) as source_document:
        for record in inventory['records']:
            translated = supplied.get(str(record['id']), {})
            if translated.get('status') != 'translated':
                continue
            box = translated.get('layout_box', record['bbox'])
            reason = None
            try:
                if (not isinstance(box, (list, tuple)) or len(box) != 4
                        or any(isinstance(v, bool) or not isinstance(v, (int, float))
                               or not math.isfinite(v) for v in box)
                        or box[2] <= box[0] or box[3] <= box[1]):
                    reason = 'invalid_layout_box'
                else:
                    page = source_document[int(record['page'])]
                    # Text extraction and insertion use unrotated coordinates,
                    # whereas page.rect reflects /Rotate and the visible CropBox.
                    if not (page.rect * page.derotation_matrix).contains(pymupdf.Rect(box)):
                        reason = 'layout_outside_page'
            except (ValueError, TypeError, IndexError, OverflowError):
                reason = 'invalid_layout_box'
            if reason:
                invalid_layouts.append({'id': record['id'], 'reason': reason})
    if invalid_layouts:
        write_json(report_path, {'passed': False, 'failures': ['invalid_layout_regions'],
                                'invalid_layout_regions': invalid_layouts, 'fit_failures': []})
        return 2

    # Check each distinct output character once, before covering any source text.
    characters = {c for r in supplied.values() if r.get('status') == 'translated'
                  for c in r['translation'] if not c.isspace()}
    requested_font = font_file
    missing = []
    for candidate_font in dict.fromkeys((font_file, DEFAULT_FONT.parent / 'ARIALUNI.TTF',
                                         DEFAULT_FONT.parent / 'arial.ttf')):
        if not candidate_font.is_file():
            continue
        font = pymupdf.Font(fontfile=str(candidate_font))
        missing = sorted(c for c in characters if not font.has_glyph(ord(c)))
        if not missing:
            font_file = candidate_font
            break
    if missing:
        write_json(report_path, {'passed': False, 'failures': ['font_missing_glyphs'],
                                'font_file': str(requested_font),
                                'missing_glyphs': [f'U+{ord(c):04X}' for c in missing]})
        return 2

    document = pymupdf.open(bound_source)
    covered = [record for record in inventory["records"] if record["status"] == "pending" and supplied[str(record['id'])].get('status') in ('translated', 'cover_only', 'merged')]
    by_page: dict[int, list[dict[str, object]]] = {}
    for record in covered:
        by_page.setdefault(int(record["page"]), []).append(record)
    unsafe = []
    restore_by_page: dict[int, set[int]] = {}
    drawings_by_page = {}
    for page_index, records in by_page.items():
        drawings = drawing_index(document[page_index]) if any(r.get('kind') == 'outline' for r in records) else []
        drawings_by_page[page_index] = drawings
        for record in records:
            if record.get('kind') != 'outline':
                continue
            translated = supplied[str(record['id'])]
            review = translated.get('cover_review', {})
            # Explicit agent pixel review, never inferred from OCR confidence.
            boxes = translated.get('cover_boxes', [record['bbox']])
            layout_box = translated.get('layout_box', record['bbox'])
            reasons = []
            if not boxes:
                reasons.append('empty_cover_boxes')
            if translated.get('rotation', record['rotation']) not in (0, 90, 180, 270):
                reasons.append('unsupported_rotation')
            for box in dict.fromkeys(tuple(b) for b in boxes):
                box_reasons = cover_conflicts(document[page_index], box, drawings)
                if review.get('source_text_paths') is True:
                    threshold = max(24., min(pymupdf.Rect(record['bbox']).width, pymupdf.Rect(record['bbox']).height) * 2.5)
                    source_rect = pymupdf.Rect(record['bbox']) + (-2, -2, 2, 2)
                    def is_reviewed_source_text(reason):
                        if ':' not in reason:
                            return False
                        path_rect = pymupdf.Rect(drawings['paths'][int(reason.split(':')[1])]['rect'])
                        return (max(path_rect.width, path_rect.height) <= threshold
                                or (min(path_rect.width, path_rect.height) > 2 and path_rect.intersects(source_rect)))
                    box_reasons = [reason for reason in box_reasons if not is_reviewed_source_text(reason)]
                reasons.extend(box_reasons)
                if not pymupdf.Rect(box).intersects(pymupdf.Rect(record['bbox'])):
                    reasons.append('region_not_adjacent_to_source')
                for other in inventory['records']:
                    if other['page'] == page_index and other['id'] != record['id'] and other.get('kind') != 'outline' and pymupdf.Rect(box).intersects(pymupdf.Rect(other['bbox'])):
                        reasons.append(f'other_native_text:{other["id"]}')
            page = document[page_index]
            if not (page.rect * page.derotation_matrix).contains(pymupdf.Rect(layout_box)):
                reasons.append('layout_outside_page')
            if not pymupdf.Rect(layout_box).intersects(pymupdf.Rect(record['bbox'])):
                reasons.append('layout_not_adjacent_to_source')
            if not all(review.get(k) is True for k in ('approved', 'text_only', 'white_background')) or not review.get('note'):
                reasons.append('source_pixel_review_required')
            restorable = {'crossing_path', 'symbol_or_frame', 'filled_region', 'curve'}
            if reasons and review.get('restore_conflicting_paths') is True and all(reason.split(':')[0] in restorable for reason in reasons):
                restore_by_page.setdefault(page_index, set()).update(
                    int(reason.split(':')[1]) for reason in reasons
                )
                reasons = []
            if reasons:
                unsafe.append({'id': record['id'], 'reasons': reasons})
    if unsafe:
        document.close()
        write_json(report_path, {'passed': False, 'failures': ['unsafe_outline_regions'], 'regions': unsafe, 'fit_failures': []})
        return 2
    # Fit before erasing source labels. Failed labels stay intact in a preview.
    translated_records = [r for r in covered if supplied[str(r['id'])].get('status') == 'translated']
    baselines = typography_baselines(translated_records, supplied)
    fitted_sizes = {}
    for record in translated_records:
        translated = supplied[str(record['id'])]
        fitted_sizes[record['id']] = insert_fitted_text(
            document[int(record['page'])],
            pymupdf.Rect(translated.get('layout_box', record['bbox'])),
            str(translated['translation']).strip(),
            baselines[(int(record['page']), translated.get('role', 'body'))],
            rgb_from_int(int(record['color'])),
            int(translated.get('rotation', record['rotation']) if record.get('kind') == 'outline' else record['rotation']),
            font_file, commit=False,
        )
    fit_failures = [key for key, size in fitted_sizes.items() if size is None]
    fit_failures.extend(r['id'] for r in covered
                        if supplied[str(r['id'])].get('merged_into') in fit_failures)
    for page_index, records in by_page.items():
        page = document[page_index]
        records = [r for r in records if r['id'] not in fit_failures]
        for record in records:
            if record.get('kind') != 'outline':
                page.add_redact_annot(pymupdf.Rect(record["bbox"]), fill=None, cross_out=False)
        page.apply_redactions(images=0, graphics=0, text=0)
        for record in records:
            if record.get('kind') == 'outline':
                for box in supplied[str(record['id'])].get('cover_boxes', [record['bbox']]):
                    page.draw_rect(pymupdf.Rect(box), color=None, fill=(1, 1, 1), overlay=True)
        if restore_by_page.get(page_index):
            redraw_paths(page, [drawings_by_page[page_index]['paths'][index] for index in sorted(restore_by_page[page_index])])

    applied_records: list[dict[str, object]] = []
    for record in translated_records:
        if record['id'] in fit_failures:
            continue
        translated = supplied[str(record["id"])]
        page = document[int(record["page"])]
        fitted_size = insert_fitted_text(
            page,
            pymupdf.Rect(translated.get('layout_box', record['bbox'])),
            str(translated["translation"]).strip(),
            fitted_sizes[record['id']],
            rgb_from_int(int(record["color"])),
            int(translated.get('rotation', record['rotation']) if record.get('kind') == 'outline' else record['rotation']),
            font_file,
        )
        if fitted_size is None:
            # Never save a candidate if a previously fitting label disappeared.
            document.close()
            write_json(report_path, {'passed': False, 'failures': ['fit_changed_after_cleanup'],
                                     'fit_failures': [record['id']]})
            return 2
        else:
            baseline = baselines[(int(record['page']), translated.get('role', 'body'))]
            applied_records.append({"id": record["id"], "font_size": fitted_size, 'baseline_font_size': baseline,
                                    'shrink_reason': 'complete_paragraph_overflow' if fitted_size < baseline else None})

    output = job_dir / OUTPUT_NAME
    if fit_failures:
        preview = job_dir / 'translated-native-cad-preview.pdf'
        document.save(preview, garbage=4, deflate=True)
        document.close()
        write_json(
            report_path,
            {
                "passed": False,
                "failures": ["text_fit_failure"],
                "incomplete_records": [],
                "fit_failures": fit_failures,
                "applied_records": applied_records,
                "source_sha256": inventory['source_sha256'],
                "preview": str(preview),
                "preview_sha256": sha256(preview),
                "source_retained_ids": fit_failures,
                "delivery_status": "preview_requires_review",
            },
        )
        print(json.dumps({'stage': 'preview_requires_review', 'output': str(preview),
                          'fit_failures': fit_failures}, ensure_ascii=False))
        return 2
    document.save(output, garbage=4, deflate=True)
    document.close()
    write_json(
        report_path,
        {
            "passed": True,
            "source_sha256": inventory["source_sha256"],
            "candidate_sha256": sha256(output),
            "failures": [],
            "incomplete_records": [],
            "fit_failures": [],
            "applied_records": applied_records,
            "seconds": round(time.perf_counter() - started, 3),
            "packet_sha256": sha256(packet_path),
            "font_file": str(font_file),
            "requested_font_file": str(requested_font),
            "restored_path_count": sum(len(paths) for paths in restore_by_page.values()),
        },
    )
    write_review_template(job_dir, sha256(output))
    print(json.dumps({"stage": "applied", "output": str(output)}, ensure_ascii=False))
    return 0


def same_page_structure(expected: dict[str, object], actual: dict[str, object]) -> bool:
    stable_fields_match = all(
        expected[key] == actual[key]
        for key in ("width", "height", "rotation")
    )
    images_match = (expected['painted_images'] == actual.get('painted_images')
                    if 'painted_images' in expected
                    else expected['image_count'] == actual['image_count'])
    # Path counts change with harmless merging/splitting and cannot prove damage.
    return stable_fields_match and images_match


def write_review_template(job_dir: Path, candidate_hash: str) -> None:
    write_json(job_dir / 'visual-review.template.json', {
        'candidate_sha256': candidate_hash,
        'all_pages_reviewed': False, 'all_changed_regions_reviewed': False,
        'visible_foreign_descriptive_text': [], 'text_overlap_failures': [],
        'line_or_graphic_damage': [], 'notes': '',
    })


def verify(
    job_dir: Path, candidate: Path, visual_review_path: Path | None
) -> int:
    inventory_path = job_dir / INVENTORY_NAME
    apply_report_path = job_dir / APPLY_REPORT_NAME
    failures: list[str] = []
    if not inventory_path.is_file() or not apply_report_path.is_file() or not candidate.is_file():
        failures.append("missing_job_evidence")
        write_json(job_dir / FINAL_QA_NAME, {"passed": False, "failures": failures})
        return 2
    inventory = read_json(inventory_path)
    apply_report = read_json(apply_report_path)
    bound_source = job_dir / SOURCE_NAME
    if sha256(bound_source) != inventory.get("source_sha256"):
        failures.append("source_hash_mismatch")
    candidate_hash = sha256(candidate)
    if not apply_report.get("passed") or apply_report.get("candidate_sha256") != candidate_hash:
        failures.append("candidate_not_bound_to_apply_report")
    vector_count_changes = []
    try:
        source_snapshots = inventory['pages']
        if any('painted_images' not in snapshot for snapshot in source_snapshots):
            with pymupdf.open(bound_source) as original:
                source_snapshots = [page_snapshot(page) for page in original]
        document = pymupdf.open(candidate)
        if document.page_count != inventory.get("page_count"):
            failures.append("page_count_mismatch")
        else:
            for index, expected in enumerate(source_snapshots):
                actual = page_snapshot(document[index])
                if not same_page_structure(expected, actual):
                    if "page_structure_mismatch" not in failures:
                        failures.append("page_structure_mismatch")
                if int(actual['vector_count']) < int(expected['vector_count']):
                    vector_count_changes.append({'page': index + 1,
                                                 'source': expected['vector_count'],
                                                 'candidate': actual['vector_count']})
        preview_dir = job_dir / "review"
        preview_dir.mkdir(exist_ok=True)
        render_binding = preview_dir / 'render-binding.json'
        rendered = read_json(render_binding) if render_binding.exists() else {}
        for index, page in enumerate(document):
            path = preview_dir / f'page-{index + 1:04d}.png'
            if rendered.get('candidate_sha256') != candidate_hash or not path.exists() or rendered.get('images', {}).get(path.name) != sha256(path):
                page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(path)
        write_json(render_binding, {'candidate_sha256': candidate_hash, 'images': {p.name: sha256(p) for p in preview_dir.glob('page-*.png')}})
        document.close()
    except Exception as exc:
        failures.append(f"candidate_read_error:{exc}")

    if visual_review_path is None or not visual_review_path.is_file():
        failures.append("visual_review_required")
    else:
        review = read_json(visual_review_path)
        if review.get("candidate_sha256") != candidate_hash:
            failures.append("visual_review_hash_mismatch")
        if not review.get("all_pages_reviewed"):
            failures.append("not_all_pages_reviewed")
        if not review.get("all_changed_regions_reviewed"):
            failures.append("not_all_changed_regions_reviewed")
        for key in (
            "visible_foreign_descriptive_text",
            "text_overlap_failures",
            "line_or_graphic_damage",
        ):
            if key not in review:
                failures.append(f'missing_review_field:{key}')
            elif review.get(key) != []:
                failures.append(key)

    qa = {
        "passed": not failures,
        "source_sha256": inventory.get("source_sha256"),
        "candidate_sha256": candidate_hash,
        "failures": failures,
        "warnings": {"reduced_vector_count": vector_count_changes} if vector_count_changes else {},
    }
    write_json(job_dir / FINAL_QA_NAME, qa)
    print(json.dumps(qa, ensure_ascii=False))
    return 0 if not failures else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("source", type=Path)
    prepare_parser.add_argument("--job-dir", required=True, type=Path)
    prepare_parser.add_argument('--target-language', help='Bind a new job to the requested target language')
    prepare_parser.add_argument('--fresh', action='store_true', help='Create an independent sibling job; return its path')
    prepare_parser.add_argument('--ocr', choices=('auto', 'always'), default='auto', help='auto detects vector-rich/image pages; always also scans sparse outline drawings')
    units_parser = subparsers.add_parser('merge-units', help='Import reviewed phrase translations into the original packet')
    units_parser.add_argument('job_dir', type=Path)
    units_parser.add_argument('--translations', required=True, type=Path)
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("job_dir", type=Path)
    apply_parser.add_argument("--packet", required=True, type=Path)
    apply_parser.add_argument("--font-file", type=Path, default=DEFAULT_FONT)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("job_dir", type=Path)
    verify_parser.add_argument("--candidate", required=True, type=Path)
    verify_parser.add_argument("--visual-review", type=Path)
    review_parser = subparsers.add_parser('review', help='Generate combined side-by-side review and residual candidates')
    review_parser.add_argument('job_dir', type=Path)
    review_parser.add_argument('--candidate', type=Path, required=True)
    review_parser.add_argument('--residual-script', choices=('cjk','latin'), required=True,
                               help='Source script to flag; identifiers are review candidates, not failures')
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    if args.command == "prepare":
        return prepare(args.source, args.job_dir, args.ocr,
                       target_language=args.target_language, fresh=args.fresh)
    if args.command == "apply":
        return apply(args.job_dir, args.packet, args.font_file)
    if args.command == 'merge-units':
        return merge_units(args.job_dir, args.translations)
    if args.command == 'review':
        packet = read_json(args.job_dir / PACKET_NAME)
        bound_source = args.job_dir / SOURCE_NAME
        if packet.get('source_sha256') != sha256(bound_source):
            raise ValueError('packet source hash mismatch')
        candidate_hash = sha256(args.candidate)
        applied = read_json(args.job_dir / APPLY_REPORT_NAME)
        if not applied.get('passed') or applied.get('candidate_sha256') != candidate_hash:
            raise ValueError('candidate must match successful apply report')
        report = review_bundle(bound_source, args.job_dir/'batch-review', packet['records'],
                               args.candidate, candidate_hash, args.residual_script)
        print(json.dumps({'stage':'review', 'seconds':report['seconds'],
                          'residual_candidates':len(report['residual_candidates']),
                          'index':str(args.job_dir/'batch-review'/'index.html')}))
        return 0
    return verify(args.job_dir, args.candidate, args.visual_review)


if __name__ == "__main__":
    raise SystemExit(main())
