import io
import math
import sys
from pathlib import Path

import pdfplumber
import pytest
from PIL import Image
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_scan
from verify_scan import rendered_orientation_mismatches


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('rich', [False, True])
def test_rendered_reading_direction_matches_image_coordinates(rotation, rich, monkeypatch):
    monkeypatch.setattr(build_scan, 'REGULAR_FONT', 'Helvetica')
    block = {'id': 'label', 'translation': 'Direction', 'role': 'caption',
             'box': [50, 50, 250, 250], 'rotation': rotation,
             'min_font': 12, 'max_font': 12}
    page = {'width_pt': 300, 'height_pt': 300, 'pixel_width': 300,
            'pixel_height': 300, 'source_page': 1}
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(300, 300))
    if rich:
        block['rich_lines'] = [[{'type': 'text', 'text': 'Direction'}]]
        build_scan._draw_rich_block(pdf, block, page, Image.new('RGB', (300, 300)))
    else:
        build_scan._draw_block(pdf, block, page)
    pdf.save()
    with pdfplumber.open(stream) as document:
        matrix = document.pages[0].chars[0]['matrix']
        # PDF y increases upwards; source image y increases downwards.
        actual = math.degrees(math.atan2(-matrix[1], matrix[0])) % 360
        assert actual == pytest.approx(rotation)
        block['status'] = 'translated'
        assert rendered_orientation_mismatches(document.pages[0].chars, [block], page) == []
        block['rotation'] = (rotation + 180) % 360
        failures = rendered_orientation_mismatches(document.pages[0].chars, [block], page)
        assert failures[0]['actual_rotations'] == [rotation]


def test_missing_rendered_direction_is_not_a_pass():
    page = {'width_pt': 300, 'height_pt': 300, 'pixel_width': 300,
            'pixel_height': 300, 'source_page': 1}
    block = {'id': 'missing', 'status': 'translated', 'box': [10, 10, 90, 90], 'rotation': 90}
    assert rendered_orientation_mismatches([], [block], page)[0]['actual_rotations'] == []
