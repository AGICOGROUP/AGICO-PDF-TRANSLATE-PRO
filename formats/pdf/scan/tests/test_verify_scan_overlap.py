from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import verify_scan  # noqa: E402


class WordOverlapTests(unittest.TestCase):
    def test_adjacent_lines_with_glyph_bbox_touch_are_not_overlap(self):
        upper = {"x0": 157.5, "x1": 402.3, "top": 78.2, "bottom": 93.5}
        lower = {"x0": 85.9, "x1": 538.6, "top": 92.0, "bottom": 107.3}
        self.assertFalse(verify_scan.words_materially_overlap(upper, lower))

    def test_words_occupying_same_region_are_overlap(self):
        first = {"x0": 211.8, "x1": 339.6, "top": 196.2, "bottom": 210.4}
        second = {"x0": 247.5, "x1": 333.3, "top": 197.0, "bottom": 211.3}
        self.assertTrue(verify_scan.words_materially_overlap(first, second))

    def test_crossing_vertical_and_horizontal_labels_are_not_overlap(self):
        horizontal = {
            "x0": 118.1, "x1": 536.6, "top": 413.1, "bottom": 426.6,
            "upright": True,
        }
        vertical = {
            "x0": 129.5, "x1": 134.4, "top": 418.2, "bottom": 426.3,
            "upright": False,
        }
        self.assertFalse(verify_scan.words_materially_overlap(horizontal, vertical))


if __name__ == "__main__":
    unittest.main()
