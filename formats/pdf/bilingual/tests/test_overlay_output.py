from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bilingual_overlay.py"
FONT = Path(r"C:\Windows\Fonts\simhei.ttf")


@unittest.skipUnless(FONT.is_file(), "SimHei is required for the CJK overlay test")
class BilingualOverlayOutputTests(unittest.TestCase):
    def test_preserves_source_geometry_and_extractable_unicode(self) -> None:
        chinese_text = chr(0x4F60) + chr(0x597D)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.pdf"
            translations = temp / "translations.json"
            output = temp / "output.pdf"

            source_doc = pymupdf.open()
            source_page = source_doc.new_page(width=320, height=240)
            source_page.insert_text((36, 48), "Hello")
            source_doc.save(source)
            source_doc.close()

            translations.write_text(
                json.dumps(
                    [{"id": "p1-l1", "page": 0, "source": "Hello", "translation": chinese_text, "x": 36, "y": 72, "rotation": 90}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--translations",
                    str(translations),
                    "--output",
                    str(output),
                    "--font-file",
                    str(FONT),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            source_doc = pymupdf.open(source)
            output_doc = pymupdf.open(output)
            self.assertEqual(output_doc.page_count, source_doc.page_count)
            self.assertEqual(output_doc[0].rect, source_doc[0].rect)
            extracted = output_doc[0].get_text()
            self.assertIn("Hello", extracted)
            self.assertIn(chinese_text, extracted)
            lines = [line for block in output_doc[0].get_text("dict")["blocks"] if "lines" in block for line in block["lines"]]
            translated_line = next(line for line in lines if chinese_text in "".join(span["text"] for span in line["spans"]))
            output_doc.close()
            source_doc.close()
            self.assertAlmostEqual(0.0, translated_line["dir"][0], places=2)
            self.assertAlmostEqual(-1.0, translated_line["dir"][1], places=2)
            report = json.loads(output.with_suffix(".build-report.json").read_text(encoding="utf-8"))
            self.assertEqual("translate-pdf-bilingual-overlay", report["builder"])
            self.assertEqual(1, report["mapped_source_count"])

    def test_rejects_unmapped_or_duplicate_source_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.pdf"
            doc = pymupdf.open(); doc.new_page(); doc.save(source); doc.close()
            translations = temp / "translations.json"
            translations.write_text(json.dumps([
                {"id": "same", "page": 0, "source": "A", "translation": "甲", "x": 10, "y": 10},
                {"id": "same", "page": 0, "source": "B", "translation": "乙", "x": 20, "y": 20},
            ], ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), str(source), "-t", str(translations), "-o", str(temp / "out.pdf"), "--font-file", str(FONT)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(2, result.returncode)
            self.assertIn("unique", result.stderr)


if __name__ == "__main__":
    unittest.main()
