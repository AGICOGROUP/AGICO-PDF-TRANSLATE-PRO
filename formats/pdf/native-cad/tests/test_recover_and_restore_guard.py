from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "formats" / "pdf" / "native-cad" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import native_cad_pipeline  # noqa: E402
import recover_faint  # noqa: E402
from cad_outline import drawing_index  # noqa: E402
from native_cad_pipeline import path_hidden_in_source  # noqa: E402


class HiddenPathRestoreGuardTests(unittest.TestCase):
    """`redraw_paths` replays above existing content and cannot restore z-order."""

    def make_page(self, path: Path) -> Path:
        pdf = canvas.Canvas(str(path), pagesize=(842, 595))
        pdf.setLineWidth(1.0)
        pdf.setStrokeColorRGB(0, 0, 0)
        pdf.line(100, 300, 300, 300)          # buried by the wide light stroke next
        pdf.line(100, 200, 300, 200)          # stays visible
        pdf.setLineWidth(14.0)
        pdf.setStrokeColorRGB(0.984, 0.980, 0.957)
        pdf.line(100, 300, 300, 300)
        pdf.save()
        return path

    def find(self, page, y, width):
        index = drawing_index(page)
        for position, path in enumerate(index["paths"]):
            rect = pymupdf.Rect(path["rect"])
            colour = path.get("color")
            if (abs(rect.y0 - (595 - y)) < 2 and abs(rect.height) < 2
                    and (path.get("width") or 0) > width - 0.6 and colour):
                return index, position
        raise AssertionError("fixture line not found")

    def assertPath(self, name, y, width, expected):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_page(Path(directory) / name)
            document = pymupdf.open(source)
            try:
                page = document[0]
                index, position = self.find(page, y, width)
                self.assertIs(expected, path_hidden_in_source(
                    page, index["paths"][position], position, {}))
            finally:
                document.close()

    def test_buried_dark_line_is_refused(self):
        self.assertPath("buried.pdf", 300, 1.0, True)

    def test_visible_dark_line_is_allowed(self):
        self.assertPath("visible.pdf", 200, 1.0, False)

    def test_light_paint_is_never_an_artifact_risk(self):
        self.assertPath("light.pdf", 300, 14.0, False)


class FragmentMergeTests(unittest.TestCase):
    """Recovery must join fragments of one label without fusing two labels."""

    def label(self, text, box, confidence=0.99):
        return {"source": text, "bbox": list(box), "confidence": confidence}

    def test_identical_labels_in_different_columns_stay_separate(self):
        found = [self.label("Fecha", [583.4, 477.7, 598.5, 483.5]),
                 self.label("Fecha", [610.3, 487.7, 625.4, 493.5])]
        merged = recover_faint.merge_fragments(found)
        self.assertEqual(2, len(merged))

    def test_identical_labels_far_apart_on_the_sheet_stay_separate(self):
        found = [self.label("Direction", [121.4, 411.2, 129.0, 431.1]),
                 self.label("Direction", [282.6, 411.2, 290.4, 431.3])]
        merged = recover_faint.merge_fragments(found)
        self.assertEqual(2, len(merged))

    def test_vertical_fragments_of_one_label_merge(self):
        found = [self.label("rotation", [283.1, 387.9, 290.7, 406.2]),
                 self.label("rotation", [283.4, 387.9, 290.7, 405.3])]
        merged = recover_faint.merge_fragments(found)
        self.assertEqual(1, len(merged))
        self.assertAlmostEqual(290.7, merged[0]["bbox"][2], places=1)

    def test_horizontal_fragments_of_one_label_merge(self):
        found = [self.label("ESTANDA No.", [759.6, 195.6, 772.0, 200.4]),
                 self.label("ESTANDA No.", [771.5, 195.7, 790.0, 200.3])]
        merged = recover_faint.merge_fragments(found)
        self.assertEqual(1, len(merged))
        self.assertAlmostEqual(790.0, merged[0]["bbox"][2], places=1)


class NullTranslationTests(unittest.TestCase):
    """`str(None)` is "None", which must never read as a supplied translation."""

    def packet_pair(self, translation):
        record = {"id": "p0001-f00001", "page": 0, "source": "Fecha",
                  "bbox": [0, 0, 10, 4], "kind": "outline", "status": "pending"}
        decision = {"id": "p0001-f00001", "source": "Fecha", "status": "translated",
                    "translation": translation, "page": 0, "bbox": [0, 0, 10, 4],
                    "kind": "outline", "role": "body"}
        return ({"records": [record]}, {"records": [decision]})

    def test_null_translation_is_incomplete(self):
        inventory, packet = self.packet_pair(None)
        _, incomplete = native_cad_pipeline.validate_packet(inventory, packet)
        self.assertIn("p0001-f00001", incomplete)

    def test_empty_translation_is_incomplete(self):
        inventory, packet = self.packet_pair("")
        _, incomplete = native_cad_pipeline.validate_packet(inventory, packet)
        self.assertIn("p0001-f00001", incomplete)

    def test_real_translation_passes(self):
        inventory, packet = self.packet_pair("日期")
        _, incomplete = native_cad_pipeline.validate_packet(inventory, packet)
        self.assertNotIn("p0001-f00001", incomplete)


if __name__ == "__main__":
    unittest.main()
