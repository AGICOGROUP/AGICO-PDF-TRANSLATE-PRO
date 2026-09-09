import importlib.util
import io
import json
import sys
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen import canvas


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location('evidence_' + name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_solid_fill_cannot_erase_long_border():
    cleaner = load('build_clean_image_bases')
    source = np.full((200, 200, 3), 255, dtype=np.uint8)
    source[10:190, 20:22] = 0
    before = source.copy()
    with pytest.raises(ValueError, match='structur'):
        cleaner.clean_region(source, {'box': [10, 10, 180, 190], 'mode': 'solid_fill', 'fill_rgb': [255, 255, 255]})
    assert np.array_equal(source, before)


def test_clean_report_measures_outside_and_protected_pixels(tmp_path):
    cleaner = load('build_clean_image_bases')
    source = np.full((20, 20, 3), 255, dtype=np.uint8)
    source[5:8, 5:8] = 0
    Image.fromarray(source).save(tmp_path / 'source.png')
    metadata = tmp_path / 'metadata.json'
    metadata.write_text(json.dumps({'images': [{'id': 'img', 'source': 'source.png', 'output': 'clean.png', 'protected_boxes': [[5, 5, 8, 8]], 'regions': [{'box': [3, 3, 12, 12], 'mode': 'neutral_plain'}]}]}))
    result = cleaner.build(metadata)['images'][0]
    assert result.get('outside_region_pixel_changes') == 0
    assert result.get('protected_pixel_changes') == 0
    assert np.array_equal(np.array(Image.open(tmp_path / 'clean.png'))[5:8, 5:8], source[5:8, 5:8])


def test_body_image_text_is_left_aligned():
    overlay = load('apply_image_vector_text')
    overlay.register_fonts(overlay.default_font(False), overlay.default_font(True))
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(300, 200))
    overlay.draw_horizontal(pdf, (20, 20, 220, 180), {'text': 'Longer first line\nShort', 'role': 'body', 'max_font': 12})
    pdf.save()
    positions = []
    PdfReader(stream).pages[0].extract_text(visitor_text=lambda text, cm, tm, font, size: positions.append((text.strip(), tm[4])) if text.strip() else None)
    assert len(positions) == 2
    assert positions[0][1] == positions[1][1]


def test_font_fit_reports_failure_instead_of_fake_minimum():
    overlay = load('apply_image_vector_text')
    overlay.register_fonts(overlay.default_font(False), overlay.default_font(True))
    with pytest.raises(ValueError, match='fit'):
        overlay.fitted_size(['W' * 200], overlay.FONT_REGULAR, 10, 1, 1)


def test_ocr_artifact_cannot_bypass_native_translation(tmp_path):
    runner = load('run_v6_job')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'pages': [{'blocks': [{'id': 'p0001-b0001', 'text': 'Real body', 'role': 'ocr-artifact', 'translation': '正文'}]}]}))
    assert runner._manifest_complete(manifest) is False


def test_empty_typography_check_is_not_a_pass(tmp_path):
    source = tmp_path / 'source.pdf'
    pdf = canvas.Canvas(str(source), pagesize=(200, 300))
    pdf.drawString(20, 150, 'Source paragraph')
    pdf.save()
    manifest = tmp_path / 'manifest.json'
    extracted = subprocess.run([sys.executable, str(SCRIPTS / 'pdf_translation_pipeline.py'), 'extract', '--input', str(source), '--manifest', str(manifest)], capture_output=True)
    assert extracted.returncode == 0, extracted.stderr
    rebuilt = tmp_path / 'rebuild.json'
    rebuilt.write_text('{"blocks": []}')
    report = tmp_path / 'qa.json'
    checked = subprocess.run([sys.executable, str(SCRIPTS / 'verify_native_typography.py'), str(source), str(manifest), str(rebuilt), '--report', str(report)], capture_output=True)
    assert checked.returncode != 0
    assert json.loads(report.read_text(encoding='utf-8'))['passed'] is False


def semantic_review():
    return {'source_sha256': 'source', 'candidate_sha256': 'candidate', 'adapter': 'native', 'selected_source_pages': [1], 'pages': [{'source_page': 1, 'status': 'passed', 'reviewed_source_ids': ['p0001-b0001', 'img/label1'], 'context_checked': 'Manufacturing tolerance and footnote checked against source.', 'corrections': [], 'unresolved_issues': []}]}


@pytest.mark.parametrize('defect', ['missing', 'stale', 'omitted_label', 'unresolved', 'empty_context', 'missing_page'])
def test_semantic_evidence_rejects_missing_stale_or_incomplete_review(defect):
    runner = load('run_v6_job')
    review = semantic_review()
    if defect == 'missing':
        review = None
    elif defect == 'stale':
        review['candidate_sha256'] = 'old'
    elif defect == 'omitted_label':
        review['pages'][0]['reviewed_source_ids'].pop()
    elif defect == 'unresolved':
        review['pages'][0]['unresolved_issues'] = ['Wrong unit']
    elif defect == 'empty_context':
        review['pages'][0]['context_checked'] = ''
    elif defect == 'missing_page':
        review['pages'] = []
    with pytest.raises(ValueError, match='translation review'):
        runner.validate_translation_review(review, {1: {'p0001-b0001', 'img/label1'}}, 'source', 'candidate')


def test_semantic_evidence_accepts_complete_source_bound_review():
    runner = load('run_v6_job')
    runner.validate_translation_review(semantic_review(), {1: {'p0001-b0001', 'img/label1'}}, 'source', 'candidate')


def test_cleanup_evidence_does_not_default_missing_metrics_to_zero():
    runner = load('run_v6_job')
    with pytest.raises(ValueError, match='cleanup evidence'):
        runner.validate_cleanup_evidence({'images': [{'id': 'img', 'changed_pixels': 5}]}, {'img'})


def test_native_runner_rejects_hidden_ocr_at_init(tmp_path):
    from reportlab.lib.utils import ImageReader
    runner = load('run_v6_job')
    source = tmp_path / 'scan.pdf'
    pdf = canvas.Canvas(str(source), pagesize=(200, 300))
    pdf.drawImage(ImageReader(Image.new('RGB', (200, 300), 'white')), 0, 0, 200, 300)
    text = pdf.beginText(20, 150)
    text.setTextRenderMode(3)
    text.textLine('Invisible OCR')
    pdf.drawText(text)
    pdf.save()
    with pytest.raises(ValueError, match='scan-only'):
        runner.init_job(source, tmp_path / 'jobs')


def test_runner_verification_requires_semantic_evidence_and_accepts_complete_job(tmp_path):
    runner = load('run_v6_job')
    source = tmp_path / 'source.pdf'
    pdf = canvas.Canvas(str(source), pagesize=(300, 400))
    pdf.drawString(30, 200, 'Tolerance is 5 mm.')
    pdf.save()
    job = runner.init_job(source, tmp_path / 'jobs')
    runner.build_native(job)
    metadata = tmp_path / 'metadata.json'
    metadata.write_text('{"images": []}')
    review = tmp_path / 'images.json'
    review.write_text('{"complete": true, "reviewed_image_ids": [], "images": [], "confirm_items": []}')
    runner.annotate_images(job, metadata, review)
    runner.build_images(job)
    runner.assemble(job)
    candidate_hash = runner._sha256(job / 'candidate.pdf')
    visual = {'candidate_sha256': candidate_hash, 'all_pages_rendered': True, 'reviewed_changed_regions': True, 'untranslated_clear_image_labels': 0, 'unreported_confirm_items': 0, 'reviewed_anomaly_pages': []}
    for key in ('text_overlap_failures', 'anchored_line_failures', 'unreadable_text_failures', 'missing_glyph_failures', 'content_failures', 'clipping_failures', 'structure_failures'):
        visual[key] = []
    visual_path = job / 'visual-review.json'
    visual_path.write_text(json.dumps(visual))
    with pytest.raises(ValueError, match='translation review'):
        runner.verify(job, False, visual_path)
    assert runner.state.load_job(job)['stage'] == 'assembled'
    semantic = semantic_review()
    semantic['source_sha256'] = runner._sha256(source)
    semantic['candidate_sha256'] = candidate_hash
    semantic['pages'][0]['reviewed_source_ids'] = ['p0001-b0001']
    semantic['pages'][0]['context_checked'] = 'Test fixture: tolerance remains 5 mm.'
    (job / 'translation-review.json').write_text(json.dumps(semantic))
    runner.verify(job, False, visual_path)
    assert runner.state.load_job(job)['stage'] == 'verified'
    assert json.loads((job / 'final-qa.json').read_text())['passed'] is True
    assert runner.resume(job)[0]['action'] == 'deliver'
    semantic['pages'][0]['context_checked'] = 'Rechecked the unchanged fixture: tolerance is still 5 mm.'
    (job / 'translation-review.json').write_text(json.dumps(semantic))
    runner.verify(job, False, visual_path)
    assert runner.resume(job)[0]['action'] == 'deliver'


def test_legacy_verified_boolean_is_not_delivery_evidence(tmp_path):
    runner = load('run_v6_job')
    source = tmp_path / 'source.pdf'
    pdf = canvas.Canvas(str(source))
    pdf.drawString(30, 200, 'Native source')
    pdf.save()
    job = runner.init_job(source, tmp_path / 'jobs')
    qa = job / 'final-qa.json'
    qa.write_text('{"passed":true}')
    runner.state.bind_artifact(job, 'final_qa', qa)
    old = runner.state.load_job(job)
    old['stage'] = 'verified'
    runner.state.save_job(job, old)
    assert runner.resume(job)[0]['action'] != 'deliver'
