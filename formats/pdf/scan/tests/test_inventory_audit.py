import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


def test_legacy_inventory_audit_is_document_wide_stable_and_keeps_existing_ids(tmp_path):
    from audit_scan_inventory import audit_inventory
    image = Image.new('RGB', (1000, 500), 'white')
    draw = ImageDraw.Draw(image)
    for y in (100, 300):
        for x in range(100, 800, 18):
            draw.rectangle((x, y, x+8, y+15), fill='black')
    path = tmp_path / 'source.png'
    image.save(path)
    manifest = {'selected_pages': [1, 2], 'pages': [
        {'source_page': p, 'render_path': str(path)} for p in (1, 2)],
        'source_lines': [{'id': f'p{p}-l1', 'page': p, 'box': [90, 90, 815, 125]} for p in (1, 2)]}
    original = json.dumps(manifest)
    updated, added = audit_inventory(manifest)
    assert json.dumps(manifest) == original
    assert {c['page'] for c in added} == {1, 2}
    assert all(c['box'][1] > 250 for c in added)
    assert all(c['ocr_attempts'] == 0 for c in added), 'Ink audit does not spend an OCR attempt'
    second, new = audit_inventory(updated)
    assert not new
    assert second == updated


def test_inventory_audit_rejects_changed_source_pixels(tmp_path):
    from audit_scan_inventory import audit_inventory
    import pytest
    path = tmp_path / 'source.png'
    Image.new('RGB', (20, 20), 'white').save(path)
    manifest = {'selected_pages': [1], 'source_lines': [], 'pages': [
        {'source_page': 1, 'render_path': str(path), 'render_sha256': '0' * 64}]}
    with pytest.raises(ValueError, match='hash mismatch'):
        audit_inventory(manifest)
