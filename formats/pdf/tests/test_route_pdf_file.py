from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[3]
ROUTER = ROOT / "formats" / "pdf" / "scripts" / "route_pdf_file.py"
BILINGUAL_ADAPTER = "formats/pdf/bilingual/SKILL.md"
NATIVE_CAD_ADAPTER = "formats/pdf/native-cad/SKILL.md"


class PdfRouterContractTests(unittest.TestCase):
    def run_router(
        self, source: Path, mode: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(ROUTER), str(source)]
        if mode is not None:
            command.extend(["--mode", mode])
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def make_text_pdf(self, path: Path, text: str = "Selectable text") -> Path:
        page = canvas.Canvas(str(path), pagesize=(300, 300))
        page.drawString(30, 250, text)
        page.save()
        return path

    def make_blank_pdf(self, path: Path, pages: int = 1) -> Path:
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=300, height=300)
        with path.open("wb") as stream:
            writer.write(stream)
        return path

    def make_large_drawing_pdf(self, path: Path, text: str | None = None) -> Path:
        page = canvas.Canvas(str(path), pagesize=(1684, 1191))
        page.rect(30, 30, 1624, 1131)
        for offset in range(20):
            page.line(100, 150 + offset * 35, 900, 150 + offset * 35)
        if text:
            page.drawString(1250, 100, text)
        page.save()
        return path

    def test_routes_native_text_pdf_to_native_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_text_pdf(Path(directory) / "native.pdf")
            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("native-text", report["pdf_type"])
            self.assertEqual("formats/pdf/native/SKILL.md", report["adapter"])
            self.assertEqual(1, report["native_text_pages"])

    def test_routes_scan_only_pdf_to_scan_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_blank_pdf(Path(directory) / "scan.pdf", pages=2)
            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("scan-only", report["pdf_type"])
            self.assertEqual("formats/pdf/scan/SKILL.md", report["adapter"])
            self.assertEqual(0, report["native_text_pages"])
            self.assertEqual(2, report["page_count"])

    def test_routes_large_native_engineering_drawing_to_bilingual_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_large_drawing_pdf(
                Path(directory) / "drawing.pdf", "SECTION A-A"
            )
            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("engineering-drawing", report["document_kind"])
            self.assertEqual(BILINGUAL_ADAPTER, report["adapter"])
            self.assertEqual("add_bilingual", report["translation_mode"])
            self.assertEqual("inspect_bilingual_coverage", report["next_action"])

    def test_explicit_replace_routes_native_engineering_drawing_to_native_cad(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_large_drawing_pdf(
                Path(directory) / "drawing.pdf", "SECTION A-A"
            )
            result = self.run_router(source, mode="replace")
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("native-text", report["pdf_type"])
            self.assertEqual("engineering-drawing", report["document_kind"])
            self.assertEqual(NATIVE_CAD_ADAPTER, report["adapter"])
            self.assertEqual("replace", report["translation_mode"])
            self.assertEqual("translate", report["next_action"])

    def test_explicit_replace_routes_mixed_engineering_drawing_to_native_cad(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text_page = self.make_large_drawing_pdf(root / "text.pdf", "SECTION A-A")
            blank_page = self.make_large_drawing_pdf(root / "blank.pdf")
            writer = PdfWriter()
            writer.add_page(PdfReader(text_page).pages[0])
            writer.add_page(PdfReader(blank_page).pages[0])
            source = root / "mixed-drawing.pdf"
            with source.open("wb") as stream:
                writer.write(stream)

            result = self.run_router(source, mode="replace")
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("mixed", report["pdf_type"])
            self.assertEqual("engineering-drawing", report["document_kind"])
            self.assertEqual(NATIVE_CAD_ADAPTER, report["adapter"])

    def test_explicit_bilingual_routes_normal_native_pdf_to_bilingual(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_text_pdf(Path(directory) / "report.pdf", "Report body")
            result = self.run_router(source, mode="bilingual")
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("document", report["document_kind"])
            self.assertEqual(BILINGUAL_ADAPTER, report["adapter"])
            self.assertEqual("add_bilingual", report["translation_mode"])

    def test_scan_only_pdf_never_routes_to_native_cad(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_large_drawing_pdf(Path(directory) / "drawing.pdf")
            result = self.run_router(source, mode="replace")
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("scan-only", report["pdf_type"])
            self.assertEqual("formats/pdf/scan/SKILL.md", report["adapter"])
            self.assertEqual("replace", report["translation_mode"])

    def test_routes_large_scan_engineering_drawing_to_scan_additive_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_large_drawing_pdf(Path(directory) / "drawing.pdf")
            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("engineering-drawing", report["document_kind"])
            self.assertEqual("formats/pdf/scan/SKILL.md", report["adapter"])
            self.assertEqual("add_bilingual", report["translation_mode"])
            self.assertEqual("inspect_bilingual_coverage", report["next_action"])

    def test_routes_extreme_portrait_scan_sheet_as_rotated_engineering_drawing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_blank_pdf(Path(directory) / "rotated-content-drawing.pdf")
            reader = PdfReader(source)
            writer = PdfWriter()
            writer.add_blank_page(width=842, height=1775)
            with source.open("wb") as stream:
                writer.write(stream)
            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("engineering-drawing", report["document_kind"])
            self.assertIn("image_internal_rotation_candidate", report["drawing_evidence"])
            self.assertEqual("add_bilingual", report["translation_mode"])

    def test_normal_report_keeps_replacement_route(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_text_pdf(Path(directory) / "report.pdf", "Report body")
            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("document", report["document_kind"])
            self.assertEqual("replace", report["translation_mode"])
            self.assertEqual("formats/pdf/native/SKILL.md", report["adapter"])

    def test_routes_mixed_pdf_to_native_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text_pdf = self.make_text_pdf(root / "text.pdf")
            blank_pdf = self.make_blank_pdf(root / "blank.pdf")
            writer = PdfWriter()
            writer.add_page(PdfReader(text_pdf).pages[0])
            writer.add_page(PdfReader(blank_pdf).pages[0])
            source = root / "mixed.pdf"
            with source.open("wb") as stream:
                writer.write(stream)

            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("mixed", report["pdf_type"])
            self.assertEqual("formats/pdf/native/SKILL.md", report["adapter"])
            self.assertEqual(1, report["native_text_pages"])
            self.assertEqual(2, report["page_count"])

    def test_rejects_encrypted_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "encrypted.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=300)
            writer.encrypt("secret")
            with source.open("wb") as stream:
                writer.write(stream)

            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            report = json.loads(result.stdout)
            self.assertTrue(report["encrypted"])
            self.assertIn("encrypted", report["error"])

    def test_rejects_fake_pdf_and_signature_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "fake.pdf"
            fake.write_bytes(b"not a pdf")
            result = self.run_router(fake)
            self.assertEqual(2, result.returncode)
            self.assertIn("signature", json.loads(result.stdout)["error"])

            wrong_extension = self.make_blank_pdf(root / "actual.bin")
            result = self.run_router(wrong_extension)
            self.assertEqual(2, result.returncode)
            self.assertTrue(json.loads(result.stdout)["extension_mismatch"])

    def test_scan_rotation_is_reported_and_stops_unsafe_routing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "rotated.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=300, height=300)
            page.rotate(90)
            with source.open("wb") as stream:
                writer.write(stream)

            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            report = json.loads(result.stdout)
            self.assertEqual([1], report["rotated_pages"])
            self.assertIn("normalize", report["error"])

    def test_rejects_zero_page_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "empty.pdf"
            writer = PdfWriter()
            with source.open("wb") as stream:
                writer.write(stream)

            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            report = json.loads(result.stdout)
            self.assertEqual(0, report["page_count"])
            self.assertIn("no pages", report["error"])


if __name__ == "__main__":
    unittest.main()
