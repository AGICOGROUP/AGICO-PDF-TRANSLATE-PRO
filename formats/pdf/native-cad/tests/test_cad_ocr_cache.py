import importlib
from pathlib import Path
import sys

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cad_outline


def test_page_identity_is_independent_and_sensitive_to_resources_crop_rotation():
    cache = importlib.import_module('cad_cache')
    with pymupdf.open() as document:
        document.new_page(width=200, height=100)
        document.new_page(width=200, height=100)
        document[0].insert_text((20, 30), 'SILO')
        baseline = cache.page_fingerprint(document[0])
        document[1].insert_text((20, 30), 'Changed other page')
        assert cache.page_fingerprint(document[0]) == baseline
        # The content stream is unchanged; changing the shared font resource
        # must still invalidate OCR for the page that uses that resource.
        font_xref = document[0].get_fonts()[0][0]
        document.xref_set_key(font_xref, 'BaseFont', '/Courier')
        resource_changed = cache.page_fingerprint(document[0])
        assert resource_changed != baseline
        document[0].set_rotation(90)
        rotated = cache.page_fingerprint(document[0])
        assert rotated != resource_changed
        document[0].set_cropbox(pymupdf.Rect(0, 0, 150, 100))
        assert cache.page_fingerprint(document[0]) != rotated


def test_ocr_identity_tracks_dependency_and_model_content_without_engine(tmp_path, monkeypatch):
    cache = importlib.import_module('cad_cache')
    model = tmp_path / 'default.onnx'
    model.write_bytes(b'original')
    monkeypatch.setattr(cache, '_model_files', lambda: [model])
    monkeypatch.setattr(cache.metadata, 'version', lambda name: '1.0')
    baseline = cache.ocr_identity()
    monkeypatch.setattr(cache.metadata, 'version', lambda name: '2.0' if name == 'onnxruntime' else '1.0')
    assert cache.ocr_identity() != baseline
    monkeypatch.setattr(cache.metadata, 'version', lambda name: '1.0')
    model.write_bytes(b'updated model bytes')
    assert cache.ocr_identity() != baseline


def test_unchanged_model_content_is_not_rehashed_each_identity_call(tmp_path, monkeypatch):
    cache = importlib.import_module('cad_cache')
    model = tmp_path / 'default.onnx'
    model.write_bytes(b'model')
    monkeypatch.setattr(cache, '_model_files', lambda: [model])
    first = cache.ocr_identity()
    original_open = Path.open

    def disallow_model_read(path, *args, **kwargs):
        if path == model:
            raise AssertionError('unchanged model was rehashed')
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', disallow_model_read)
    assert cache.ocr_identity() == first


def test_lazy_engine_constructs_only_on_first_call():
    cache = importlib.import_module('cad_cache')
    calls = []

    def factory():
        calls.append('constructed')
        return lambda image: (image, None)

    engine = cache.LazyOCR(factory)
    assert calls == []
    assert engine('first') == ('first', None)
    assert engine('second') == ('second', None)
    assert calls == ['constructed']


def test_tiled_cache_reuses_unchanged_page_after_other_page_changes(tmp_path):
    calls = []

    def engine(image):
        calls.append(image.shape)
        return [], None

    with pymupdf.open() as document:
        document.new_page(width=100, height=100)
        document.new_page(width=100, height=100)
        document[0].insert_text((10, 20), 'First')
        cad_outline.extract_outline_records(document, tmp_path, 'whole-doc-before', [], engine=engine, dpi=72)
        assert len(calls) == 2
        document[1].insert_text((20, 30), 'Change')
        _, report = cad_outline.extract_outline_records(document, tmp_path, 'whole-doc-after', [], engine=engine, dpi=72)
    assert len(calls) == 3
    assert report['cache_hits'] == 1
    assert report['tiles_run'] == 1


def test_tiled_hit_does_not_initialize_lazy_engine(tmp_path):
    cache = importlib.import_module('cad_cache')
    with pymupdf.open() as document:
        document.new_page(width=100, height=100)
        cad_outline.extract_outline_records(document, tmp_path, 's', [], engine=lambda image: ([], None), dpi=72)

        def forbidden_factory():
            raise AssertionError('cache hit initialized OCR')

        _, report = cad_outline.extract_outline_records(document, tmp_path, 's', [],
                                                       engine=cache.LazyOCR(forbidden_factory), dpi=72)
        assert report['cache_hits'] == 1


@pytest.mark.parametrize('rotation,box,expected', [
    (90, [50, 20, 70, 60], [20, 30, 60, 50]),
    (180, [140, 50, 180, 70], [20, 30, 60, 50]),
    (270, [30, 140, 50, 180], [20, 30, 60, 50]),
])
def test_tiled_rotated_ocr_returns_unrotated_source_coordinates(tmp_path, rotation, box, expected):
    x0, y0, x1, y1 = box

    def engine(image):
        return [([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], 'Label', .99)], None

    with pymupdf.open() as document:
        page = document.new_page(width=200, height=100)
        page.set_rotation(rotation)
        records, _ = cad_outline.extract_outline_records(document, tmp_path, 's', [], engine=engine, dpi=72)
    assert records[0]['bbox'] == pytest.approx(expected)


def test_tiled_cache_invalidates_ocr_identity_and_dpi(tmp_path, monkeypatch):
    cache = importlib.import_module('cad_cache')
    calls = []

    def engine(image):
        calls.append(True)
        return [], None

    monkeypatch.setattr(cad_outline, 'ocr_identity', lambda: 'model-one')
    with pymupdf.open() as document:
        document.new_page(width=100, height=100)
        cad_outline.extract_outline_records(document, tmp_path, 's', [], engine=engine, dpi=72)
        monkeypatch.setattr(cad_outline, 'ocr_identity', lambda: 'model-two')
        cad_outline.extract_outline_records(document, tmp_path, 's', [], engine=engine, dpi=72)
        cad_outline.extract_outline_records(document, tmp_path, 's', [], engine=engine, dpi=144)
    assert len(calls) == 3


def test_document_layer_visibility_changes_fingerprint_with_actual_rendering(tmp_path):
    cache = importlib.import_module('cad_cache')
    visible, hidden = tmp_path / 'visible.pdf', tmp_path / 'hidden.pdf'
    with pymupdf.open() as document:
        page = document.new_page(width=200, height=100)
        layer = document.add_ocg('Labels', on=True)
        page.insert_text((20, 40), 'SILO', oc=layer)
        document.save(visible)
    with pymupdf.open(visible) as document:
        document.set_layer(-1, basestate='OFF', on=[], off=[layer])
        document.save(hidden)
    with pymupdf.open(visible) as before, pymupdf.open(hidden) as after:
        assert before[0].get_pixmap().samples != after[0].get_pixmap().samples
        assert before[0].get_text() != after[0].get_text()
        assert cache.page_fingerprint(before[0]) != cache.page_fingerprint(after[0])


def test_document_form_defaults_are_bound_and_pages_keep_distinct_identity(tmp_path):
    cache = importlib.import_module('cad_cache')
    source, changed = tmp_path / 'form.pdf', tmp_path / 'changed-form.pdf'
    with pymupdf.open() as document:
        page = document.new_page(width=200, height=100)
        widget = pymupdf.Widget()
        widget.field_name = 'description'
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.field_value = 'SILO'
        widget.rect = pymupdf.Rect(10, 10, 100, 40)
        page.add_widget(widget)
        document.new_page(width=200, height=100)
        document.save(source)
    with pymupdf.open(source) as document:
        document.xref_set_key(document.pdf_catalog(), 'AcroForm/NeedAppearances', 'true')
        document.save(changed)
    with pymupdf.open(source) as before, pymupdf.open(changed) as after:
        assert cache.page_fingerprint(before[0]) != cache.page_fingerprint(after[0])
        assert cache.page_fingerprint(before[1]) != cache.page_fingerprint(after[1])
        assert cache.page_fingerprint(after[0]) != cache.page_fingerprint(after[1])
