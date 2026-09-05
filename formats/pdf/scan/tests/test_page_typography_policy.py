from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_scan import apply_page_typography_policy, build_pdf, register_fonts, resolve_page_typography, typography_group


class PageTypographyPolicyTests(unittest.TestCase):
    def test_role_groups_are_stable(self) -> None:
        self.assertEqual(typography_group("title"), "major_title")
        self.assertEqual(typography_group("subheading"), "minor_title")
        self.assertEqual(typography_group("list_item"), "body")
        self.assertEqual(typography_group("caption"), "annotation")
        self.assertEqual(typography_group("header"), "header")
        self.assertEqual(typography_group("footer"), "footer")
        self.assertEqual(typography_group("table_cell"), "table")

    def test_page_policy_unifies_each_group(self) -> None:
        blocks = [
            {"id": "h1", "role": "title", "max_font": 18, "min_font": 11, "bold": True},
            {"id": "h2", "role": "heading", "max_font": 14, "min_font": 10, "bold": True},
            {"id": "h3", "role": "subheading", "max_font": 13, "min_font": 9, "bold": False},
            {"id": "b1", "role": "body", "max_font": 11, "min_font": 7, "bold": False},
            {"id": "b2", "role": "list_item", "max_font": 10, "min_font": 7, "bold": False},
        ]
        evidence = apply_page_typography_policy(blocks)
        bodies = [item for item in blocks if typography_group(item["role"]) == "body"]
        minors = [item for item in blocks if typography_group(item["role"]) == "minor_title"]
        self.assertEqual(len({item["max_font"] for item in bodies}), 1)
        self.assertEqual(len({item["bold"] for item in minors}), 1)
        self.assertGreaterEqual(evidence["major_title"]["font_size"], evidence["minor_title"]["font_size"])

    def test_dense_body_block_reduces_all_body_blocks_uniformly(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            render = root / "page.png"
            Image.new("RGB", (400, 400), "white").save(render)
            blocks = [
                {"id": "b1", "page": 1, "source_line_ids": ["l1"], "source": "甲", "translation": "Short body text", "role": "body", "status": "translated", "action": "replace", "box": [20, 20, 360, 80], "clean_box": [20, 20, 50, 40], "background": [255, 255, 255], "max_font": 12, "min_font": 7},
                {"id": "b2", "page": 1, "source_line_ids": ["l2"], "source": "乙", "translation": "A much longer translated body paragraph that requires wrapping across several lines inside a deliberately smaller container", "role": "list_item", "status": "translated", "action": "replace", "box": [20, 100, 240, 180], "clean_box": [20, 100, 50, 120], "background": [255, 255, 255], "max_font": 12, "min_font": 7},
            ]
            manifest = {
                "source": "fixture.pdf", "source_sha256": "a" * 64,
                "selected_pages": [1],
                "pages": [{"source_page": 1, "width_pt": 200, "height_pt": 200, "render_path": str(render), "pixel_width": 400, "pixel_height": 400, "dpi": 144}],
                "source_lines": [{"id": "l1", "page": 1, "box": [20, 20, 50, 40], "text": "甲", "score": 1}, {"id": "l2", "page": 1, "box": [20, 100, 50, 120], "text": "乙", "score": 1}],
                "blocks": blocks,
            }
            report = build_pdf(manifest, root / "out.pdf")
            sizes = {item["id"]: item["font_size"] for item in report["rendered_blocks"]}
            self.assertEqual(sizes["b1"], sizes["b2"])
            self.assertLess(sizes["b1"], 12)


    def test_common_fit_does_not_let_one_body_block_shrink_independently(self) -> None:
        register_fonts("en")
        blocks = [
            {"id": "short", "role": "body", "action": "replace", "translation": "Short text", "box": [20, 20, 380, 80], "max_font": 12, "min_font": 7, "bold": False},
            {"id": "dense", "role": "list_item", "action": "replace", "translation": "A deliberately dense paragraph that must wrap across several lines and therefore needs a smaller common page body size", "box": [20, 100, 300, 220], "max_font": 12, "min_font": 7, "bold": False},
            {"id": "footer", "role": "footer", "action": "replace", "translation": "Page 1", "box": [300, 360, 390, 390], "max_font": 5, "min_font": 5, "bold": False},
        ]
        page = {"width_pt": 200, "height_pt": 200, "pixel_width": 400, "pixel_height": 400}
        evidence = resolve_page_typography(blocks, page)
        self.assertEqual(blocks[0]["max_font"], blocks[1]["max_font"])
        self.assertEqual(blocks[0]["min_font"], blocks[1]["min_font"])
        self.assertEqual(evidence["body"]["font_size"], blocks[0]["max_font"])
        self.assertNotEqual(blocks[2]["max_font"], blocks[0]["max_font"])


if __name__ == "__main__":
    unittest.main()
