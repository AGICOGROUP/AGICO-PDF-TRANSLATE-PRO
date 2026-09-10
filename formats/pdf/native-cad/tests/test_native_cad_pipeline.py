from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pymupdf
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, red


ROOT = Path(__file__).resolve().parents[4]
PIPELINE = ROOT / "formats" / "pdf" / "native-cad" / "scripts" / "native_cad_pipeline.py"
FONT = Path(r"C:\Windows\Fonts\simhei.ttf")


class NativeCadPipelineTests(unittest.TestCase):
    def make_drawing(self, path: Path) -> Path:
        pdf = canvas.Canvas(str(path), pagesize=(842, 595))
        pdf.rect(24, 24, 794, 547)
        pdf.line(80, 300, 760, 300)
        pdf.line(420, 80, 420, 515)
        pdf.setStrokeColor(red)
        pdf.line(80, 338, 250, 338)
        pdf.setFillColor(black)
        pdf.drawString(90, 330, "SECTION A-A")
        pdf.drawString(90, 280, "Ø20 mm")
        pdf.save()
        return path

    def make_form_drawing(self, path: Path) -> Path:
        pdf = canvas.Canvas(str(path), pagesize=(842, 595))
        pdf.rect(24, 24, 794, 547)
        pdf.beginForm("CAD-LABEL", 0, 0, 180, 40)
        pdf.drawString(5, 15, "FORM LABEL")
        pdf.endForm()
        pdf.saveState()
        pdf.translate(100, 300)
        pdf.doForm("CAD-LABEL")
        pdf.restoreState()
        pdf.save()
        return path

    def run_pipeline(self, *args: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PIPELINE), *(str(arg) for arg in args)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def red_pixel_count(self, page: pymupdf.Page, rect: pymupdf.Rect) -> int:
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(4, 4), clip=rect, alpha=False)
        samples = pixmap.samples
        return sum(
            1
            for offset in range(0, len(samples), pixmap.n)
            if samples[offset] > 180
            and samples[offset + 1] < 100
            and samples[offset + 2] < 100
        )

    def prepare(self, source: Path, job: Path) -> dict[str, object]:
        result = self.run_pipeline("prepare", source, "--job-dir", job)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads((job / "source-inventory.json").read_text(encoding="utf-8"))

    def test_prepare_binds_source_and_exports_stable_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_drawing(root / "drawing.pdf")
            job = root / "job"

            inventory = self.prepare(source, job)

            expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(expected_hash, inventory["source_sha256"])
            self.assertEqual(source.read_bytes(), (job / "SOURCE.pdf").read_bytes())
            records = inventory["records"]
            self.assertEqual(["p0001-s00001", "p0001-s00002"], [r["id"] for r in records])
            self.assertEqual("pending", records[0]["status"])
            self.assertEqual("protected", records[1]["status"])
            self.assertEqual("Ø20 mm", records[1]["source"])
            packet = json.loads((job / "translation-packet.json").read_text(encoding="utf-8"))
            self.assertEqual(["p0001-s00001"], [r["id"] for r in packet["records"]])

    def test_apply_rejects_missing_translations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_drawing(root / "drawing.pdf")
            job = root / "job"
            self.prepare(source, job)
            packet_path = job / "translation-packet.json"

            result = self.run_pipeline("apply", job, "--packet", packet_path)

            self.assertNotEqual(0, result.returncode)
            report = json.loads((job / "apply-report.json").read_text(encoding="utf-8"))
            self.assertFalse(report["passed"])
            self.assertEqual(["p0001-s00001"], report["incomplete_records"])
            self.assertFalse((job / "translated-native-cad.pdf").exists())

    def test_fit_failure_saves_preview_with_original_failed_label(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.pdf'
            pdf = canvas.Canvas(str(source), pagesize=(842, 595))
            pdf.drawString(90, 330, 'NORMAL LABEL')
            pdf.drawString(90, 280, 'FAILED LABEL')
            # Small vector strokes stand in for a font-outline label.
            pdf.line(100, 190, 105, 180)
            pdf.line(105, 180, 110, 190)
            pdf.line(80, 200, 760, 200)
            pdf.save()
            job = root / 'job'
            self.prepare(source, job)
            packet_path = job / 'translation-packet.json'
            packet = json.loads(packet_path.read_text(encoding='utf-8'))
            inventory_path = job / 'source-inventory.json'
            inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
            outline = {'id': 'p0001-o-test', 'page': 0, 'kind': 'outline',
                       'source': 'OUTLINED LABEL', 'bbox': [98, 403, 112, 417],
                       'font_size': 12, 'rotation': 0, 'color': 0, 'status': 'pending'}
            inventory['records'].append(outline)
            inventory_path.write_text(json.dumps(inventory), encoding='utf-8')
            packet['records'].append({**outline, 'role': 'body',
                                      'cover_review': {'approved': True, 'text_only': True,
                                                       'white_background': True, 'source_text_paths': True,
                                                       'note': 'Known small outline-stroke fixture.'}})
            for record in packet['records']:
                record.update(status='translated', translation='Translated')
                if record['source'] == 'FAILED LABEL':
                    record['translation'] = 'too long ' * 2000
                    failed_id = record['id']
                if record['source'] == 'OUTLINED LABEL':
                    record['translation'] = 'too long ' * 2000
            packet_path.write_text(json.dumps(packet), encoding='utf-8')
            result = self.run_pipeline('apply', job, '--packet', packet_path, '--font-file', FONT)
            self.assertNotEqual(0, result.returncode)
            report = json.loads((job / 'apply-report.json').read_text(encoding='utf-8'))
            self.assertFalse(report['passed'])
            self.assertEqual([failed_id, 'p0001-o-test'], report['source_retained_ids'])
            preview = Path(report['preview'])
            with pymupdf.open(preview) as doc, pymupdf.open(source) as original:
                self.assertIn('Translated', doc[0].get_text())
                self.assertIn('FAILED LABEL', doc[0].get_text())
                self.assertNotIn('NORMAL LABEL', doc[0].get_text())
                self.assertEqual(len(original[0].get_drawings()), len(doc[0].get_drawings()))
                for record in inventory['records']:
                    if record['id'] in report['source_retained_ids']:
                        clip = pymupdf.Rect(record['bbox'])
                        self.assertEqual(original[0].get_pixmap(clip=clip).samples,
                                         doc[0].get_pixmap(clip=clip).samples)
            verified = self.run_pipeline('verify', job, '--candidate', preview)
            self.assertNotEqual(0, verified.returncode)
            self.assertFalse(json.loads((job / 'final-qa.json').read_text())['passed'])

    def test_apply_replaces_text_without_removing_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_drawing(root / "drawing.pdf")
            job = root / "job"
            self.prepare(source, job)
            packet_path = job / "translation-packet.json"
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            packet["records"][0].update(
                translation="A-A剖面", status="translated"
            )
            packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

            result = self.run_pipeline(
                "apply", job, "--packet", packet_path, "--font-file", FONT
            )

            self.assertEqual(0, result.returncode, result.stderr)
            candidate = job / "translated-native-cad.pdf"
            with pymupdf.open(source) as source_doc, pymupdf.open(candidate) as candidate_doc:
                self.assertGreaterEqual(
                    len(candidate_doc[0].get_drawings()), len(source_doc[0].get_drawings())
                )
                record = json.loads(
                    (job / "source-inventory.json").read_text(encoding="utf-8")
                )["records"][0]
                rect = pymupdf.Rect(record["bbox"])
                self.assertGreaterEqual(
                    self.red_pixel_count(candidate_doc[0], rect),
                    self.red_pixel_count(source_doc[0], rect),
                )
                text = candidate_doc[0].get_text()
            self.assertIn("A-A剖面", text)
            self.assertNotIn("SECTION A-A", text)
            self.assertIn("Ø20 mm", text)
            report = json.loads((job / "apply-report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["passed"])
            self.assertEqual([], report["fit_failures"])

    def test_verify_requires_candidate_bound_complete_visual_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_drawing(root / "drawing.pdf")
            job = root / "job"
            self.prepare(source, job)
            packet_path = job / "translation-packet.json"
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            packet["records"][0].update(translation="A-A剖面", status="translated")
            packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
            applied = self.run_pipeline(
                "apply", job, "--packet", packet_path, "--font-file", FONT
            )
            self.assertEqual(0, applied.returncode, applied.stderr)
            candidate = job / "translated-native-cad.pdf"

            incomplete = self.run_pipeline("verify", job, "--candidate", candidate)
            self.assertNotEqual(0, incomplete.returncode)
            self.assertFalse(json.loads((job / "final-qa.json").read_text())["passed"])

            review = job / "visual-review.json"
            review.write_text(
                json.dumps(
                    {
                        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                        "all_pages_reviewed": True,
                        "all_changed_regions_reviewed": True,
                        "visible_foreign_descriptive_text": [],
                        "text_overlap_failures": [],
                        "line_or_graphic_damage": [],
                        "notes": "",
                    }
                ),
                encoding="utf-8",
            )
            verified = self.run_pipeline(
                "verify", job, "--candidate", candidate, "--visual-review", review
            )
            self.assertEqual(0, verified.returncode, verified.stderr)
            qa = json.loads((job / "final-qa.json").read_text(encoding="utf-8"))
            self.assertTrue(qa["passed"])
            self.assertEqual([], qa["failures"])
            preview = job / 'review' / 'page-0001.png'
            rendered_at = preview.stat().st_mtime_ns
            repeated = self.run_pipeline('verify', job, '--candidate', candidate, '--visual-review', review)
            self.assertEqual(0, repeated.returncode, repeated.stderr)
            self.assertEqual(rendered_at, preview.stat().st_mtime_ns)
            visual = json.loads(review.read_text(encoding='utf-8'))
            visual['line_or_graphic_damage'] = [{'page': 1, 'reason': 'Broken process connection'}]
            review.write_text(json.dumps(visual), encoding='utf-8')
            damaged = self.run_pipeline('verify', job, '--candidate', candidate, '--visual-review', review)
            self.assertNotEqual(0, damaged.returncode)
            self.assertIn('line_or_graphic_damage', json.loads((job / 'final-qa.json').read_text())['failures'])

    def test_form_xobject_text_is_inventoried_and_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_form_drawing(root / "form-drawing.pdf")
            job = root / "job"
            inventory = self.prepare(source, job)
            self.assertEqual(["FORM LABEL"], [r["source"] for r in inventory["records"]])
            packet_path = job / "translation-packet.json"
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            packet["records"][0].update(translation="表单标签", status="translated")
            packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

            result = self.run_pipeline(
                "apply", job, "--packet", packet_path, "--font-file", FONT
            )

            self.assertEqual(0, result.returncode, result.stderr)
            with pymupdf.open(job / "translated-native-cad.pdf") as candidate:
                text = candidate[0].get_text()
                self.assertNotIn("FORM LABEL", text)
                self.assertIn("表单标签", text)


if __name__ == "__main__":
    unittest.main()
