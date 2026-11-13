import importlib.util
from pathlib import Path

import pymupdf


def router():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'route_pdf_file.py'
    spec = importlib.util.spec_from_file_location('rotation_route', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rotated_portrait_media_uses_visible_landscape_for_drawing(tmp_path):
    source = tmp_path / 'drawing.pdf'
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((200, 300), 'A1')
    for k in range(350):
        page.draw_line((40, 40 + k * 2), (550, 40 + k * 2))
    page.set_rotation(270)
    doc.save(source)
    code, result = router().route(source, 'replace')
    assert code == 0
    assert result['adapter'].endswith('native-cad/SKILL.md')


def test_rotated_scan_working_copy_keeps_pixels_and_original(tmp_path):
    source = tmp_path / 'scan.pdf'
    doc = pymupdf.open()
    page = doc.new_page(width=350, height=500)
    page.draw_rect((30, 40, 170, 250), color=(1, 0, 0), fill=(0, 1, 0))
    page.set_rotation(270)
    doc.save(source)
    original = source.read_bytes()
    before = pymupdf.open(source)[0].get_pixmap().samples
    output = tmp_path / 'normalized.pdf'
    code, result = router().route_with_normalization(source, 'replace', output)
    assert code == 0 and result['adapter'].endswith('scan/SKILL.md')
    assert source.read_bytes() == original
    assert pymupdf.open(output)[0].rotation == 0
    assert pymupdf.open(output)[0].get_pixmap().samples == before
    assert result['normalized_source'] == str(output.resolve())
    # Existing artifacts must never be silently overwritten.
    code, result = router().route_with_normalization(source, 'replace', output)
    assert code == 2 and 'new path' in result['error']
