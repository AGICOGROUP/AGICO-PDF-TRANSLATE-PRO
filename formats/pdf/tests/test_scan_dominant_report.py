import importlib.util
from pathlib import Path

import pymupdf

spec = importlib.util.spec_from_file_location('scan_report_router', Path(__file__).parents[1] / 'scripts/route_pdf_file.py')
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


def make_report(path, native_pages=1, image_pages=20):
    doc = pymupdf.open()
    image = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 2, 2), False)
    image.clear_with(230)
    for i in range(20):
        page = doc.new_page(width=595, height=842)
        if i < image_pages:
            page.insert_image(page.rect, pixmap=image)
        if i < native_pages:
            page.insert_text((20, 30), 'Selectable cover title')
    doc.save(path)


def test_scanned_report_with_one_native_cover_uses_preserving_scan_adapter(tmp_path):
    path = tmp_path / 'report.pdf'
    make_report(path)
    code, result = router.route(path, 'replace')
    assert code == 0
    assert result['pdf_type'] == 'mixed'
    assert result['adapter'] == router.SCAN_ADAPTER
    assert 'scan_dominant_report' in result['drawing_evidence']


def test_substantial_native_content_remains_native(tmp_path):
    path = tmp_path / 'native.pdf'
    make_report(path, native_pages=5)
    assert router.route(path, 'replace')[1]['adapter'] == router.NATIVE_ADAPTER


def test_rotated_scan_dominant_report_requires_normalization(tmp_path):
    path = tmp_path / 'rotated.pdf'
    make_report(path)
    with pymupdf.open(path) as doc:
        doc[1].set_rotation(90)
        doc.saveIncr()
    code, result = router.route(path, 'replace')
    assert code == 2
    assert 'normalize' in result['error']
    assert result['rotated_pages']


def test_all_rotated_pages_still_have_full_raster_coverage(tmp_path):
    path = tmp_path / 'all-rotated.pdf'
    make_report(path)
    with pymupdf.open(path) as doc:
        for page in doc:
            page.set_rotation(90)
        doc.saveIncr()
    code, result = router.route(path, 'replace')
    assert code == 2
    assert 'scan_dominant_report' in result['drawing_evidence']


def test_small_image_does_not_make_a_report_scan_dominant(tmp_path):
    path = tmp_path / 'mostly_blank.pdf'
    make_report(path, image_pages=2)
    assert router.route(path, 'replace')[1]['adapter'] == router.NATIVE_ADAPTER
