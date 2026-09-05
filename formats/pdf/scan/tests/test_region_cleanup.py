from __future__ import annotations

import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_scan import clean_background
from contracts import ManifestError, validate_manifest


def manifest_for(block: dict) -> dict:
    return {
        "source": "fixture.pdf",
        "source_sha256": "a" * 64,
        "selected_pages": [1],
        "pages": [{"source_page": 1, "pixel_width": 120, "pixel_height": 80}],
        "source_lines": [
            {"id": "l1", "page": 1, "box": [10, 10, 40, 20], "text": "Uno", "score": 1, "rotation": 0},
            {"id": "l2", "page": 1, "box": [10, 40, 40, 50], "text": "Dos", "score": 1, "rotation": 0},
        ],
        "blocks": [block],
    }


def region_block() -> dict:
    return {
        "id": "region-1",
        "page": 1,
        "source_line_ids": ["l1", "l2"],
        "source": "Uno Dos",
        "translation": "一 二",
        "role": "body",
        "status": "translated",
        "action": "replace",
        "box": [10, 10, 100, 55],
        "clean_boxes": [[10, 10, 40, 20], [10, 40, 40, 50]],
        "background": [255, 255, 255],
    }


class RegionCleanupTests(unittest.TestCase):
    def test_manifest_accepts_multiple_glyph_cleanup_boxes(self) -> None:
        report = validate_manifest(manifest_for(region_block()))
        self.assertEqual(report["translated_block_count"], 1)

    def test_cleanup_preserves_graphic_between_glyph_boxes(self) -> None:
        image = Image.new("RGB", (120, 80), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 40, 20), fill="black")
        draw.line((0, 30, 119, 30), fill="red", width=2)
        draw.rectangle((10, 40, 40, 50), fill="black")
        cleaned, report = clean_background(image, [region_block()])
        self.assertEqual(cleaned.getpixel((20, 15)), (255, 255, 255))
        self.assertEqual(cleaned.getpixel((20, 45)), (255, 255, 255))
        self.assertEqual(cleaned.getpixel((20, 30)), (255, 0, 0))
        self.assertEqual(report["outside_approved_pixel_changes"], 0)

    def test_manifest_rejects_both_cleanup_forms(self) -> None:
        block = region_block()
        block["clean_box"] = [10, 10, 40, 50]
        with self.assertRaisesRegex(ManifestError, "one of clean_box or clean_boxes"):
            validate_manifest(manifest_for(block))

    def test_legacy_single_cleanup_box_remains_valid(self) -> None:
        block = region_block()
        block.pop("clean_boxes")
        block["clean_box"] = [10, 10, 40, 50]
        validate_manifest(manifest_for(block))


if __name__ == "__main__":
    unittest.main()
