"""Explicit prose/list continuation pages; no implicit reconstruction or table flow."""
from __future__ import annotations

import copy
import hashlib
import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def output_page_plan(manifest: dict) -> list[dict]:
    extra = manifest.get('pagination', {}).get('continuations', [])
    result = []
    for source in manifest['selected_pages']:
        for index in [0] + sorted(c['index'] for c in extra if c['source_page'] == source):
            result.append(dict(output_page=len(result)+1, source_page=source, continuation_index=index))
    return result


def require_supported_destinations(manifest: dict) -> None:
    """Never drop or retain stale interactive destinations during pagination."""
    reader = PdfReader(manifest['source'])
    if reader.outline or reader.named_destinations:
        raise ValueError('pagination of internal bookmarks/named destinations is not implemented')
    for number in manifest['selected_pages']:
        annotations = reader.pages[number-1].get('/Annots') or []
        annotations = annotations.get_object() if hasattr(annotations, 'get_object') else annotations
        for reference in annotations:
            item = reference.get_object(); action = item.get('/A') or {}
            action = action.get_object() if hasattr(action, 'get_object') else action
            if item.get('/Dest') is not None or action.get('/S') == '/GoTo':
                raise ValueError('pagination of internal link destinations is not implemented')


def _overlap(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _inside(box, outer):
    return (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)
            and outer[0] <= box[0] < box[2] <= outer[2] and outer[1] <= box[1] < box[3] <= outer[3])


def validate_pagination(manifest: dict) -> None:
    data = manifest.get('pagination')
    segmented = [b for b in manifest['blocks'] if 'segments' in b]
    if data is None:
        if segmented: raise ValueError('segments require an explicit pagination plan')
        return
    if not isinstance(data, dict) or not str(data.get('reason', '')).strip():
        raise ValueError('pagination requires an actual overflow reason')
    pages = {p['source_page']: p for p in manifest['pages']}
    extra = data.get('continuations')
    if not isinstance(extra, list) or not extra or not segmented:
        raise ValueError('pagination requires continuation pages and exact translation segments')
    keys = [(c.get('source_page'), c.get('index')) for c in extra]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate continuation page')
    for source in manifest['selected_pages']:
        indices = sorted(i for s, i in keys if s == source)
        if indices != list(range(1, len(indices)+1)):
            raise ValueError('continuation indices must start at one and be consecutive')
    for c in extra:
        if c.get('source_page') not in manifest['selected_pages']:
            raise ValueError('continuation owner is not a selected source page')
        page = pages[c['source_page']]; bounds = [0, 0, page['pixel_width'], page['pixel_height']]
        if not _inside(c.get('body_box'), bounds):
            raise ValueError('continuation body box escapes original page geometry')
        for region in c.get('repeat_regions', []):
            if region.get('role') not in ('header', 'footer', 'table_header', 'table_frame') or not _inside(region.get('box'), bounds):
                raise ValueError('only located original-format header/footer/table regions may repeat')
            target = region.get('target_box', region['box'])
            if (not _inside(target, bounds)
                    or abs((target[2]-target[0])-(region['box'][2]-region['box'][0])) > .01
                    or abs((target[3]-target[1])-(region['box'][3]-region['box'][1])) > .01):
                raise ValueError('repeated format pixels may shift but must not stretch or escape the page')
            for b in manifest['blocks']:
                if b['page'] != c['source_page'] or not _overlap(b['box'], region['box']): continue
                primary = not b.get('segments') or any(s['continuation_index'] == 0 for s in b['segments'])
                if primary and b['role'] not in ('header', 'footer', 'table_header', 'warning_title'):
                    raise ValueError('repeat region would duplicate body, artwork or identifier ownership')
        for repeated in c.get('repeat_blocks', []):
            owner = next((b for b in manifest['blocks'] if b.get('id') == repeated.get('id')), None)
            if (owner is None or owner['page'] != c['source_page']
                    or owner['role'] not in ('header', 'footer', 'warning_title')
                    or not _inside(repeated.get('box'), bounds)):
                raise ValueError('only an existing same-owner ordinary header/footer may be repeated')
    occupied = set()
    for block in segmented:
        if block['action'] != 'replace' or block.get('rich_lines') or block['role'].startswith('table'):
            raise ValueError('pagination supports plain prose/lists only; complex table or rich text flow is unsupported')
        segments = block['segments']
        if not isinstance(segments, list) or not segments or ''.join(s.get('translation', '') for s in segments) != block['translation']:
            raise ValueError(f"block {block['id']} segment text must concatenate exactly to its complete translation")
        indices = [s.get('continuation_index') for s in segments]
        if indices != sorted(indices):
            raise ValueError('segments must follow nondecreasing physical-page order')
        for segment in segments:
            index = segment['continuation_index']; owner = block['page']
            if not isinstance(index, int) or index < 0 or not segment.get('translation', '').strip():
                raise ValueError('each segment needs a nonempty translation and output index')
            if index and (owner, index) not in keys:
                raise ValueError('segment continuation page is not declared')
            page = pages[owner]; bounds = [0, 0, page['pixel_width'], page['pixel_height']]
            if index:
                config = next(c for c in extra if (c['source_page'], c['index']) == (owner, index))
                # Repeated table headings may use their original heading frame;
                # ordinary prose/list segments stay in the reviewed body area.
                bounds = config['body_box'] if block['role'] not in ('warning_title', 'header', 'footer') else bounds
                occupied.add((owner, index))
            if not _inside(segment.get('box'), bounds):
                raise ValueError('segment box escapes its declared continuation body area')
    if set(keys) != occupied:
        raise ValueError('empty continuation page is not justified by overflow content')
    for moved in data.get('moved_table_frames', []):
        if moved.get('content_kind') != 'prose_callout' or not str(moved.get('reason', '')).strip():
            raise ValueError('only an explicitly reviewed prose callout frame may move to continuation')
        owner = moved.get('source_page'); region = moved.get('box')
        if owner not in pages or not _inside(region, [0,0,pages[owner]['pixel_width'],pages[owner]['pixel_height']]):
            raise ValueError('moved prose frame escapes the original source page')
        if not any(c['source_page'] == owner and any(r['role'] == 'table_frame' and r['box'] == region
                       for r in c.get('repeat_regions', [])) for c in extra):
            raise ValueError('moved frame must be preserved as exact source-format pixels on a continuation')
        for b in manifest['blocks']:
            if b['page'] == owner and _overlap(b['box'], region):
                if (b['action'] != 'replace' or b['role'] not in ('body','list_item','warning_body','warning_title')
                        or not b.get('segments') or any(s['continuation_index'] == 0 for s in b['segments'])):
                    raise ValueError('moved frame overlaps content still owned by the primary page or a protected graphic')
    refs = data.get('reference_updates', {})
    if refs.get('status') not in ('applied', 'not_present') or not str(refs.get('reason', '')).strip():
        raise ValueError('pagination needs an explicit running-page/TOC/internal-reference update review')
    expected = {(r['source_page'], r['continuation_index']) for r in output_page_plan(manifest)}
    numbering = data.get('page_numbers', [])
    if len(numbering) != len(expected) or {(r.get('source_page'), r.get('continuation_index')) for r in numbering} != expected:
        raise ValueError('page-number plan must account for every original and continuation output')
    for row in numbering:
        if row.get('text') is None:
            if not str(row.get('reason', '')).strip(): raise ValueError('unnumbered output needs its actual source-style reason')
        elif not isinstance(row['text'], str) or not row['text'].strip() or not _inside(row.get('box'), [0, 0, pages[row['source_page']]['pixel_width'], pages[row['source_page']]['pixel_height']]):
            raise ValueError('running page number needs explicit text and a located original-style box')
        if row.get('block_id'):
            block = next((b for b in manifest['blocks'] if b['id'] == row['block_id']), None)
            if (block is None or block['page'] != row['source_page'] or block['role'] != 'footer'
                    or block['action'] != 'replace' or block.get('segments')
                    or (row['continuation_index'] == 0 and block['translation'] != row['text'])):
                raise ValueError('page-number block_id must bind its same-owner replacement footer and primary text')


def blocks_for_output(manifest: dict, source: int, index: int) -> list[dict]:
    result = []
    for block in manifest['blocks']:
        if block['page'] != source or block['action'] not in ('replace', 'add_bilingual'): continue
        segments = block.get('segments')
        if segments is None:
            if index == 0: result.append(copy.deepcopy(block))
            continue
        for segment_index, segment in enumerate(segments):
            if segment['continuation_index'] == index:
                result.append({**copy.deepcopy(block), 'translation': segment['translation'], 'box': segment['box'],
                               '_segment_index': segment_index})
    return result


def primary_manifest(manifest: dict) -> dict:
    result = copy.deepcopy(manifest)
    number_ids = {r.get('block_id') for r in manifest.get('pagination', {}).get('page_numbers', [])}
    expanded = []
    for block in result['blocks']:
        if block['id'] in number_ids:
            block['_suppress_draw'] = True
            expanded.append(block)
            continue
        if 'segments' not in block:
            expanded.append(block)
            continue
        first = [(i,s) for i,s in enumerate(block['segments']) if s['continuation_index'] == 0]
        if first:
            expanded.extend({**copy.deepcopy(block),'translation':s['translation'],'box':s['box'],
                             '_segment_index':i} for i,s in first)
        else:
            block['_suppress_draw'] = True
            expanded.append(block)
    result['blocks'] = expanded
    return result


def assemble_continuations(manifest: dict, primary_path: Path, destination: Path, draw_block,
                           clean_paths: dict[int, str], number_font: str) -> dict:
    """Repeat clean source-format pixels and redraw current selectable headings.

    Clipping a whole PDF page would retain invisible body text in its stream.
    Small raster-background crops plus the current heading blocks avoid that
    duplicate content while preserving the scan's actual header/table styling.
    """
    validate_pagination(manifest)
    primary = PdfReader(primary_path); pages = {p['source_page']: p for p in manifest['pages']}
    primary_index = {n: i for i, n in enumerate(manifest['selected_pages'])}
    plan = output_page_plan(manifest); rows = []; new_records = []; repeated = []
    number_ids = {r.get('block_id') for r in manifest['pagination']['page_numbers']}
    with PdfWriter() as writer:
        for row in plan:
            source, index = row['source_page'], row['continuation_index']; page = pages[source]
            base = primary.pages[primary_index[source]]
            numbering = next(n for n in manifest['pagination']['page_numbers'] if (n['source_page'], n['continuation_index']) == (source, index))
            if index == 0:
                writer.add_page(base); target = writer.pages[-1]
            else:
                config = next(c for c in manifest['pagination']['continuations'] if (c['source_page'], c['index']) == (source, index))
                target = writer.add_blank_page(page['width_pt'], page['height_pt'])
                stream = io.BytesIO(); pdf = canvas.Canvas(stream, pagesize=(page['width_pt'], page['height_pt']), pageCompression=1)
                with Image.open(clean_paths[source]) as clean:
                    for region in config.get('repeat_regions', []):
                        x0, y0, x1, y1 = region['box']; sx = page['width_pt']/page['pixel_width']; sy = page['height_pt']/page['pixel_height']
                        crop = clean.crop(tuple(map(int, region['box'])))
                        tx0, ty0, tx1, ty1 = region.get('target_box', region['box'])
                        pdf.drawImage(ImageReader(crop), tx0*sx, page['height_pt']-ty1*sy,
                                      (tx1-tx0)*sx, (ty1-ty0)*sy)
                        repeated.append(dict(output_page=row['output_page'], source_page=source,
                            box=region['box'], target_box=region.get('target_box', region['box']), role=region['role'],
                            clean_base_sha256=hashlib.sha256(Path(clean_paths[source]).read_bytes()).hexdigest(),
                            pixel_sha256=hashlib.sha256(crop.tobytes()).hexdigest()))
                        crop.close()
                # Repeat only the current, already-reviewed ordinary headers and
                # footers. Segmented headings are drawn by their own assignment.
                for block in manifest['blocks']:
                    if (block['page'] == source and not block.get('segments')
                            and block['id'] not in number_ids
                            and block['action'] == 'replace'
                            and block['role'] in ('header', 'footer', 'table_header', 'warning_title')
                            and any(_inside(block['box'], r['box']) for r in config.get('repeat_regions', []))):
                        draw_block(pdf, block, page)
                for repeated_block in config.get('repeat_blocks', []):
                    owner = next(b for b in manifest['blocks'] if b['id'] == repeated_block['id'])
                    draw_block(pdf, {**owner, 'box': repeated_block['box']}, page)
                for block in blocks_for_output(manifest, source, index):
                    record = draw_block(pdf, block, page)
                    record.update(output_page=row['output_page'], continuation_index=index)
                    new_records.append(record)
                pdf.save(); target.merge_page(PdfReader(stream).pages[0])
            moves = [r for r in manifest['pagination'].get('moved_table_frames', [])
                     if index == 0 and r['source_page'] == source]
            if numbering.get('text') is not None or moves:
                stream = io.BytesIO(); pdf = canvas.Canvas(stream, pagesize=(page['width_pt'], page['height_pt']))
                sx = page['width_pt']/page['pixel_width']; sy = page['height_pt']/page['pixel_height']
                for moved in moves:
                    x0,y0,x1,y1=moved['box'];pdf.setFillColorRGB(1,1,1)
                    pdf.rect(x0*sx,page['height_pt']-y1*sy,(x1-x0)*sx,(y1-y0)*sy,fill=1,stroke=0)
                if numbering.get('text') is not None:
                    x0, y0, x1, y1 = numbering['box']
                    pdf.setFillColorRGB(1, 1, 1); pdf.rect(x0*sx, page['height_pt']-y1*sy, (x1-x0)*sx, (y1-y0)*sy, fill=1, stroke=0)
                    pdf.setFillColorRGB(0, 0, 0); pdf.setFont(number_font, float(numbering.get('font_size', 8)))
                    pdf.drawString(x0*sx+1, page['height_pt']-y1*sy+2, numbering['text'])
                    if numbering.get('block_id'):
                        new_records.append(dict(id=numbering['block_id'], complete=True,
                            font_size=float(numbering.get('font_size',8)), line_count=1,
                            box_pt=[x0*sx,page['height_pt']-y1*sy,x1*sx,page['height_pt']-y0*sy],
                            output_page=row['output_page'], continuation_index=index, page_number=True))
                pdf.save()
                target.merge_page(PdfReader(stream).pages[0])
            rows.append(row)
        writer.write(destination)
    return {'output_page_mapping': rows, 'continuation_rendered_blocks': new_records,
            'continuation_repeat_regions': repeated,
            'pagination_moved_table_frames': manifest['pagination'].get('moved_table_frames', [])}


def verify_page_numbers(manifest: dict, pdf_path: Path) -> list[str]:
    if not manifest.get('pagination'): return []
    import pdfplumber
    pages = {p['source_page']: p for p in manifest['pages']}; errors = []
    with pdfplumber.open(pdf_path) as document:
        for row in output_page_plan(manifest):
            number = next(n for n in manifest['pagination']['page_numbers'] if
                (n['source_page'], n['continuation_index']) == (row['source_page'], row['continuation_index']))
            if number.get('text') is None: continue
            page = pages[row['source_page']]; x0, y0, x1, y1 = number['box']
            sx, sy = page['width_pt']/page['pixel_width'], page['height_pt']/page['pixel_height']
            actual = document.pages[row['output_page']-1].crop((x0*sx, y0*sy, x1*sx, y1*sy)).extract_text() or ''
            if ''.join(actual.split()) != ''.join(number['text'].split()):
                errors.append(f"output page {row['output_page']}: running page-number glyphs differ from plan")
    return errors
