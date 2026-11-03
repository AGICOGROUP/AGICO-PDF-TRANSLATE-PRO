import io
import sys
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import build_scan


def test_explicit_signature_ink_is_preserved_while_black_caption_is_cleaned():
    image = Image.new('RGB', (80, 40), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 50, 20), fill='black')
    draw.line((20, 8, 42, 30), fill=(40, 45, 150), width=2)
    block = {'action': 'replace', 'clean_box': [5, 5, 60, 30],
             'background': [255, 255, 255], 'preserve_colored_ink': True}
    cleaned, _ = build_scan.clean_background(image, [block])
    source = np.asarray(image); target = np.asarray(cleaned)
    signature = (source[:, :, 2] - source[:, :, 0].astype(int)) > 40
    assert np.array_equal(source[signature], target[signature])
    assert tuple(target[15, 12]) == (255, 255, 255)


def test_optional_signature_policy_does_not_keep_colored_source_text_by_default():
    image = Image.new('RGB', (40, 40), (40, 45, 150))
    block = {'action': 'replace', 'clean_box': [0, 0, 39, 39], 'background': [255, 255, 255]}
    cleaned, _ = build_scan.clean_background(image, [block])
    assert cleaned.getpixel((20, 20)) == (255, 255, 255)


def test_local_cleanup_patch_cannot_cover_protected_original_numeric_ink(tmp_path):
    source = Image.new('RGB', (100, 100), 'white')
    ImageDraw.Draw(source).text((45, 43), '123', fill='black')
    source_path = tmp_path / 'source.png'; source.save(source_path)
    clean = source.copy();ImageDraw.Draw(clean).rectangle((10, 35, 80, 65), fill='white')
    page = {'width_pt': 100, 'height_pt': 100, 'render_path': str(source_path),
            'protected_boxes': [[43, 40, 67, 56]]}
    block = {'action': 'replace', 'clean_box': [10, 35, 80, 65]}
    output = tmp_path / 'out.pdf';c = canvas.Canvas(str(output), pagesize=(100, 100))
    c.drawImage(ImageReader(source), 0, 0, width=100, height=100)
    build_scan._draw_cleanup_patches(c, page, [block], clean)
    c.save()
    with pymupdf.open(output) as doc:
        pix = doc[0].get_pixmap(alpha=False)
        result = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    assert np.array_equal(np.asarray(source)[40:56, 43:67], np.asarray(result)[40:56, 43:67])


def test_overlapping_protection_windows_do_not_cancel_each_other():
    rectangles = build_scan._unprotected_rectangles((0, 0, 20, 20), [(2, 2, 12, 12), (8, 8, 18, 18)])
    for x in range(20):
        for y in range(20):
            painted = any(a <= x < c and b <= y < d for a,b,c,d in rectangles)
            protected = (2 <= x < 12 and 2 <= y < 12) or (8 <= x < 18 and 8 <= y < 18)
            assert painted != protected
