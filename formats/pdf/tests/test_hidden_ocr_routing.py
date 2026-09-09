import importlib.util
from pathlib import Path

from PIL import Image
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
