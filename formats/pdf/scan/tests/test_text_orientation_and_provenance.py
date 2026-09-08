from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from contracts import ManifestError, validate_manifest  # noqa: E402
from extract_scan import _ocr_pass, merge_ocr_records, rotation_from_quad  # noqa: E402
from verify_scan import evaluate_evidence, requires_cjk_residual_gate  # noqa: E402
import extract_scan  # noqa: E402
import build_scan  # noqa: E402


def manifest(rotation: int = 90, block_rotation: int | None = 90) -> dict:
    block = {
        "id": "p01-label",
        "page": 1,
        "source_line_ids": ["p01-l001"],
        "source": "POGLED A",
        "translation": "视图A",
        "role": "caption",
        "status": "translated",
        "action": "add_bilingual",
        "source_preserved": True,
        "placement": "blank_panel",
        "companion_kind": "title_block",
        "companion_anchor_box": [80, 80, 290, 360],
        "box": [300, 300, 480, 350],
        "color": [0, 0.3, 0.6],
        "min_font": 7,
        "max_font": 10,
    }
    if block_rotation is not None:
        block["rotation"] = block_rotation
    return {
        "source": "source.pdf",
        "source_sha256": "a" * 64,
        "target_language": "zh",
        "selected_pages": [1],
        "pages": [{
            "source_page": 1,
            "width_pt": 600,
            "height_pt": 800,
            "pixel_width": 1200,
            "pixel_height": 1600,
            "render_path": "source.png",
        }],
        "source_lines": [{
            "id": "p01-l001", "page": 1, "box": [100, 100, 180, 260],
            "text": "POGLED A", "score": 0.99, "rotation": rotation,
        }],
        "blocks": [block],
    }


class TextOrientationAndProvenanceTests(unittest.TestCase):
    def test_page_detector_keeps_full_400_dpi_page_resolution(self):
        class ResizeConfig:
            limit_side_len = 736
            limit_type = "min"

        class Detector:
            preprocess_op = [ResizeConfig()]

        class Engine:
            text_detector = Detector()

        engine = Engine()

        extract_scan.configure_page_detector(engine)

        self.assertEqual(8000, engine.text_detector.preprocess_op[0].limit_side_len)
        self.assertEqual("max", engine.text_detector.preprocess_op[0].limit_type)

    def test_merge_drops_contained_word_fragment_from_other_scale(self):
        records = [
            {
                "box": [100, 100, 500, 140],
                "quad": [[100, 100], [500, 100], [500, 140], [100, 140]],
                "rotation": 0,
                "text": "fabricacion y suministro de durmientes",
                "score": 0.91,
                "scale": 1.0,
            },
            {
                "box": [205, 102, 300, 138],
                "quad": [[205, 102], [300, 102], [300, 138], [205, 138]],
                "rotation": 0,
                "text": "suministro",
                "score": 0.96,
                "scale": 3.0,
            },
        ]

        merged = merge_ocr_records(records)

        self.assertEqual(["fabricacion y suministro de durmientes"], [item["text"] for item in merged])

    def test_merge_drops_corrupted_contained_fragment_from_other_scale(self):
        records = [
            {
                "box": [100, 100, 500, 140],
                "quad": [[100, 100], [500, 100], [500, 140], [100, 140]],
                "rotation": 0,
                "text": "METROPOLITANO LINEA B",
                "score": 0.84,
                "scale": 1.0,
            },
            {
                "box": [205, 102, 300, 138],
                "quad": [[205, 102], [300, 102], [300, 138], [205, 138]],
                "rotation": 0,
                "text": "METROPC",
                "score": 0.91,
                "scale": 3.0,
            },
        ]

        merged = merge_ocr_records(records)

        self.assertEqual(["METROPOLITANO LINEA B"], [item["text"] for item in merged])

    def test_merge_keeps_distinct_line_inside_larger_multiline_box(self):
        records = [
            {"box": [100, 100, 500, 220], "quad": [], "rotation": 0,
             "text": "marcan los planos de fabricacion", "score": 0.91, "scale": 1.0},
            {"box": [110, 105, 490, 140], "quad": [], "rotation": 0,
             "text": "El acero de refuerzo se colocara", "score": 0.96, "scale": 3.0},
        ]

        merged = merge_ocr_records(records)

        self.assertEqual(2, len(merged))

    def test_ocr_pass_converts_pillow_image_to_numpy_for_rapidocr(self):
        class NumpyOnlyEngine:
            def __call__(self, image):
                if not isinstance(image, np.ndarray):
                    raise TypeError("OCR engine requires a NumPy array")
                return ([[[0, 0], [20, 0], [20, 10], [0, 10]], "TEST", 0.99],), None

        records = _ocr_pass(NumpyOnlyEngine(), Image.new("RGB", (40, 20), "white"), 1.0)

        self.assertEqual("TEST", records[0]["text"])

    def test_chinese_target_uses_cjk_capable_font_and_skips_source_cjk_gate(self):
        self.assertIn("msyh", build_scan.CJK_REGULAR_FONT_PATHS[0].name.lower())
        self.assertFalse(requires_cjk_residual_gate("zh"))
        self.assertTrue(requires_cjk_residual_gate("en"))

    def test_rotation_from_quad_detects_cardinal_directions(self):
        self.assertEqual(0, rotation_from_quad([[10, 10], [50, 10], [50, 20], [10, 20]]))
        self.assertEqual(90, rotation_from_quad([[10, 10], [10, 50], [0, 50], [0, 10]]))
        self.assertEqual(180, rotation_from_quad([[50, 20], [10, 20], [10, 10], [50, 10]]))
        self.assertEqual(270, rotation_from_quad([[10, 50], [10, 10], [20, 10], [20, 50]]))
        # OCR engines may normalize point order while retaining a tall text box.
        self.assertEqual(90, rotation_from_quad([[10, 10], [20, 10], [20, 80], [10, 80]]))

    def test_manifest_rejects_missing_or_mismatched_translation_rotation(self):
        with self.assertRaisesRegex(ManifestError, "rotation"):
            validate_manifest(manifest(block_rotation=None))
        with self.assertRaisesRegex(ManifestError, "rotation"):
            validate_manifest(manifest(block_rotation=0))

    def test_final_evidence_rejects_unofficial_builder(self):
        data = manifest()
        report = evaluate_evidence(
            manifest=data,
            extracted_by_page={1: "视图A"},
            build_report={
                "rendered_blocks": [{"id": "p01-label", "font_size": 9, "complete": True}],
                "outside_approved_pixel_changes": 0,
            },
            output_page_count=1,
            geometry_match=True,
            visual_review={
                "all_pages_rendered": True,
                "reviewed_changed_regions": True,
                "reviewed_anomaly_pages": [],
                "text_overlap_failures": [],
                "clipping_failures": [],
                "untranslated_clear_labels": 0,
            },
            residual_cjk=[],
            font_embedding_failures=[],
            automated_overlap_failures=[],
        )
        self.assertFalse(report["passed"])
        self.assertFalse(report["official_pipeline"])

    def test_summary_panel_cannot_assign_multiple_source_labels_to_one_translation(self):
        data = manifest()
        data["source_lines"].append({
            "id": "p01-l002", "page": 1, "box": [100, 300, 220, 360],
            "text": "DETALJ B", "score": 0.99, "rotation": 90,
        })
        data["blocks"][0]["source_line_ids"].append("p01-l002")
        with self.assertRaisesRegex(ManifestError, "one-to-one"):
            validate_manifest(data)

    def test_blank_panel_requires_nearby_structural_anchor(self):
        data = manifest()
        data["blocks"][0].pop("companion_anchor_box")
        with self.assertRaisesRegex(ManifestError, "companion_anchor_box"):
            validate_manifest(data)

        data = manifest()
        data["blocks"][0]["box"] = [800, 1000, 1000, 1100]
        with self.assertRaisesRegex(ManifestError, "too far"):
            validate_manifest(data)

        coverage = validate_manifest(manifest())
        self.assertEqual(1, coverage["translated_block_count"])


if __name__ == "__main__":
    unittest.main()
