import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "apply_image_vector_text.py"
)
SPEC = importlib.util.spec_from_file_location("apply_image_vector_text", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class EmptyImageTextTests(unittest.TestCase):
    def test_default_fonts_include_chinese_glyphs(self):
        MODULE.register_fonts(MODULE.default_font(False), MODULE.default_font(True))
        regular = MODULE.pdfmetrics.getFont(MODULE.FONT_REGULAR)
        bold = MODULE.pdfmetrics.getFont(MODULE.FONT_BOLD)
        self.assertNotEqual(0, regular.face.charToGlyph.get(ord("中"), 0))
        self.assertNotEqual(0, bold.face.charToGlyph.get(ord("中"), 0))

    def test_empty_text_cleans_raster_without_drawing_duplicate_label(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            image_path = root / "clean.png"
            Image.new("RGB", (20, 20), "white").save(image_path)
            MODULE.register_fonts(
                MODULE.default_font(False), MODULE.default_font(True)
            )
            result = MODULE.make_overlay(
                100,
                100,
                [
                    {
                        "output": str(image_path),
                        "placement": [10, 10, 40, 40],
                        "regions": [
                            {
                                "box": [2, 2, 18, 10],
                                "text": "",
                                "max_font": 5,
                            }
                        ],
                    }
                ],
                root,
            )
            self.assertTrue(result.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
