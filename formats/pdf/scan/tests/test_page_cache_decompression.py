"""Fresh fixtures exercising pypdf's actual bounded stream decompressor."""
from pathlib import Path
import sys

import pymupdf
import pypdf
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_scan


def fresh_manifest(tmp_path):
    manifest = {"source": "fresh.pdf", "source_sha256": "b" * 64,
                "target_language": "en", "selected_pages": [1, 2, 3],
                "pages": [], "blocks": [], "source_lines": []}
    for number in manifest["selected_pages"]:
        image = tmp_path / f"source-{number}.png"
        Image.new("RGB", (256, 256), (number * 30, 100, 200)).save(image)
        manifest["pages"].append({"source_page": number, "render_path": str(image),
            "width_pt": 256, "height_pt": 256, "pixel_width": 256, "pixel_height": 256})
        manifest["source_lines"].append({"id": f"l{number}", "page": number,
            "text": "Label", "box": [20, 20, 100, 40], "rotation": 0})
        manifest["blocks"].append({"id": f"b{number}", "page": number,
            "source_line_ids": [f"l{number}"], "source": "Label", "translation": f"Page {number}",
            "status": "translated", "action": "replace", "role": "body",
            "box": [20, 20, 200, 60], "clean_box": [20, 20, 100, 40], "rotation": 0})
    return manifest


def pixels(path):
    with pymupdf.open(path) as doc:
        return [page.get_pixmap().samples for page in doc]


def test_warm_cache_survives_real_decompression_limit(tmp_path):
    manifest = fresh_manifest(tmp_path)
    output = tmp_path / "translated.pdf"
    build_scan.build_pdf(manifest, output)
    expected = pixels(output)
    cache = tmp_path / "page-build-cache"
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in cache.glob("*")}
    # A small fixture crosses the same limit as a >75 MB raster in production.
    # This only lowers the protection for this test and pytest restores it.
    original_config = pypdf.get_configuration()
    with pypdf.apply_configuration(zlib_maximum_output_length=100_000):
        with pypdf.PdfReader(cache / "page-0001.pdf") as reader:
            image = next(iter(reader.pages[0]["/Resources"]["/XObject"].values())).get_object()
            with pytest.raises(pypdf.errors.LimitReachedError):
                image.get_data()
        result = build_scan.build_pdf(manifest, output)
        assert pypdf.get_configuration().zlib_maximum_output_length == 100_000
    assert result["page_cache_hits"] == [1, 2, 3]
    assert result["dirty_pages"] == []
    assert result["object_deduplication"] == "skipped_decompression_limit"
    assert pixels(output) == expected
    assert pypdf.get_configuration() == original_config
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == state for p, state in before.items())


def test_hash_bound_unreadable_page_cache_rebuilds_locally(tmp_path):
    manifest = fresh_manifest(tmp_path)
    output = tmp_path / "translated.pdf"
    initial = build_scan.build_pdf(manifest, output)
    expected = pixels(output)
    cache_pdf = Path(initial["pages"][1]["page_pdf_path"])
    cache_pdf.write_bytes(b"%PDF-1.4\nnot a page tree\n%%EOF")
    # Keep metadata internally authentic to prove parser failure, not hash failure,
    # is handled as a miss. The other page caches must remain reusable.
    import json
    import hashlib
    meta = json.loads(cache_pdf.with_suffix(".json").read_text(encoding="utf-8"))
    meta["payload"]["report"]["output_sha256"] = hashlib.sha256(cache_pdf.read_bytes()).hexdigest()
    meta["payload_sha256"] = build_scan._json_hash(meta["payload"])
    cache_pdf.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
    result = build_scan.build_pdf(manifest, output)
    assert result["page_cache_hits"] == [1, 3]
    assert result["dirty_pages"] == [2]
    assert pixels(output) == expected


def test_failed_fallback_preserves_published_pdf_and_report(tmp_path, monkeypatch):
    manifest = fresh_manifest(tmp_path)
    output = tmp_path / "translated.pdf"
    build_scan.build_pdf(manifest, output)
    before = output.read_bytes()
    report_path = output.with_suffix(".build-report.json")
    before_report = report_path.read_bytes()
    def fail_write(*args, **kwargs):
        raise OSError("fixture fallback write failed")
    monkeypatch.setattr(build_scan.PdfWriter, "write", fail_write)
    with pypdf.apply_configuration(zlib_maximum_output_length=100_000):
        with pytest.raises(OSError, match="fixture fallback write failed"):
            build_scan.build_pdf(manifest, output)
    assert output.read_bytes() == before
    assert report_path.read_bytes() == before_report


def test_failed_local_render_keeps_previous_page_cache(tmp_path, monkeypatch):
    manifest = fresh_manifest(tmp_path)
    output = tmp_path / "translated.pdf"
    initial = build_scan.build_pdf(manifest, output)
    page = Path(initial["pages"][1]["page_pdf_path"])
    cache_before = page.read_bytes()
    manifest["blocks"][1]["translation"] = "Changed"
    def fail_render(manifest, target, clean_dir):
        Path(target).write_bytes(b"incomplete")
        raise OSError("fixture render failed")
    monkeypatch.setattr(build_scan, "_render_pdf", fail_render)
    with pytest.raises(OSError, match="fixture render failed"):
        build_scan.build_pdf(manifest, output)
    assert page.read_bytes() == cache_before
