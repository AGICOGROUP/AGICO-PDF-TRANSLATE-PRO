from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
import pytest

from PIL import Image
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[3]
BRIDGE = ROOT / "formats" / "image" / "scripts" / "image_pdf_bridge.py"
sys.path.insert(0, str(BRIDGE.parent))
import image_pdf_bridge as bridge


class ImagePdfBridgeTests(unittest.TestCase):
    def run_bridge(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BRIDGE), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_wrap_png_creates_one_page_pdf_and_records_source_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (320, 180), "white").save(source)
            pdf = root / "source.pdf"
            metadata = root / "image-metadata.json"

            result = self.run_bridge("wrap", str(source), str(pdf), str(metadata))

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, len(PdfReader(pdf).pages))
            report = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual([320, 180], report["pixel_size"])
            self.assertEqual("PNG", report["format"])
            self.assertEqual("RGB", report["mode"])

    def test_wrap_rejects_unsupported_image_format(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.gif"
            Image.new("RGB", (10, 10), "white").save(source)
            result = self.run_bridge("wrap", str(source), str(root / "x.pdf"), str(root / "x.json"))
            self.assertEqual(2, result.returncode)
            self.assertIn("PNG or JPEG", result.stderr)

    def test_unwrap_restores_png_pixel_size_and_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            image = Image.new("RGBA", (96, 64), (255, 255, 255, 0))
            for x in range(20, 76):
                for y in range(16, 48):
                    image.putpixel((x, y), (20, 40, 60, 255))
            image.save(source)
            pdf = root / "source.pdf"
            metadata = root / "image-metadata.json"
            self.assertEqual(0, self.run_bridge("wrap", str(source), str(pdf), str(metadata)).returncode)
            pdf.with_suffix(".build-report.json").write_text(json.dumps({
                "builder": "PDF-TRANSLATE-PRO-SCAN",
                "output_sha256": __import__("hashlib").sha256(pdf.read_bytes()).hexdigest(),
            }), encoding="utf-8")

            output = root / "translated.final.png"
            result = self.run_bridge("unwrap", str(pdf), str(metadata), str(output))

            self.assertEqual(0, result.returncode, result.stderr)
            with Image.open(output) as translated:
                self.assertEqual((96, 64), translated.size)
                self.assertEqual("RGBA", translated.mode)
                self.assertEqual(0, translated.getpixel((0, 0))[3])
                self.assertEqual(255, translated.getpixel((48, 32))[3])

    def test_unwrap_rejects_pdf_without_official_scan_build_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (40, 30), "white").save(source)
            pdf, metadata = root / "source.pdf", root / "image-metadata.json"
            self.assertEqual(0, self.run_bridge("wrap", str(source), str(pdf), str(metadata)).returncode)
            result = self.run_bridge("unwrap", str(pdf), str(metadata), str(root / "out.png"))
            self.assertEqual(2, result.returncode)
            self.assertIn("official scan", result.stderr.lower())

    def test_unwrap_requires_same_output_format_as_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jpg"
            Image.new("RGB", (80, 50), "white").save(source)
            pdf = root / "source.pdf"
            metadata = root / "image-metadata.json"
            self.assertEqual(0, self.run_bridge("wrap", str(source), str(pdf), str(metadata)).returncode)
            pdf.with_suffix(".build-report.json").write_text(json.dumps({
                "builder": "PDF-TRANSLATE-PRO-SCAN",
                "output_sha256": __import__("hashlib").sha256(pdf.read_bytes()).hexdigest(),
            }), encoding="utf-8")

            result = self.run_bridge("unwrap", str(pdf), str(metadata), str(root / "wrong.png"))
            self.assertEqual(2, result.returncode)
            self.assertIn("same image format", result.stderr)


def test_unwrap_cannot_overwrite_original_image(tmp_path, monkeypatch):
    source = tmp_path/'source.png'
    Image.new('RGB',(20,20),'white').save(source)
    pdf, metadata = tmp_path/'source.pdf', tmp_path/'image-metadata.json'
    bridge.wrap(source, pdf, metadata)
    before = source.read_bytes()
    monkeypatch.setattr(bridge, 'find_pdftoppm', lambda: pytest.fail('Must reject before render'))
    with pytest.raises(bridge.BridgeError, match='overwrite source'):
        bridge.unwrap(pdf, metadata, source)
    assert source.read_bytes() == before


def test_wrap_rejects_source_changed_during_decode_without_carrier_or_metadata(tmp_path, monkeypatch):
    source = tmp_path/'source.png'
    Image.new('RGB',(20,20),'white').save(source)
    original = bridge.ImageOps.exif_transpose
    def changed(image):
        result = original(image)
        source.write_bytes(source.read_bytes() + b'source changed')
        return result
    monkeypatch.setattr(bridge.ImageOps, 'exif_transpose', changed)
    with pytest.raises(bridge.BridgeError, match='Source changed'):
        bridge.wrap(source, tmp_path/'source.pdf', tmp_path/'image-metadata.json')
    assert sorted(path.name for path in tmp_path.iterdir()) == ['source.png']


@pytest.mark.parametrize('mode', ['RGBA', 'P'])
def test_wrap_rejects_derived_alpha_overwriting_source_before_any_writes(tmp_path, mode):
    source = tmp_path/'image-metadata-alpha.png'
    if mode == 'RGBA':
        image = Image.new('RGBA',(20,20),(30,60,90,120))
        image.save(source)
    else:
        image = Image.new('P',(20,20),0)
        image.putpalette([30,60,90, 90,60,30] + [0]*762)
        image.putpixel((10,10),1)
        image.save(source, transparency=0)
    original = source.read_bytes()
    original_hash = bridge.sha256_file(source)
    with pytest.raises(bridge.BridgeError, match='alpha.*distinct'):
        bridge.wrap(source, tmp_path/'source.pdf', tmp_path/'image-metadata.json')
    assert source.read_bytes() == original
    assert bridge.sha256_file(source) == original_hash
    with Image.open(source) as preserved:
        assert preserved.mode == mode
    assert sorted(path.name for path in tmp_path.iterdir()) == ['image-metadata-alpha.png']


@pytest.mark.parametrize('protected', ['carrier', 'metadata'])
def test_wrap_rejects_derived_alpha_aliasing_other_job_inputs(tmp_path, protected):
    source = tmp_path/'source.png'
    Image.new('RGBA',(20,20),(30,60,90,120)).save(source)
    metadata = tmp_path/'image-metadata.json'
    alpha = tmp_path/'image-metadata-alpha.png'
    carrier = tmp_path/'source.pdf'
    if protected == 'carrier':
        carrier = alpha
    else:
        metadata.write_bytes(b'previous metadata')
        alpha.hardlink_to(metadata)
    originals = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    with pytest.raises(bridge.BridgeError, match='alpha.*distinct'):
        bridge.wrap(source, carrier, metadata)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == originals


def test_failed_unwrap_render_keeps_candidate_and_removes_partial_render(tmp_path, monkeypatch):
    source = tmp_path/'source.png'
    Image.new('RGB',(20,20),'white').save(source)
    pdf, metadata = tmp_path/'source.pdf', tmp_path/'image-metadata.json'
    bridge.wrap(source, pdf, metadata)
    pdf.with_suffix('.build-report.json').write_text(json.dumps({
        'builder':'PDF-TRANSLATE-PRO-SCAN', 'output_sha256':bridge.sha256_file(pdf)}))
    output = tmp_path/'result.png'
    Image.new('RGB',(20,20),'black').save(output)
    before = output.read_bytes()
    monkeypatch.setattr(bridge, 'find_pdftoppm', lambda: 'synthetic-renderer')
    def failed_render(command, **kwargs):
        Path(command[-1] + '.png').write_bytes(b'partial render')
        return subprocess.CompletedProcess(command, 1, stderr='synthetic render failure')
    monkeypatch.setattr(bridge.subprocess, 'run', failed_render)
    with pytest.raises(bridge.BridgeError, match='render failure'):
        bridge.unwrap(pdf, metadata, output)
    assert output.read_bytes() == before
    assert not list(tmp_path.glob('.*-render-*'))


if __name__ == "__main__":
    unittest.main()
