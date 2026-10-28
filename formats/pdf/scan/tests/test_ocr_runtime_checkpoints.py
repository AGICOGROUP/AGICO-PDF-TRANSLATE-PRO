from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import extract_scan


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    package = tmp_path / 'rapidocr'
    package.mkdir()
    for name in ('det', 'cls', 'rec'):
        (package / f'{name}.onnx').write_bytes(name.encode())
    config = package / 'config.yaml'
    config.write_text(''.join(f'{name}:\n  model_path: {name.lower()}.onnx\n'
                              for name in ('Det', 'Cls', 'Rec')), encoding='utf-8')
    engines = []
    def create_engine():
        engine = SimpleNamespace(text_recognizer=object())
        engines.append(engine)
        return engine
    monkeypatch.setitem(sys.modules, 'rapidocr_onnxruntime', SimpleNamespace(
        __file__=str(package / '__init__.py'), RapidOCR=create_engine))
    monkeypatch.setattr(extract_scan, 'configure_page_detector', lambda engine: None)
    return package, config, engines


def make_source(tmp_path):
    source = tmp_path / 'fresh.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(source)
    return source


@pytest.mark.parametrize('name', ['det', 'cls', 'rec'])
def test_runtime_signature_tracks_model_bytes_even_with_unchanged_file_stat(runtime, name):
    package, _, engines = runtime
    before = extract_scan.ocr_runtime_signature()
    selected = package / f'{name}.onnx'
    stat = selected.stat()
    selected.write_bytes(b'new')
    os.utime(selected, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert extract_scan.ocr_runtime_signature() != before
    assert engines == []  # Fingerprinting must not initialize any OCR engine.


def test_runtime_signature_tracks_configuration_without_onnx_initialization(runtime):
    _, config, engines = runtime
    before = extract_scan.ocr_runtime_signature()
    config.write_text(config.read_text(encoding='utf-8') + '\n# changed recognition parameters\n', encoding='utf-8')
    assert extract_scan.ocr_runtime_signature() != before
    assert engines == []


def test_runtime_signature_ignores_disabled_detector_and_classifier(runtime):
    package, config, engines = runtime
    config.write_text('Global:\n  use_text_det: false\n  use_angle_cls: false\n'
                      'Rec:\n  model_path: rec.onnx\n', encoding='utf-8')
    (package / 'det.onnx').unlink()
    (package / 'cls.onnx').unlink()
    signature = extract_scan.ocr_runtime_signature()
    assert set(signature['models']) == {'Rec'}
    assert engines == []


def test_runtime_signature_tracks_language_guard_implementation(runtime, tmp_path, monkeypatch):
    import ocr_language_guard

    implementation = tmp_path / 'guard.py'
    implementation.write_text('version one', encoding='utf-8')
    monkeypatch.setattr(ocr_language_guard, '__file__', str(implementation))
    before = extract_scan.ocr_runtime_signature()
    implementation.write_text('version two', encoding='utf-8')
    assert extract_scan.ocr_runtime_signature() != before


def test_checkpoint_invalidates_model_and_configuration_changes(runtime, tmp_path, monkeypatch):
    package, config, engines = runtime
    source = make_source(tmp_path)
    monkeypatch.setattr(extract_scan, '_ocr_pass', lambda *args: [])
    job = tmp_path / 'job'
    first = extract_scan.extract_selected_pages(source, [1], job, dpi=72)
    warm = extract_scan.extract_selected_pages(source, [1], job, dpi=72)
    assert not first['pages'][0]['ocr_cache_hit']
    assert warm['pages'][0]['ocr_cache_hit']
    assert len(engines) == 1
    (package / 'rec.onnx').write_bytes(b'new')
    changed_model = extract_scan.extract_selected_pages(source, [1], job, dpi=72)
    assert not changed_model['pages'][0]['ocr_cache_hit']
    config.write_text(config.read_text(encoding='utf-8') + '\n# changed threshold\n', encoding='utf-8')
    changed_config = extract_scan.extract_selected_pages(source, [1], job, dpi=72)
    assert not changed_config['pages'][0]['ocr_cache_hit']
    assert len(engines) == 3


@pytest.mark.parametrize('scales', [(), (0,), (-1,), (float('nan'),), (float('inf'),), (1, 2, 3)])
def test_extraction_rejects_invalid_scales_and_more_than_two_attempts(tmp_path, scales):
    source = make_source(tmp_path)
    with pytest.raises(ValueError, match='scale'):
        extract_scan.extract_selected_pages(source, [1], tmp_path / 'job', ocr_scales=scales)


@pytest.mark.parametrize('dual', [False, True])
def test_single_pass_default_and_explicit_dual_scale_preserve_audit_and_attempts(runtime, tmp_path, monkeypatch, dual):
    _, _, engines = runtime
    source = make_source(tmp_path)
    scales_seen = []
    def rejected(engine, image, scale):
        scales_seen.append(scale)
        return [{'box': [10, 10, 100, 30], 'quad': [], 'rotation': 0, 'text': 'uncertain',
                 'score': .1, 'scale': scale, 'review_required': True,
                 'ocr_attempts': 2 if engine._angle_retry_allowed else 1}]
    monkeypatch.setattr(extract_scan, '_ocr_pass', rejected)
    monkeypatch.setattr(extract_scan, 'uncovered_text_candidates', lambda *args: [[10, 80, 150, 100]])
    kwargs = {'ocr_scales': (1., 3.)} if dual else {}
    report = extract_scan.extract_selected_pages(source, [1], tmp_path / 'job', dpi=72, **kwargs)
    candidates = report['pages'][0]['ocr_review_candidates']
    assert scales_seen == ([1., 3.] if dual else [1.])
    assert engines[0]._angle_retry_allowed is (not dual)
    assert report['source_lines'] == []
    assert any(row['reason'] == 'recognition_rejected' and row['ocr_attempts'] == 2 for row in candidates)
    assert any(row['reason'] == 'uncovered_ink' for row in candidates)
    assert all(row['ocr_attempts'] <= 2 for row in candidates)
    assert json.loads((tmp_path / 'job' / 'page-checkpoints' / 'page-0001.json').read_text(encoding='utf-8'))['page']['ocr_review_candidates'] == candidates


@pytest.mark.parametrize('ocr_unavailable', [False, True])
def test_explicit_no_ocr_preserves_render_and_unresolved_visual_inventory(tmp_path, monkeypatch, capsys, ocr_unavailable):
    import verify_scan

    def forbidden(*args, **kwargs):
        raise AssertionError('no-ocr must not inspect or initialize the recognizer')
    monkeypatch.setitem(sys.modules, 'rapidocr_onnxruntime', None if ocr_unavailable else
                        SimpleNamespace(RapidOCR=forbidden))
    monkeypatch.setattr(extract_scan, 'ocr_runtime_signature', forbidden)
    source = tmp_path / 'fresh-visual-source.pdf'
    image = Image.new('RGB', (800, 300), 'white')
    draw = ImageDraw.Draw(image)
    # A fresh raster text-like line; ink audit must retain it for visual reading.
    for x in range(80, 680, 20):
        draw.rectangle((x, 100, x + 9, 118), fill='black')
    image.save(source, 'PDF', resolution=72)
    job = tmp_path / 'visual-job'
    monkeypatch.setattr(sys, 'argv', ['extract_scan.py', '--source', str(source), '--output',
                                      str(job), '--dpi', '72', '--no-ocr'])
    extract_scan.main()
    summary = json.loads(capsys.readouterr().out.splitlines()[-1])
    report = json.loads((job / 'extraction-report.json').read_text(encoding='utf-8'))
    page = report['pages'][0]
    assert summary['recognition_skipped'] is True
    assert summary['reading_method'] == 'visual_required'
    assert report['recognition_skipped'] is True
    assert page['reading_method'] == 'visual_required'
    assert report['source_lines'] == []
    assert report['source_sha256'] == extract_scan.sha256_file(source)
    assert page['media_box'] == [0, 0, 800, 300]
    assert (page['pixel_width'], page['pixel_height']) == (800, 300)
    render = Path(page['render_path'])
    assert render.exists()
    assert page['render_sha256'] == extract_scan.sha256_file(render)
    candidates = page['ocr_review_candidates']
    assert candidates
    assert all(row['ocr_attempts'] == 0 and row['reason'] == 'uncovered_ink' for row in candidates)
    review = {'source_sha256': report['source_sha256'], 'candidate_sha256': 'b', 'adapter': 'scan',
              'selected_source_pages': [1], 'pages': [{'source_page': 1, 'status': 'passed',
                  'reviewed_source_ids': [], 'context_checked': 'No recognition performed.',
                  'corrections': [], 'unresolved_issues': [], 'no_readable_text': 'No OCR lines'}]}
    assert verify_scan.validate_translation_review(review, report, report['source_sha256'], 'b')
    resumed = extract_scan.extract_selected_pages(source, [1], job, dpi=72, run_ocr=False)
    assert resumed['pages'][0]['ocr_cache_hit']
    assert resumed['pages'][0]['ocr_review_candidates'] == candidates
    assert resumed['recognition_skipped'] is True
