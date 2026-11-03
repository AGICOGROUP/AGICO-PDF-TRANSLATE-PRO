"""OCR envelopes may omit antialiased glyph edges; nearby rules stay intact."""
from pathlib import Path
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compile_translation import compile_translation


def inputs(tmp_path, dpi=200):
    path = tmp_path / 'source.png'
    image = Image.new('RGB', (120, 100), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((29, 29, 52, 42), fill='black')  # OCR misses one glyph-edge pixel.
    draw.line((10, 27, 100, 27), fill='black')  # Nearby cell rule must survive.
    image.save(path)
    extraction = {'source': 'source.pdf', 'source_sha256': 'a'*64,
        'selected_pages': [1], 'pages': [{'source_page': 1, 'pixel_width': 120,
        'pixel_height': 100, 'width_pt': 120, 'height_pt': 100,
        'dpi': dpi, 'render_path': str(path)}],
        'source_lines': [{'id': 'a', 'page': 1, 'text': 'Test',
                          'box': [30, 30, 52, 42], 'rotation': 0}]}
    return extraction, {'source_sha256': 'a'*64, 'groups': []}, {
        'source_sha256': 'a'*64, 'target_language': 'en',
        'regions': [{'id': 'body', 'ids': ['a'], 'translation': 'Output'}]}


def test_default_cleanup_covers_missed_glyph_edge_without_crossing_cell_rule(tmp_path):
    extraction, draft, decisions = inputs(tmp_path, dpi=400)
    result = compile_translation(extraction, draft, decisions)
    box = result['blocks'][0]['clean_boxes'][0]
    assert box[0] <= 29 and box[1] <= 29 and box[2] >= 53 and box[3] >= 43
    assert box[1] > 27  # Raster cell rule remains outside cleanup.


def test_explicit_visual_cleanup_boxes_are_not_expanded(tmp_path):
    extraction, draft, decisions = inputs(tmp_path)
    decisions['regions'][0]['clean_boxes'] = [[30, 30, 52, 42]]
    assert compile_translation(extraction, draft, decisions)['blocks'][0]['clean_boxes'] == [[30, 30, 52, 42]]


def test_default_cleanup_without_source_pixels_retains_exact_envelope(tmp_path):
    extraction, draft, decisions = inputs(tmp_path)
    extraction['pages'][0].pop('render_path')
    assert compile_translation(extraction, draft, decisions)['blocks'][0]['clean_boxes'] == [[30,30,52,42]]


def test_scaled_default_margin_clamps_to_page(tmp_path):
    extraction, draft, decisions = inputs(tmp_path, dpi=400)
    extraction['source_lines'][0]['box'] = [0, 0, 119, 99]
    assert compile_translation(extraction, draft, decisions)['blocks'][0]['clean_boxes'] == [[0, 0, 120, 100]]


def test_added_margin_does_not_erase_a_nearby_preserved_number(tmp_path):
    extraction, draft, decisions = inputs(tmp_path, dpi=400)
    extraction['source_lines'].append({'id':'number','page':1,'text':'123',
        'box':[54,29,75,43],'rotation':0})
    decisions['regions'].append({'id':'number','ids':['number'],
        'preserve_reason':'Drawing number retained in original raster.'})
    assert compile_translation(extraction,draft,decisions)['blocks'][0]['clean_boxes'][0][2] == 54


def test_added_margin_respects_source_pixel_protection_without_invented_transcription(tmp_path):
    extraction, draft, decisions = inputs(tmp_path, dpi=400)
    extraction['pages'][0]['ocr_review_candidates'] = [{'id':'numeric-band', 'box':[54,29,75,43]}]
    decisions['candidate_dispositions'] = {'numeric-band': {'disposition':'preserved_ink'}}
    assert compile_translation(extraction,draft,decisions)['blocks'][0]['clean_boxes'][0][2] == 54
