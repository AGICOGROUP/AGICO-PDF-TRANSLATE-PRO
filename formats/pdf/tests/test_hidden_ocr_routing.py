import importlib.util
from pathlib import Path
import sys

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


PDF = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_scan(path, visible=False, form=False):
    pdf = canvas.Canvas(str(path), pagesize=(300, 400))
    pdf.drawImage(ImageReader(Image.new('RGB', (300, 400), 'white')), 0, 0, 300, 400)
    pdf.saveState()
    if form:
        pdf.beginForm('ocr')
    text = pdf.beginText(20, 350)
    text.setTextRenderMode(3)
    text.textLine('Hidden OCR paragraph')
    pdf.drawText(text)
    if form:
        pdf.endForm()
        pdf.doForm('ocr')
    pdf.restoreState()
    if visible:
        pdf.drawString(20, 100, 'Visible native paragraph')
    pdf.save()


def test_hidden_ocr_routes_to_scan_in_both_entrypoints(tmp_path):
    source = tmp_path / 'scan.pdf'
    make_scan(source)
    router = load('ocr_router_test', PDF / 'scripts/route_pdf_file.py')
    classifier = load('ocr_classifier_test', PDF / 'scan/scripts/classify_pdf.py')
    assert router.route(source)[1]['pdf_type'] == 'scan-only'
    assert classifier.classify(source)['route'] == 'scan-only'


def test_hidden_form_text_is_not_native(tmp_path):
    source = tmp_path / 'form.pdf'
    make_scan(source, form=True)
    router = load('ocr_form_router_test', PDF / 'scripts/route_pdf_file.py')
    assert router.route(source)[1]['native_text_pages'] == 0


def test_visible_text_after_graphics_restore_remains_native(tmp_path):
    source = tmp_path / 'mixed.pdf'
    make_scan(source, visible=True)
    router = load('ocr_visible_router_test', PDF / 'scripts/route_pdf_file.py')
    assert router.route(source)[1]['pdf_type'] == 'native-text'


@pytest.mark.parametrize('mode', [3, 7])
@pytest.mark.parametrize('form', [False, True])
def test_small_visible_label_does_not_count_dense_hidden_ocr(tmp_path, mode, form):
    source = tmp_path / 'dense-hidden.pdf'
    pdf = canvas.Canvas(str(source), pagesize=(1684, 1191))
    pdf.drawString(20, 100, 'A 12')
    pdf.saveState()
    if form:
        pdf.beginForm('ocr')
    text = pdf.beginText(20, 1000)
    text.setTextRenderMode(mode)
    text.textLine('HiddenOCR ' * 1500)
    pdf.drawText(text)
    if form:
        pdf.endForm()
        pdf.doForm('ocr')
    pdf.restoreState()
    pdf.save()
    router = load('dense_hidden_router', PDF / 'scripts/route_pdf_file.py')
    # Exercise the pypdf-only fallback independently of optional acceleration.
    assert router.native_char_count(PdfReader(source).pages[0]) == 3
    code, result = router.route(source)
    assert code == 0
    assert result['native_char_counts'] == [3]
    assert result['document_kind'] == 'engineering-drawing'
    assert result['ocr_recommended_pages'] == [1]


def test_form_inherits_render_mode_without_leaking_into_parent(tmp_path):
    source = tmp_path / 'inherited-form.pdf'
    pdf = canvas.Canvas(str(source))
    pdf.beginForm('label')
    pdf.drawString(20, 100, 'FORM')
    pdf.endForm()
    pdf.saveState()
    pdf._code.append('3 Tr')
    pdf.doForm('label')
    pdf.restoreState()
    pdf.doForm('label')
    pdf.drawString(20, 130, 'END')
    pdf.save()
    router = load('inherited_form_router', PDF / 'scripts/route_pdf_file.py')
    assert router.native_char_count(PdfReader(source).pages[0]) == 7
    assert router.route(source)[1]['native_char_counts'] == [7]


@pytest.mark.parametrize('mode', range(8))
def test_text_probe_counts_fill_and_stroke_once(tmp_path, mode):
    pymupdf = pytest.importorskip('pymupdf')
    source = tmp_path / 'render-mode.pdf'
    pdf = canvas.Canvas(str(source))
    text = pdf.beginText(20, 100)
    text.setTextRenderMode(mode)
    text.textLine('Test 12')
    pdf.drawText(text)
    pdf.save()
    router = load('mode_router', PDF / 'scripts/route_pdf_file.py')
    with pymupdf.open(source) as document:
        count = router.native_char_count(PdfReader(source).pages[0], trace_page=document[0])
    assert count == (0 if mode in (3, 7) else 6)


def test_unavailable_optional_backend_keeps_routing(tmp_path, monkeypatch):
    source = tmp_path / 'no-backend.pdf'
    make_scan(source, visible=True, form=True)
    router = load('no_backend_router', PDF / 'scripts/route_pdf_file.py')
    monkeypatch.setitem(sys.modules, 'pymupdf', None)
    code, result = router.route(source)
    assert code == 0
    assert result['native_char_counts'] == [22]
    assert result['adapter'] == 'formats/pdf/native/SKILL.md'


def test_text_probe_failure_uses_pypdf_visible_count(tmp_path):
    source = tmp_path / 'probe-failure.pdf'
    make_scan(source, visible=True, form=True)
    router = load('failed_probe_router', PDF / 'scripts/route_pdf_file.py')

    class FailedPage:
        def get_texttrace(self):
            raise RuntimeError('text backend unavailable')

    assert router.native_char_count(PdfReader(source).pages[0], trace_page=FailedPage()) == 22


def test_router_uses_text_probe_without_full_pypdf_decoding(tmp_path, monkeypatch):
    pytest.importorskip('pymupdf')
    source = tmp_path / 'fast-native.pdf'
    make_scan(source, visible=True)
    router = load('fast_native_router', PDF / 'scripts/route_pdf_file.py')

    def unavailable_decode(*args, **kwargs):
        raise ValueError('full text decoder must not be needed for routing')

    monkeypatch.setattr('pypdf._page.PageObject.extract_text', unavailable_decode)
    code, result = router.route(source)
    assert code == 0
    assert result['native_char_counts'] == [22]


def test_optional_backend_open_failure_keeps_pypdf_route(tmp_path, monkeypatch):
    pymupdf = pytest.importorskip('pymupdf')
    source = tmp_path / 'open-failure.pdf'
    make_scan(source, visible=True)
    router = load('open_failure_router', PDF / 'scripts/route_pdf_file.py')

    def failed_open(*args, **kwargs):
        raise RuntimeError('optional runtime failure')

    monkeypatch.setattr(pymupdf, 'open', failed_open)
    code, result = router.route(source)
    assert code == 0
    assert result['native_char_counts'] == [22]


def test_optional_backend_cannot_hide_unreadable_content_stream(tmp_path):
    source = tmp_path / 'broken-stream.pdf'
    make_scan(source, visible=True)
    reader = PdfReader(source)
    writer = PdfWriter()
    page = writer.add_page(reader.pages[0])
    broken = DecodedStreamObject()
    broken.set_data(b'BT /F1 12 Tf (unterminated literal')
    page[NameObject('/Contents')] = broken
    with source.open('wb') as stream:
        writer.write(stream)
    router = load('broken_stream_router', PDF / 'scripts/route_pdf_file.py')
    code, result = router.route(source)
    assert code == 2
    assert result['adapter'] is None
    assert result['error'].startswith('cannot read PDF:')


def test_pypdf_fallback_tolerates_empty_font_resources():
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=400)
    content = DecodedStreamObject()
    content.set_data(b'BT /Missing 12 Tf (Label) Tj ET')
    page[NameObject('/Contents')] = content
    router = load('empty_resources_router', PDF / 'scripts/route_pdf_file.py')
    assert router.native_char_count(page) == 0
