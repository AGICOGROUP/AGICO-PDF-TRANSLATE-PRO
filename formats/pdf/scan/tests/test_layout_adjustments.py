from __future__ import annotations

import sys
import importlib.util
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Adapters intentionally have same-named CLI helpers. A joint repository test
# must exercise this adapter's file regardless of another adapter's sys.path.
spec = importlib.util.spec_from_file_location('pdf_scan_layout_adjustments_tests', SCRIPT_DIR / 'layout_adjustments.py')
layout_adjustments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout_adjustments)
LayoutAdjustmentError = layout_adjustments.LayoutAdjustmentError
validate_layout_adjustment = layout_adjustments.validate_layout_adjustment


BASE = {"page": 1, "source_box": [100, 100, 300, 200], "original_box": [100, 100, 300, 200], "target_box": [160, 110, 320, 190], "scale": 0.8, "trigger": "text_does_not_fit", "fit_failure": True, "approved_background_regions": [[100, 100, 300, 200]]}


class LayoutAdjustmentTests(unittest.TestCase):
    def test_explicit_vacated_image_area_can_receive_target_text(self):
        item = dict(BASE, vacate_for_text=True)
        validate_layout_adjustment(item, 600, 800, [[110, 110, 140, 140]], original_protected_boxes=[])

    def test_vacating_does_not_allow_erasing_source_content(self):
        item = dict(BASE, vacate_for_text=True)
        with self.assertRaisesRegex(LayoutAdjustmentError, "original image"):
            validate_layout_adjustment(item, 600, 800, [], original_protected_boxes=[[110,110,140,140]])

    def test_vacating_still_protects_target_text(self):
        item = dict(BASE, vacate_for_text=True)
        with self.assertRaisesRegex(LayoutAdjustmentError, "target image"):
            validate_layout_adjustment(item, 600, 800, [[200,120,240,150]], original_protected_boxes=[])

    def test_valid_scan_layout_adjustment_passes(self) -> None:
        validate_layout_adjustment(dict(BASE), 600, 800, [])

    def test_page_escape_fails(self) -> None:
        item = dict(BASE); item["target_box"] = [500, 110, 660, 190]
        with self.assertRaises(LayoutAdjustmentError): validate_layout_adjustment(item, 600, 800, [])

    def test_different_source_crop_fails(self) -> None:
        item = dict(BASE); item["source_box"] = [110, 100, 310, 200]
        with self.assertRaisesRegex(LayoutAdjustmentError, "source_box"):
            validate_layout_adjustment(item, 600, 800, [])

    def test_original_image_containing_protected_text_fails(self) -> None:
        with self.assertRaisesRegex(LayoutAdjustmentError, "original image"):
            validate_layout_adjustment(dict(BASE), 600, 800, [[110, 110, 140, 140]])


if __name__ == "__main__": unittest.main()
