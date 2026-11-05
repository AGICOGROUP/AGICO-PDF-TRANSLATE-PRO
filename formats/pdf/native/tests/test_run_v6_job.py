from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
import io
import copy
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont


RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "run_v6_job.py"


def make_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=(200, 200))
    pdf.drawString(20, 150, "Test")
    image = Image.new("RGB", (8, 8), (0, 90, 200))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    pdf.drawImage(ImageReader(io.BytesIO(stream.getvalue())), 20, 30, 40, 40)
    pdf.save()


def run(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *(str(value) for value in args)],
        capture_output=True,
        text=True,
    )


def prepare_annotation_job(root: Path) -> tuple[Path, str]:
    source = root / "source.pdf"
    make_pdf(source)
    initialized = run("init", source, "--jobs-root", root / "jobs")
    job_dir = Path(json.loads(initialized.stdout)["job_dir"])
    job_path = job_dir / "job.json"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job["stage"] = "native_translated"
    native_pdf = job_dir / "translated-native.pdf"
    make_pdf(native_pdf)
    job["artifacts"]["native_pdf"] = {
        "path": str(native_pdf.resolve()),
        "sha256": hashlib.sha256(native_pdf.read_bytes()).hexdigest(),
    }
    job_path.write_text(json.dumps(job), encoding="utf-8")
    inventory = json.loads(
        (job_dir / "images" / "image-inventory.json").read_text(encoding="utf-8")
    )
    return job_dir, inventory["images"][0]["id"]


def prepare_text_native_job(root: Path) -> Path:
    source = root / 'text-only.pdf'
    pdf = canvas.Canvas(str(source), pagesize=(240, 200))
    pdf.drawString(20, 150, 'Pumpe QX-62')
    pdf.drawString(20, 110, '4.8 kW')
    pdf.save()
    result = run('init', source, '--jobs-root', root / 'jobs',
                 '--source-language', 'de', '--target-language', 'en', '--fresh')
    assert result.returncode == 0, result.stderr
    job_dir = Path(json.loads(result.stdout)['job_dir'])
    path = job_dir / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    for page in manifest['pages']:
        for block in page['blocks']:
            block['translation'] = block['source_text'].replace('Pumpe', 'Pump')
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    result = run('build-native', job_dir)
    assert result.returncode == 0, result.stderr
    return job_dir


def routed_review(image_id: str, method: str = "deterministic_cleanup") -> dict:
    return {
        "complete": True,
        "reviewed_image_ids": [image_id],
        "images": [
            {
                "id": image_id,
                "asset_type": "raster_simple",
                "method": method,
                "expected_label_count": 1,
                "translated_label_count": 1,
                "preserved_label_count": 0,
                "confirm_count": 0,
                "structural_review_complete": True,
                "labels": [
                    {
                        "id": "label-1",
                        "source_text": "烟囱",
                        "translation": "Chimney",
                        "ocr_confidence": "high",
                        "method": method,
                        "status": "translated",
                    }
                ],
            }
        ],
        "confirm_items": [],
    }


class RunV6JobTests(unittest.TestCase):
    def test_resume_directs_bound_empty_inventory_to_assemble(self):
        with tempfile.TemporaryDirectory() as name:
            job_dir = prepare_text_native_job(Path(name))
            self.assertEqual(json.loads(run('resume', job_dir).stdout)['action'], 'assemble')

    def test_text_only_assemble_runs_real_image_stages_and_final_review_gates(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as name:
            job_dir = prepare_text_native_job(Path(name))
            result = run('assemble', job_dir)
            self.assertEqual(result.returncode, 0, result.stderr)
            job = json.loads((job_dir / 'job.json').read_text(encoding='utf-8'))
            self.assertEqual(job['stage'], 'assembled')
            for key in ('image_metadata', 'image_review', 'clean_image_report', 'candidate_pdf'):
                record = job['artifacts'][key]
                self.assertEqual(hashlib.sha256(Path(record['path']).read_bytes()).hexdigest(), record['sha256'])
            image_review = json.loads(Path(job['artifacts']['image_review']['path']).read_text(encoding='utf-8'))
            self.assertEqual(image_review, {'complete': True, 'reviewed_image_ids': [], 'images': [], 'confirm_items': []})
            self.assertEqual(json.loads(Path(job['artifacts']['clean_image_report']['path']).read_text(encoding='utf-8'))['images'], [])
            rejected = run('verify', job_dir)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('visual review report is required', rejected.stderr)
            candidate = Path(job['artifacts']['candidate_pdf']['path'])
            with pymupdf.open(candidate) as document:
                self.assertEqual(len(document), 1)
                self.assertIn('Pump QX-62', document[0].get_text())
                self.assertIn('4.8 kW', document[0].get_text())
                self.assertNotIn('Pumpe', document[0].get_text())
                self.assertTrue(document[0].get_pixmap().samples)
            manifest = json.loads((job_dir / 'manifest.json').read_text(encoding='utf-8'))
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            semantic = {'source_sha256': job['source']['sha256'], 'candidate_sha256': digest,
                        'adapter': 'native', 'selected_source_pages': [1], 'pages': [{
                            'source_page': 1, 'status': 'passed',
                            'reviewed_source_ids': [b['id'] for b in manifest['pages'][0]['blocks']],
                            'context_checked': 'Known fixture: Pumpe becomes Pump; QX-62 and4.8kW unchanged; actual saved page rendered and extracted.',
                            'corrections': [], 'unresolved_issues': []}]}
            visual = {'candidate_sha256': digest, 'all_pages_rendered': True,
                      'reviewed_changed_regions': True, 'reviewed_anomaly_pages': [],
                      'untranslated_clear_image_labels': 0, 'unreported_confirm_items': 0}
            for key in ('text_overlap_failures', 'anchored_line_failures', 'unreadable_text_failures',
                        'missing_glyph_failures', 'content_failures', 'clipping_failures', 'structure_failures'):
                visual[key] = []
            visual_path = job_dir / 'visual-review.json'
            visual_path.write_text(json.dumps(visual), encoding='utf-8')
            rejected = run('verify', job_dir, '--visual-review-report', visual_path)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('missing translation review', rejected.stderr)
            (job_dir / 'translation-review.json').write_text(json.dumps(semantic), encoding='utf-8')
            result = run('verify', job_dir, '--visual-review-report', visual_path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads((job_dir / 'final-qa.json').read_text(encoding='utf-8'))['passed'])
            self.assertEqual(json.loads((job_dir / 'job.json').read_text(encoding='utf-8'))['stage'], 'verified')

    def test_empty_image_shortcut_rejects_invalid_or_unbound_inventory(self):
        with tempfile.TemporaryDirectory() as name:
            job_dir = prepare_text_native_job(Path(name))
            job_path = job_dir / 'job.json'
            original_job = json.loads(job_path.read_text(encoding='utf-8'))
            inventory_path = Path(original_job['artifacts']['image_inventory']['path'])
            inventory_bytes = inventory_path.read_bytes()
            original_inventory = json.loads(inventory_bytes)
            native = Path(original_job['artifacts']['native_pdf']['path'])
            native_bytes = native.read_bytes()
            source = Path(original_job['source']['path'])
            source_bytes = source.read_bytes()
            for fault in ('missing', 'missing_record', 'bad_json', 'missing_images', 'wrong_images_type',
                          'wrong_source_hash', 'wrong_source_path', 'unbound_hash', 'source_changed', 'native_changed'):
                with self.subTest(fault=fault):
                    job = copy.deepcopy(original_job)
                    inventory = copy.deepcopy(original_inventory)
                    if fault == 'missing':
                        inventory_path.unlink()
                    elif fault == 'missing_record':
                        del job['artifacts']['image_inventory']
                    elif fault == 'bad_json':
                        inventory_path.write_text('{', encoding='utf-8')
                    elif fault == 'missing_images':
                        del inventory['images']
                    elif fault == 'wrong_images_type':
                        inventory['images'] = {}
                    elif fault == 'wrong_source_hash':
                        inventory['source_sha256'] = '0' * 64
                    elif fault == 'wrong_source_path':
                        inventory['source_path'] = str(Path(name) / 'other.pdf')
                    elif fault == 'unbound_hash':
                        inventory_path.write_bytes(inventory_bytes + b'\n')
                    elif fault == 'source_changed':
                        source.write_bytes(source_bytes + b'\nchanged')
                    elif fault == 'native_changed':
                        native.write_bytes(native_bytes + b'\nchanged')
                    if fault in ('missing_images', 'wrong_images_type', 'wrong_source_hash', 'wrong_source_path'):
                        inventory_path.write_text(json.dumps(inventory), encoding='utf-8')
                    if fault in ('bad_json', 'missing_images', 'wrong_images_type', 'wrong_source_hash', 'wrong_source_path'):
                        job['artifacts']['image_inventory']['sha256'] = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
                    job_path.write_text(json.dumps(job), encoding='utf-8')
                    result = run('assemble', job_dir)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(json.loads(job_path.read_text(encoding='utf-8'))['stage'], 'native_translated')
                    self.assertFalse((job_dir / 'image-review.json').exists())
                    self.assertFalse((job_dir / 'candidate.pdf').exists())
                    inventory_path.write_bytes(inventory_bytes)
                    source.write_bytes(source_bytes)
                    native.write_bytes(native_bytes)
                    job_path.write_text(json.dumps(original_job), encoding='utf-8')

    def test_nonempty_inventory_still_requires_explicit_image_review(self):
        with tempfile.TemporaryDirectory() as name:
            job_dir, _ = prepare_annotation_job(Path(name))
            self.assertEqual(json.loads(run('resume', job_dir).stdout)['action'], 'review_images')
            result = run('assemble', job_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((job_dir / 'image-review.json').exists())
            self.assertEqual(json.loads((job_dir / 'job.json').read_text(encoding='utf-8'))['stage'], 'native_translated')

    def test_init_writes_explicit_source_and_target_languages(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)

            result = run(
                "init",
                source,
                "--jobs-root",
                root / "jobs",
                "--source-language",
                "ru",
                "--target-language",
                "zh-CN",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            job_dir = Path(json.loads(result.stdout)["job_dir"])
            manifest = json.loads(
                (job_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("ru", manifest["source_language"])
            self.assertEqual("zh-CN", manifest["target_language"])

    def test_init_creates_source_bound_job_and_resume_requests_translation(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            result = run("init", source, "--jobs-root", root / "jobs")
            self.assertEqual(result.returncode, 0, result.stderr)
            job_dir = Path(json.loads(result.stdout)["job_dir"])
            job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
            self.assertIn("manifest", job["artifacts"])
            self.assertIn("image_inventory", job["artifacts"])
            resumed = run("resume", job_dir)
            self.assertEqual(resumed.returncode, 2)
            # The fixture contains target-language text only, so no translation
            # round trip is needed.
            self.assertEqual(json.loads(resumed.stdout)["action"], "build_native")

    def test_assemble_rejects_skipped_stages(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            initialized = run("init", source, "--jobs-root", root / "jobs")
            job_dir = Path(json.loads(initialized.stdout)["job_dir"])
            result = run("assemble", job_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("images_cleaned", result.stderr)

    def test_verify_rejects_extractable_cjk(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            initialized = run("init", source, "--jobs-root", root / "jobs")
            job_dir = Path(json.loads(initialized.stdout)["job_dir"])
            candidate = job_dir / "candidate.pdf"
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            pdf = canvas.Canvas(str(candidate), pagesize=(200, 200))
            pdf.setFont("STSong-Light", 12)
            pdf.drawString(20, 150, "中文残留")
            pdf.save()
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            job_path = job_dir / "job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["stage"] = "assembled"
            job["artifacts"]["candidate_pdf"] = {
                "path": str(candidate.resolve()),
                "sha256": digest,
            }
            job_path.write_text(
                json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            result = run("verify", job_dir, "--visual-review-complete")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("extractable CJK", result.stderr)

    def test_verify_allows_cjk_when_target_language_is_chinese(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            initialized = run("init", source, "--jobs-root", root / "jobs")
            job_dir = Path(json.loads(initialized.stdout)["job_dir"])
            manifest_path = job_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["target_language"] = "zh"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            candidate = job_dir / "candidate.pdf"
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            pdf = canvas.Canvas(str(candidate), pagesize=(200, 200))
            pdf.setFont("STSong-Light", 12)
            pdf.drawString(20, 150, "中文残留")
            pdf.save()
            job_path = job_dir / "job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["stage"] = "assembled"
            job["artifacts"]["manifest"]["sha256"] = hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest()
            job["artifacts"]["candidate_pdf"] = {
                "path": str(candidate.resolve()),
                "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
            }
            job_path.write_text(
                json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            result = run("verify", job_dir, "--visual-review-complete")
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("extractable CJK", result.stderr)
            self.assertIn("visual review report is required", result.stderr)

    def test_image_annotation_requires_review_of_every_original_image(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            initialized = run("init", source, "--jobs-root", root / "jobs")
            job_dir = Path(json.loads(initialized.stdout)["job_dir"])
            job_path = job_dir / "job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["stage"] = "native_translated"
            job_path.write_text(json.dumps(job), encoding="utf-8")
            metadata = root / "metadata.json"
            review = root / "review.json"
            metadata.write_text('{"images": []}', encoding="utf-8")
            review.write_text(
                '{"complete": true, "reviewed_image_ids": []}',
                encoding="utf-8",
            )
            result = run(
                "annotate-images",
                job_dir,
                "--metadata",
                metadata,
                "--review",
                review,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unreviewed original images", result.stderr)

    def test_verify_rejects_overlap_and_incomplete_exception_review(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            initialized = run("init", source, "--jobs-root", root / "jobs")
            job_dir = Path(json.loads(initialized.stdout)["job_dir"])
            candidate = job_dir / "candidate.pdf"
            make_pdf(candidate)
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            job_path = job_dir / "job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["stage"] = "assembled"
            job["artifacts"]["candidate_pdf"] = {
                "path": str(candidate.resolve()),
                "sha256": digest,
            }
            job_path.write_text(json.dumps(job), encoding="utf-8")
            report = root / "visual-review.json"
            report.write_text(
                json.dumps(
                    {
                        "all_pages_rendered": True,
                        "unreviewed_images": 1,
                        "untranslated_clear_image_labels": 1,
                        "logo_review_complete": False,
                        "header_footer_high_resolution_review_complete": False,
                        "text_overlap_failures": [{"page": 1, "region": "footer"}],
                    }
                ),
                encoding="utf-8",
            )
            result = run(
                "verify",
                job_dir,
                "--visual-review-report",
                report,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("visual delivery gates failed", result.stderr)

    def test_image_annotation_rejects_unknown_localization_method(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            job_dir, image_id = prepare_annotation_job(root)
            metadata = root / "metadata.json"
            review = root / "review.json"
            metadata.write_text(
                json.dumps({"images": [{"id": image_id, "regions": []}]}),
                encoding="utf-8",
            )
            review.write_text(
                json.dumps(routed_review(image_id, "uncontrolled_redraw")),
                encoding="utf-8",
            )

            result = run(
                "annotate-images", job_dir, "--metadata", metadata, "--review", review
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported image localization method", result.stderr)

    def test_image_annotation_rejects_incomplete_label_coverage(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            job_dir, image_id = prepare_annotation_job(root)
            metadata = root / "metadata.json"
            review = root / "review.json"
            metadata.write_text(
                json.dumps({"images": [{"id": image_id, "regions": []}]}),
                encoding="utf-8",
            )
            payload = routed_review(image_id)
            payload["images"][0]["expected_label_count"] = 2
            review.write_text(json.dumps(payload), encoding="utf-8")

            result = run(
                "annotate-images", job_dir, "--metadata", metadata, "--review", review
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("image label coverage mismatch", result.stderr)

    def test_image_annotation_requires_reported_confirm_item(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            job_dir, image_id = prepare_annotation_job(root)
            metadata = root / "metadata.json"
            review = root / "review.json"
            metadata.write_text(
                json.dumps({"images": [{"id": image_id, "regions": []}]}),
                encoding="utf-8",
            )
            payload = routed_review(image_id, "preserve_confirm")
            image = payload["images"][0]
            image["translated_label_count"] = 0
            image["preserved_label_count"] = 1
            image["confirm_count"] = 1
            image["labels"][0]["translation"] = ""
            image["labels"][0]["status"] = "confirm"
            review.write_text(json.dumps(payload), encoding="utf-8")

            result = run(
                "annotate-images", job_dir, "--metadata", metadata, "--review", review
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unreported confirm item", result.stderr)

    def test_image_annotation_rejects_clear_informational_caption_as_confirm(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            job_dir, image_id = prepare_annotation_job(root)
            metadata = root / "metadata.json"
            review = root / "review.json"
            metadata.write_text(json.dumps({"images": []}), encoding="utf-8")
            payload = routed_review(image_id, "preserve_confirm")
            image = payload["images"][0]
            image["translated_label_count"] = 0
            image["preserved_label_count"] = 1
            image["confirm_count"] = 1
            image["labels"][0].update(
                {
                    "source_text": "厂区效果图下方清晰可读的企业基地说明文字",
                    "translation": "",
                    "status": "confirm",
                    "preserve_reason": "informational_caption",
                }
            )
            payload["confirm_items"] = [{"label_id": "label-1"}]
            review.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            result = run(
                "annotate-images", job_dir, "--metadata", metadata, "--review", review
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("informational image text must be translated", result.stderr)

    def test_verify_requires_changed_region_review(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            initialized = run("init", source, "--jobs-root", root / "jobs")
            job_dir = Path(json.loads(initialized.stdout)["job_dir"])
            candidate = job_dir / "candidate.pdf"
            make_pdf(candidate)
            job_path = job_dir / "job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["stage"] = "assembled"
            job["artifacts"]["candidate_pdf"] = {
                "path": str(candidate.resolve()),
                "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
            }
            job_path.write_text(json.dumps(job), encoding="utf-8")
            report = root / "visual-review.json"
            report.write_text(
                json.dumps(
                    {
                        "all_pages_rendered": True,
                        "untranslated_clear_image_labels": 0,
                        "text_overlap_failures": [],
                    }
                ),
                encoding="utf-8",
            )

            result = run("verify", job_dir, "--visual-review-report", report)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("reviewed_changed_regions", result.stderr)


if __name__ == "__main__":
    unittest.main()
