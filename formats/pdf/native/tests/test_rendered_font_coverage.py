"""Regression: fitting and PDF text must use fonts covering the final string."""
import importlib.util
import io
import sys
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics

ROOT = Path(__file__).resolve().parents[1]
def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

rebuild = load('native_font_coverage_rebuild', 'native_selectable_rebuild.py')
pipeline = load('native_font_coverage_pipeline', 'pdf_translation_pipeline.py')

def block(number, source, target, y):
    box = [20, y, 230, y + 14]
    return {'id':f'p0001-b{number:04d}', 'source_text':source,
            'translation':target, 'bbox':box, 'role':'body-12',
            'style':{'font':'Arial', 'size':12, 'role_size':12,
                     'bold':False, 'italic':False, 'align':0,
                     'color_rgb':[0,0,0]},
            'lines':[{'bbox':box,'text':source,'characters':[],'runs':[]}],
            'runs':[{'font':'Arial','size':12,'bold':False}]}

class RenderedFontCoverageTests(unittest.TestCase):
    def overlay(self, blocks):
        page = {'page':1, 'width':400, 'height':300,
                'table_cells':[], 'image_boxes':[], 'blocks':blocks}
        rebuild.mark_cjk_styles({'pages':[page]})
        data, report = rebuild.make_overlay(page, pipeline, rebuild.register_fonts())
        self.assertEqual(1, len(PdfReader(io.BytesIO(data)).pages))
        return report

    def assert_visible_glyphs(self, report, target):
        draws = [draw for item in report for draw in item['draws']
                 if target in draw.get('rendered','')]
        self.assertTrue(draws, 'Expected reviewed wording is absent from the rendered text')
        for draw in draws:
            cmap = pdfmetrics.getFont(draw['font_name']).face.charToGlyph
            self.assertTrue(all(cmap.get(ord(c),0) for c in target if not c.isspace()),
                            f"{draw['font_name']} renders {target!r} with missing glyphs")

    def test_chinese_after_a_latin_value_has_visible_glyphs(self):
        report = self.overlay([block(1,'50%','50%',40),
                               block(2,'Base case','基准情景',58)])
        self.assert_visible_glyphs(report, '基准情景')

    def test_checkmark_and_chinese_share_a_glyph_capable_render_font(self):
        report = self.overlay([block(1,'✓ Complete','✓ 完成',40)])
        self.assert_visible_glyphs(report, '✓')
        self.assert_visible_glyphs(report, '完成')

    def test_math_identifiers_remain_visible(self):
        report = self.overlay([block(1,'μ ± ≤ →','μ ± ≤ →',40)])
        self.assert_visible_glyphs(report, 'μ')
        self.assert_visible_glyphs(report, '≤')

if __name__ == '__main__':
    unittest.main()
