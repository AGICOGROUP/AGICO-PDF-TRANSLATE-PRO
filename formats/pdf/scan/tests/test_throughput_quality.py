from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_scan
import draft_blocks
import verify_scan
import extract_scan
from pypdf import PdfWriter


def test_background_sampling_does_not_convert_full_page():
    image = Image.new('RGB', (2000, 3000), (20, 40, 60))
    original = np.asarray
    def bounded(value, *args, **kwargs):
        if isinstance(value, Image.Image):
            assert value.width * value.height < 10000, 'whole-page copy per glyph'
        return original(value, *args, **kwargs)
    with patch.object(build_scan.np, 'asarray', bounded):
        assert build_scan._sample_background(image, (100, 200, 180, 230)) == (20, 40, 60)


def test_clean_cache_invalidates_pixels_but_reuses_translation_only_edit(tmp_path):
    source = tmp_path / 'source.png'
    Image.new('RGB', (100, 100), 'black').save(source)
    page = {'source_page': 1, 'render_path': str(source)}
    blocks = [{'action': 'replace', 'clean_box': [10, 10, 20, 20],
               'background': [255, 255, 255], 'translation': 'one'}]
    first, _, _, hit = build_scan.prepare_clean_base(page, blocks, tmp_path)
    assert not hit
    assert first.getpixel((15, 15)) == (255, 255, 255)
    blocks[0]['translation'] = 'two'
    second, _, _, hit = build_scan.prepare_clean_base(page, blocks, tmp_path)
    assert hit
    assert second.tobytes() == first.tobytes()
    blocks[0]['background'] = [255, 0, 0]
    third, _, _, hit = build_scan.prepare_clean_base(page, blocks, tmp_path)
    assert not hit
    assert third.getpixel((15, 15)) == (255, 0, 0)
    Image.new('RGB', (100, 100), 'blue').save(source)
    fourth, _, _, hit = build_scan.prepare_clean_base(page, blocks, tmp_path)
    assert not hit
    assert fourth.getpixel((50, 50)) == (0, 0, 255)


def review_fixture():
    manifest = {'selected_pages': [1], 'source_lines': [{'id': 'p1', 'page': 1}]}
    review = {'source_sha256': 'a'*64, 'candidate_sha256': 'b'*64,
              'adapter': 'scan', 'selected_source_pages': [1], 'pages': [{
                  'source_page': 1, 'status': 'passed', 'reviewed_source_ids': ['p1'],
                  'context_checked': 'Reviewed requirement and its exception against source pixels.',
                  'corrections': [], 'unresolved_issues': []}]}
    return manifest, review


@pytest.mark.parametrize('fault', ['missing', 'stale', 'omitted_id', 'unresolved', 'duplicate_page'])
def test_semantic_gate_rejects_incomplete_evidence(fault):
    manifest, review = review_fixture()
    if fault == 'missing': review = None
    elif fault == 'stale': review['candidate_sha256'] = 'c'*64
    elif fault == 'omitted_id': review['pages'][0]['reviewed_source_ids'] = []
    elif fault == 'unresolved': review['pages'][0]['unresolved_issues'] = ['wrong negation']
    else: review['pages'].append(copy.deepcopy(review['pages'][0]))
    assert verify_scan.validate_translation_review(review, manifest, 'a'*64, 'b'*64)


def test_semantic_gate_accepts_complete_bound_review():
    manifest, review = review_fixture()
    assert verify_scan.validate_translation_review(review, manifest, 'a'*64, 'b'*64) == []


@pytest.mark.parametrize('empty', [None, False, [], {}, '  '])
def test_semantic_gate_requires_textual_context(empty):
    manifest, review = review_fixture()
    review['pages'][0]['context_checked'] = empty
    assert verify_scan.validate_translation_review(review, manifest, 'a'*64, 'b'*64)


def test_semantic_gate_requires_textual_no_text_reason():
    manifest, review = review_fixture()
    manifest['source_lines'] = []
    review['pages'][0]['reviewed_source_ids'] = []
    review['pages'][0]['no_readable_text'] = True
    assert verify_scan.validate_translation_review(review, manifest, 'a'*64, 'b'*64)


def test_rich_blocks_decode_source_once_per_page(tmp_path):
    source = tmp_path / 'source.png'
    Image.new('RGB', (200, 200), 'white').save(source)
    manifest = {'source': 'fixture.pdf', 'source_sha256': 'a'*64, 'target_language': 'en',
                'selected_pages': [1], 'pages': [{'source_page': 1, 'width_pt': 200, 'height_pt': 200,
                'pixel_width': 200, 'pixel_height': 200, 'render_path': str(source)}],
                'source_lines': [], 'blocks': []}
    for index, y in enumerate([20, 80]):
        box = [10, y, 180, y+40]
        line_id = f'l{index}'
        manifest['source_lines'].append({'id': line_id, 'page': 1, 'text': 'UNO', 'box': box, 'rotation': 0})
        manifest['blocks'].append({'id': f'b{index}', 'page': 1, 'source_line_ids': [line_id],
            'source': 'UNO', 'translation': 'One', 'role': 'body', 'status': 'translated',
            'action': 'replace', 'box': box, 'clean_box': box,
            'rich_lines': [[{'type': 'text', 'text': 'One'}]], 'rotation': 0})
    original = Image.open
    source_decodes = []
    def tracked(path, *args, **kwargs):
        if str(path) == str(source): source_decodes.append(path)
        return original(path, *args, **kwargs)
    with patch.object(build_scan.Image, 'open', tracked):
        report = build_scan.build_pdf(manifest, tmp_path/'output.pdf')
    assert report['rendered_block_count'] == 2
    assert len(source_decodes) == 2  # Once for cleanup, once shared by all rich blocks.


def test_translation_payload_has_page_context_and_stable_region_ids():
    lines = [{'id': 'l2', 'page': 1, 'text': 'second', 'box': [10, 300, 200, 320], 'score': 1},
             {'id': 'l1', 'page': 1, 'text': 'first', 'box': [10, 200, 200, 220], 'score': 1}]
    report = {'source_sha256': 'a'*64, 'selected_pages': [1],
              'pages': [{'source_page': 1, 'pixel_height': 1000}], 'source_lines': lines}
    payload = draft_blocks.translation_payload(report)
    assert payload['pages'][0]['ordered_source_ids'] == ['l1', 'l2']
    assert payload['pages'][0]['page_context'] == 'first\nsecond'
    assert all(g['id'] for g in payload['groups'])
    assert [i for g in payload['groups'] for i in g['line_ids']] == ['l1', 'l2']


def test_context_reads_same_baseline_fragments_left_to_right():
    lines = [{'id': 'a', 'page': 1, 'text': 'La presente', 'box': [100, 300, 290, 340], 'score': 1},
             {'id': 'b', 'page': 1, 'text': 'especificacion', 'box': [310, 301, 510, 341], 'score': 1},
             {'id': 'c', 'page': 1, 'text': 'ha sido elaborada', 'box': [535, 299, 810, 339], 'score': 1}]
    payload = draft_blocks.translation_payload({'source_sha256': 'a'*64, 'selected_pages': [1],
        'pages': [{'source_page': 1, 'pixel_height': 1200}], 'source_lines': lines})
    assert payload['pages'][0]['page_context'] == 'La presente especificacion ha sido elaborada'
    assert payload['pages'][0]['ordered_source_ids'] == ['a', 'b', 'c']


def test_ocr_resume_keeps_completed_page_after_failure(tmp_path, monkeypatch):
    import types
    source = tmp_path / 'two.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=100, height=100)
    writer.write(source)
    monkeypatch.setitem(sys.modules, 'rapidocr_onnxruntime', types.SimpleNamespace(RapidOCR=lambda: object()))
    monkeypatch.setattr(extract_scan, 'configure_page_detector', lambda engine: None)
    count = 0
    def fake_pass(engine, image, scale):
        nonlocal count
        count += 1
        if count == 3:
            raise RuntimeError('simulated OCR allocation failure on page 2')
        return [{'box': [1, 1, 20, 10], 'quad': [[1, 1], [20, 1], [20, 10], [1, 10]],
                 'rotation': 0, 'text': 'Texto', 'score': 1, 'scale': scale}]
    monkeypatch.setattr(extract_scan, '_ocr_pass', fake_pass)
    with pytest.raises(RuntimeError, match='allocation'):
        extract_scan.extract_selected_pages(source, [1, 2], tmp_path / 'job', dpi=72)
    resumed = extract_scan.extract_selected_pages(source, [1, 2], tmp_path / 'job', dpi=72)
    assert resumed['pages'][0]['ocr_cache_hit'] is True
    assert len(resumed['source_lines']) == 2
    assert [row['id'] for row in resumed['source_lines']] == ['p01-l001', 'p02-l001']
    assert count == 5  # Two completed passes are not repeated after the failure.
    (tmp_path / 'job' / 'source-pages-72dpi' / 'source-page-01.png').write_bytes(b'broken')
    repaired = extract_scan.extract_selected_pages(source, [1, 2], tmp_path / 'job', dpi=72)
    assert repaired['pages'][1]['ocr_cache_hit'] is True
    assert len(repaired['source_lines']) == 2
