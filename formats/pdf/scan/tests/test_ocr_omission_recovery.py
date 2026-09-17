from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import extract_scan
import draft_blocks
import verify_scan


def test_wrong_180_classification_retries_only_rejected_crop():
    calls = []
    originals = [np.zeros((12, 60, 3), dtype=np.uint8), np.ones((12, 60, 3), dtype=np.uint8)]
    def classify(crops):
        return [c + 10 for c in crops], [['180', .998], ['0', 1.0]], 0
    def recognize(crops):
        calls.append(len(crops))
        if len(calls) == 1:
            return [('sol e aap', .337), ('clear next line', .92)], 0
        assert np.array_equal(crops[0], originals[0])
        return [('Los anclajes del pretensado', .908)], 0
    engine = SimpleNamespace(text_cls=classify, text_recognizer=recognize,
                             use_angle_cls=True, text_score=.5)
    result, angles, attempts = extract_scan.recognize_with_angle_guard(engine, originals)
    assert result[0][0].startswith('Los anclajes')
    assert angles == [0, 0]
    assert attempts == [2, 1]
    assert calls == [2, 1]


def test_good_upside_down_reading_is_not_retried():
    engine = SimpleNamespace(text_cls=lambda crops: (crops, [['180', .99]], 0),
        text_recognizer=lambda crops: ([('clear rotated text', .94)], 0),
        use_angle_cls=True, text_score=.5)
    _, angles, attempts = extract_scan.recognize_with_angle_guard(engine, [np.zeros((10, 40, 3))])
    assert angles == [180]
    assert attempts == [1]


def test_explicit_second_scale_does_not_add_another_orientation_retry():
    calls = []
    def recognize(crops):
        calls.append(1)
        return [('bad', .3)], 0
    engine = SimpleNamespace(text_cls=lambda crops: (crops, [['180', .99]], 0),
        text_recognizer=recognize, use_angle_cls=True, text_score=.5)
    _, _, attempts = extract_scan.recognize_with_angle_guard(engine, [np.zeros((10, 40, 3))], allow_retry=False)
    assert calls == [1]
    assert attempts == [1]


def test_uncovered_text_candidate_excludes_covered_line_and_rules():
    image = Image.new('RGB', (1000, 600), 'white')
    draw = ImageDraw.Draw(image)
    for y in (100, 200):
        for x in range(100, 800, 18):
            draw.rectangle((x, y, x + 8, y + 15), fill='black')
    draw.line((20, 350, 980, 350), fill='black', width=2)
    result = extract_scan.uncovered_text_candidates(image, [[95, 95, 810, 120]])
    assert any(b[1] <= 200 and b[3] >= 215 for b in result)
    assert not any(b[1] <= 100 <= b[3] for b in result)
    assert not any(b[1] <= 350 <= b[3] for b in result)


def test_uncovered_justified_line_with_wide_word_spaces():
    image = Image.new('RGB', (1100, 300), 'white')
    draw = ImageDraw.Draw(image)
    # Short, widely spaced words: each alone is below the ten-character filter.
    for word in range(10):
        for char in range(3):
            x = 50 + word * 95 + char * 15
            draw.rectangle((x, 100, x + 8, 115), fill='black')
    result = extract_scan.uncovered_text_candidates(image, [])
    assert any(b[0] <= 50 and b[2] >= 943 and b[1] <= 100 <= b[3] for b in result)


def test_candidate_inventory_reaches_draft_and_existing_semantic_review():
    candidate = {'id': 'p01-c001', 'box': [10, 20, 300, 40], 'reason': 'uncovered_ink'}
    manifest = {'source_sha256': 'a', 'selected_pages': [1], 'source_lines': [],
                'pages': [{'source_page': 1, 'pixel_height': 500, 'ocr_review_candidates': [candidate]}]}
    draft = draft_blocks.translation_payload(manifest)
    assert draft['pages'][0]['ocr_review_candidates'] == [candidate]
    review = {'source_sha256': 'a', 'candidate_sha256': 'b', 'adapter': 'scan',
        'selected_source_pages': [1], 'pages': [{'source_page': 1, 'status': 'passed',
        'reviewed_source_ids': [], 'context_checked': 'blank', 'corrections': [],
        'unresolved_issues': [], 'no_readable_text': 'blank'}]}
    assert verify_scan.validate_translation_review(review, manifest, 'a', 'b')
    review['pages'][0]['reviewed_source_ids'] = ['p01-c001']
    assert verify_scan.validate_translation_review(review, manifest, 'a', 'b'), 'IDs alone cannot resolve suspected missing text'
    review['pages'][0]['corrections'] = [{'source_id': 'p01-c001', 'disposition': 'non_text', 'reason': 'Inspected: decorative marks, not text.'}]
    assert not verify_scan.validate_translation_review(review, manifest, 'a', 'b')


def test_accepted_short_word_does_not_hide_rejected_whole_line():
    assert not extract_scan.candidate_is_covered([10, 10, 900, 40], [20, 10, 90, 40])
    assert extract_scan.candidate_is_covered([10, 10, 900, 40], [5, 5, 905, 45])


def test_candidate_cannot_bind_to_remote_translated_title_and_can_preserve_model():
    candidate = {'id': 'c1', 'box': [10, 500, 300, 530]}
    line = {'id': 'l1', 'page': 1, 'box': [10, 50, 300, 80]}
    block = {'page': 1, 'source_line_ids': ['l1'], 'action': 'replace', 'translation': '标题'}
    manifest = {'selected_pages': [1], 'source_lines': [line], 'blocks': [block],
                'pages': [{'source_page': 1, 'ocr_review_candidates': [candidate]}]}
    note = {'source_id': 'c1', 'disposition': 'supplemented', 'source_line_ids': ['l1'], 'reason': 'Read source'}
    review = {'source_sha256': 'a', 'candidate_sha256': 'b', 'adapter': 'scan', 'selected_source_pages': [1],
        'pages': [{'source_page': 1, 'status': 'passed', 'reviewed_source_ids': ['l1','c1'],
                   'context_checked': 'Checked page', 'unresolved_issues': [], 'corrections': [note]}]}
    assert any('location' in e for e in verify_scan.validate_translation_review(review, manifest, 'a', 'b'))
    line['box'] = candidate['box']
    assert not verify_scan.validate_translation_review(review, manifest, 'a', 'b')
    note.update(disposition='preserved', reason='Verified model identifier; retain exactly.')
    block.update(action='preserve', status='preserve_confirm', translation='')
    assert not verify_scan.validate_translation_review(review, manifest, 'a', 'b')


def test_wide_single_line_image_keeps_direct_recognition_path():
    box = np.array([[0, 0], [200, 0], [200, 10], [0, 10]], dtype=np.float32)
    def detector(_):
        raise AssertionError('wide strip must bypass detector as before')
    engine = SimpleNamespace(load_img=lambda pixels: pixels, text_detector=detector,
        sorted_boxes=lambda boxes: boxes, get_crop_img_list=lambda *args: None,
        get_boxes_img_without_det=lambda pixels, h, w: ([box], [pixels]),
        use_angle_cls=False, use_text_det=True, min_height=30, width_height_ratio=8,
        text_score=.5, text_recognizer=lambda crops: ([('clear strip', .9)], 0))
    result = extract_scan._ocr_pass(engine, Image.new('RGB', (200, 10), 'white'), 1)
    assert result[0]['text'] == 'clear strip'
