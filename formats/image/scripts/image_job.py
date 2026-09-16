"""Batch the existing image workflow; reviews remain agent-authored evidence."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import re

import numpy as np
from PIL import Image, ImageOps

from image_pdf_bridge import wrap, unwrap, sha256_file

ROOT = Path(__file__).resolve().parents[3]
SCAN = ROOT / 'formats/pdf/scan/scripts'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def run(script, *args):
    subprocess.run([sys.executable, str(script), *map(str, args)], check=True)


def image_ocr_scale(pixel_size, dpi):
    """Avoid treating a 72-pt/pixel carrier's enlargement as real scan detail."""
    if dpi <= 0 or min(pixel_size) <= 0:
        raise ValueError('Image dimensions and DPI must be positive')
    # Small source glyphs benefit from 2x interpolation, not a blind 400/72x.
    # Larger originals retain all native pixels. This affects OCR only.
    source_scale = 2 if max(pixel_size) < 1600 else 1
    return min(1.0, source_scale * 72 / dpi)


def print_inventory(extraction, metadata):
    page = extraction['pages'][0]
    sx = metadata['pixel_size'][0] / page['pixel_width']
    sy = metadata['pixel_size'][1] / page['pixel_height']
    print('Line\tBox (original image pixels)\tSource text')
    for line in extraction['source_lines']:
        box = [round(v*s) for v,s in zip(line['box'],(sx,sy,sx,sy))]
        print(f"{line['id'].split('-l')[-1]}\t{','.join(map(str,box))}\t{line['text']}")


def prepare(source, job, target, dpi):
    if (job / 'source.pdf').exists():
        raise ValueError('Fresh preparation requires a new job directory')
    run(ROOT / 'formats/pdf/scripts/session_metrics.py', 'start', '--job', job,
        '--source', source, '--target-language', target, '--mode', 'replace', '--pages', 1,
        '--budget-per-page', 180)
    wrap(source, job / 'source.pdf', job / 'image-metadata.json')
    metadata = read(job / 'image-metadata.json')
    sys.path.insert(0, str(SCAN))
    from extract_scan import extract_selected_pages
    extraction = extract_selected_pages(
        job / 'source.pdf', [1], job / 'extract', dpi=dpi,
        ocr_scales=(image_ocr_scale(metadata['pixel_size'], dpi),))
    (job / 'manifest').mkdir(exist_ok=True)
    run(SCAN / 'draft_blocks.py', '--extraction', job / 'extract/extraction-report.json',
        '--output', job / 'manifest/draft-groups.json')
    draft = read(job / 'manifest/draft-groups.json')
    save(job / 'manifest/decisions.json', {
        'source_sha256': draft['source_sha256'], 'target_language': target,
        'styles': {}, 'supplements': [],
        'regions': [{'group': group['id'], 'translation': ''} for group in draft['groups']],
    })
    # Compact evidence for a single model read, not another OCR or translation.
    save(job / 'manifest/context.json', {
        'pages': draft['pages'],
        'groups': [{k: g[k] for k in ('id', 'line_ids', 'text', 'role', 'box')}
                   for g in draft['groups']],
        'lines': [{k: line[k] for k in ('id', 'page', 'text', 'box', 'rotation')}
                  for line in extraction['source_lines']],
    })
    # Small line inventory avoids sending the same page text three times.
    print_inventory(extraction, metadata)


def import_rows(job, path):
    """Agent-authored TSV: IDs/ranges, role, translation, optional target box.

    Supplement IDs start with + and add source text plus ORIGINAL-image pixel
    coordinates: +id TAB role TAB translation TAB x0,y0,x1,y1 TAB source text.
    Existing-line target boxes use original-image pixels too. No automatic
    translations or semantic grouping are made here.
    """
    extraction = read(job / 'extract/extraction-report.json')
    metadata = read(job / 'image-metadata.json')
    page = extraction['pages'][0]
    sx, sy = page['pixel_width']/metadata['pixel_size'][0], page['pixel_height']/metadata['pixel_size'][1]
    lines = {line['id']: line for line in extraction['source_lines']}
    regions, supplements = [], []
    for row in path.read_text(encoding='utf-8-sig').splitlines():
        if not row.strip() or row.startswith('#'):
            continue
        fields = row.split('\t')
        key, role, translation = fields[:3]
        box = None
        if len(fields) > 3 and fields[3]:
            x0,y0,x1,y1 = map(float, fields[3].split(','))
            box = [x0*sx, y0*sy, x1*sx, y1*sy]
        if key.startswith('+'):
            if box is None or len(fields) != 5 or not fields[4].strip():
                raise ValueError('Supplement requires located box and source text')
            ids = [key[1:]]
            line = {'id':ids[0], 'page':1, 'text':fields[4], 'box':box,
                    'rotation':0, 'origin':'visual_supplement'}
            if ids[0] in lines:
                raise ValueError('Duplicate supplement')
            supplements.append(line)
            lines[ids[0]] = line
        else:
            ids = []
            for part in key.split(','):
                if not re.fullmatch(r'\d+(?:-\d+)?', part):
                    raise ValueError('IDs must be line numbers or inclusive ranges')
                ends = list(map(int, part.split('-')))
                ids.extend(f'p01-l{i:03}' for i in range(ends[0], ends[-1]+1))
        item = {'ids':ids, 'role':role}
        if role == 'preserve':
            item['preserve_reason'] = translation
        else:
            item['translation'] = translation.replace('\\n','\n')
        if box is not None and not key.startswith('+'):
            item['box'] = box
        else:
            owned = [lines[i]['box'] for i in ids]
            # Same modest padding as draft groups; cleanup stays at glyph boxes.
            item['box'] = [max(0,min(b[0] for b in owned)-2*sx),
                           max(0,min(b[1] for b in owned)-2*sy),
                           min(page['pixel_width'],max(b[2] for b in owned)+2*sx),
                           min(page['pixel_height'],max(b[3] for b in owned)+2*sy)]
        if not key.startswith('+') and len(fields) > 4 and fields[4]:
            item['clean_boxes'] = []
            for envelope in fields[4].split(';'):
                x0,y0,x1,y1 = map(float, envelope.split(','))
                item['clean_boxes'].append([x0*sx,y0*sy,x1*sx,y1*sy])
        regions.append(item)
    save(job/'manifest/decisions.json', {
        'source_sha256':extraction['source_sha256'], 'target_language':read(job/'manifest/decisions.json')['target_language'],
        'styles':{'heading':{'max_font':14,'min_font':7},'body':{'max_font':12,'min_font':6},
                  'footer':{'max_font':7,'min_font':4}},
        'regions':regions,'supplements':supplements,
    })


def build(job, output):
    run(SCAN / 'compile_translation.py',
        '--extraction', job / 'extract/extraction-report.json',
        '--draft', job / 'manifest/draft-groups.json',
        '--decisions', job / 'manifest/decisions.json',
        '--output', job / 'manifest/translation-manifest.json')
    pdf = job / 'output/translated.pdf'
    run(SCAN / 'build_scan.py', '--manifest', job / 'manifest/translation-manifest.json',
        '--output', pdf)
    unwrap(pdf, job / 'image-metadata.json', output)
    metadata = read(job / 'image-metadata.json')
    restore_untouched_pixels(Path(metadata['source_path']), output,
                             read(job / 'manifest/translation-manifest.json'),
                             metadata['source_sha256'])
    print(json.dumps({'candidate_sha256':sha256_file(output), 'output':str(output)}))


def record_review(job, output, candidate_hash, note):
    """Serialize an explicit post-view whole-page review, never infer a verdict."""
    if sha256_file(output) != candidate_hash:
        raise ValueError('Review hash does not match candidate')
    if not note.strip():
        raise ValueError('Actual source/target review findings are required')
    metadata = read(job/'image-metadata.json')
    manifest = read(job/'manifest/translation-manifest.json')
    save(job/'review/translation-review.json', {
        'source_sha256':metadata['source_sha256'], 'candidate_sha256':candidate_hash,
        'adapter':'image','selected_source_pages':[1],
        'pages':[{'source_page':1,'status':'passed',
                  'reviewed_source_ids':[line['id'] for line in manifest['source_lines']],
                  'context_checked':note,'unresolved_issues':[]}]})
    save(job/'review/visual-review.json', {
        'candidate_sha256':candidate_hash,'whole_image_reviewed':True,
        'reviewed_changed_regions':True,'text_overlap_failures':[],
        'clipping_failures':[],'unreadable_text_failures':[],
        'untranslated_clear_labels':0,'notes':[note]})


def edit_mask(manifest, size):
    width, height = size
    allowed = np.zeros((height, width), dtype=bool)
    page = manifest['pages'][0]
    sx, sy = width / page['pixel_width'], height / page['pixel_height']
    for block in manifest['blocks']:
        if block['action'] != 'replace':
            continue
        boxes = block.get('clean_boxes', [block.get('clean_box')])
        for x0, y0, x1, y1 in [block['box'], *boxes]:
            allowed[max(0, math.floor(y0*sy)-1):min(height, math.ceil(y1*sy)+1),
                    max(0, math.floor(x0*sx)-1):min(width, math.ceil(x1*sx)+1)] = True
    return allowed


def restore_untouched_pixels(source, output, manifest, source_hash):
    """Avoid PDF round-trip resampling outside reviewed text regions.

    Translated pixels still come exclusively from the official raster builder.
    JPEG must be re-encoded; its final differences remain visible in check().
    """
    if sha256_file(source) != source_hash:
        raise ValueError('Source changed before output composition')
    with Image.open(source) as raw:
        fmt = raw.format
        src = ImageOps.exif_transpose(raw).copy()
    with Image.open(output) as raw:
        dst = raw.convert('RGBA' if 'A' in src.getbands() else 'RGB')
    src = src.convert(dst.mode)
    if src.size != dst.size:
        raise ValueError('Cannot compose images with different sizes')
    mask = Image.fromarray(edit_mask(manifest, src.size).astype('uint8') * 255)
    src.paste(dst, mask=mask)
    src.save(output, format=fmt, **({'quality': 95, 'subsampling': 0} if fmt == 'JPEG' else {}))


def check(source, job, output):
    metadata = read(job / 'image-metadata.json')
    manifest = read(job / 'manifest/translation-manifest.json')
    build_report = read(job / 'output/translated.build-report.json')
    source_hash, output_hash = sha256_file(source), sha256_file(output)
    failures = []
    if metadata['source_sha256'] != source_hash:
        failures.append('source_hash_mismatch')
    if build_report.get('output_sha256') != sha256_file(job / 'output/translated.pdf'):
        failures.append('stale_build_report')
    if build_report.get('builder') != 'translate-scan-pdf-professionally':
        failures.append('unofficial_builder')
    if manifest['source_sha256'] != sha256_file(job / 'source.pdf'):
        failures.append('carrier_hash_mismatch')
    expected = {b['id'] for b in manifest['blocks'] if b['action'] == 'replace'}
    rendered = build_report.get('rendered_blocks', [])
    if ({b['id'] for b in rendered} != expected
            or any(b.get('complete') is not True for b in rendered)):
        failures.append('incomplete_rendering')
    with Image.open(source) as raw:
        source_format = raw.format
        src = ImageOps.exif_transpose(raw).convert('RGBA')
    with Image.open(output) as raw:
        output_format = raw.format
        dst = raw.convert('RGBA')
    same_geometry = src.size == dst.size == tuple(metadata['pixel_size'])
    if not same_geometry or source_format != output_format:
        failures.append('raster_contract')
    pixel_evidence = {'status': 'unverified'}
    if same_geometry:
        allowed = edit_mask(manifest, src.size)
        a, b = np.asarray(src), np.asarray(dst)
        delta = np.abs(a[:, :, :3].astype(np.int16) - b[:, :, :3].astype(np.int16))
        outside = delta[~allowed]
        changed = int(np.any(outside != 0, axis=1).sum())
        pixel_evidence = {'outside_changed_pixels': changed,
                          'outside_max_difference': int(outside.max()) if outside.size else 0,
                          'outside_mean_difference': float(outside.mean()) if outside.size else 0,
                          'alpha_equal': bool(np.array_equal(a[:, :, 3], b[:, :, 3]))}
        # PNG is lossless. JPEG differences need a located source/output review;
        # do not silently invent a tolerance or borrow PDF cleanup evidence.
        pixel_evidence['status'] = 'passed' if changed == 0 and pixel_evidence['alpha_equal'] else 'unverified'
        if pixel_evidence['status'] != 'passed':
            failures.append('final_image_nontext_changes_require_review')
    required_ids = {line['id'] for line in manifest['source_lines']}
    for name in ('translation-review', 'visual-review'):
        path = job / 'review' / (name + '.json')
        if not path.exists():
            failures.append('missing_' + name)
            continue
        evidence = read(path)
        if evidence.get('candidate_sha256') != output_hash:
            failures.append('stale_' + name)
        if name == 'translation-review':
            pages = evidence.get('pages', [])
            if (evidence.get('source_sha256') != source_hash or len(pages) != 1
                or pages[0].get('source_page') != 1 or pages[0].get('status') != 'passed'
                or pages[0].get('unresolved_issues') != []
                or not pages[0].get('context_checked')
                or set(pages[0].get('reviewed_source_ids', [])) != required_ids):
                failures.append('incomplete_semantic_review')
        elif (evidence.get('whole_image_reviewed') is not True
              or evidence.get('reviewed_changed_regions') is not True
              or any(evidence.get(k) != [] for k in ('text_overlap_failures', 'clipping_failures', 'unreadable_text_failures'))
              or evidence.get('untranslated_clear_labels') != 0):
            failures.append('incomplete_visual_review')
    report = {'source_sha256': source_hash, 'output_sha256': output_hash,
              'adapter': 'image', 'pixel_check': pixel_evidence,
              'failures': failures, 'passed': not failures}
    save(job / 'qa/final-qa.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('prepare')
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--target-language', required=True)
    p.add_argument('--dpi', type=int, default=400)
    for name in ('build', 'check', 'finish'):
        p2 = subs.add_parser(name)
        p2.add_argument('--output', required=True, type=Path)
        if name == 'check':
            p2.add_argument('--source', required=True, type=Path)
        if name == 'build':
            p2.add_argument('--rows', type=Path)
        if name == 'finish':
            p2.add_argument('--candidate-sha256', required=True)
            p2.add_argument('--reviewed-all-passed', action='store_true', required=True)
            p2.add_argument('--review-note', required=True)
    for p in subs.choices.values():
        p.add_argument('--job', required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    if args.command == 'prepare':
        prepare(args.source.resolve(), args.job.resolve(), args.target_language, args.dpi)
    elif args.command == 'build':
        if args.rows:
            import_rows(args.job.resolve(), args.rows)
        build(args.job.resolve(), args.output.resolve())
    elif args.command == 'finish':
        record_review(args.job, args.output, args.candidate_sha256, args.review_note)
        report = check(Path(read(args.job/'image-metadata.json')['source_path']),args.job,args.output)
        print(json.dumps(report))
        if not report['passed']:
            return 2
        run(ROOT/'formats/pdf/scripts/session_metrics.py','pause','--job',args.job)
    else:
        report = check(args.source.resolve(), args.job.resolve(), args.output.resolve())
        print(json.dumps(report))
        if not report['passed']:
            return 2
    print(json.dumps({'stage': args.command, 'tool_seconds': round(time.perf_counter()-started, 3)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
