from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pymupdf
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_scan


def page_fixture(tmp_path, count=3, pixels=300):
    manifest = {"source": "fixture.pdf", "source_sha256": "a" * 64,
                "target_language": "en", "selected_pages": list(range(1, count + 1)),
                "pages": [], "blocks": [], "source_lines": []}
    for number in manifest["selected_pages"]:
        render = tmp_path / f"source-{number}.png"
        image = Image.new("RGB", (pixels, pixels), (240, 245, 250))
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, 80, 35), fill="black")
        draw.line((10, 100, pixels - 10, 100), fill="blue", width=2)
        image.save(render)
        manifest["pages"].append({"source_page": number, "render_path": str(render),
            "width_pt": 300, "height_pt": 300, "pixel_width": pixels, "pixel_height": pixels,
            "vector_lines": [{"points": [20, 90, 100, 90], "color": [0, 0.5, 0]}]})
        manifest["source_lines"].append({"id": f"l{number}", "page": number,
            "text": "Texto", "box": [20, 20, 80, 35], "rotation": 0})
        manifest["blocks"].append({"id": f"b{number}", "page": number,
            "source_line_ids": [f"l{number}"], "source": "Texto", "translation": f"Page {number}",
            "role": "body", "status": "translated", "action": "replace",
            "box": [20, 20, pixels - 20, pixels // 3], "clean_box": [20, 20, 81, 36],
            "background": [240, 245, 250], "rotation": 0})
    return manifest


def observe_draws(monkeypatch):
    drawn = []
    original = build_scan._draw_block

    def tracked(pdf, block, page):
        drawn.append(page["source_page"])
        return original(pdf, block, page)

    monkeypatch.setattr(build_scan, "_draw_block", tracked)
    return drawn


def page_evidence(path):
    with pymupdf.open(path) as pdf:
        return [(page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).samples,
                 page.get_text("rawdict")) for page in pdf]


def test_word_edit_renders_only_changed_page_and_matches_cold(tmp_path, monkeypatch):
    manifest = page_fixture(tmp_path)
    output = tmp_path / "translated.pdf"
    original = copy.deepcopy(manifest)
    drawn = observe_draws(monkeypatch)
    first = build_scan.build_pdf(manifest, output)
    assert drawn == [1, 2, 3]
    page1 = Path(first["pages"][0]["page_pdf_path"])
    unchanged_bytes, unchanged_mtime = page1.read_bytes(), page1.stat().st_mtime_ns
    drawn.clear()
    manifest["blocks"][1]["translation"] = "Page repaired"
    repaired = build_scan.build_pdf(manifest, output)
    assert drawn == [2]
    assert repaired["page_cache_hits"] == [1, 3]
    assert repaired["dirty_pages"] == [2]
    assert page1.read_bytes() == unchanged_bytes
    assert page1.stat().st_mtime_ns == unchanged_mtime
    cold = build_scan.build_pdf(manifest, tmp_path / "cold" / "translated.pdf", use_page_cache=False)
    assert page_evidence(output) == page_evidence(cold["output"])
    for key in ("changed_pixel_count", "outside_approved_pixel_changes", "rendered_blocks",
                "source_crop_runs", "mixed_color_block_count"):
        assert repaired[key] == cold[key]
    assert original["blocks"][0] == manifest["blocks"][0]  # Fitting must not mutate caller data.


@pytest.mark.parametrize("fault", ["pdf", "report", "report_measurement", "missing", "source", "cleanup", "geometry", "removed"])
def test_only_invalid_page_rebuilt(tmp_path, monkeypatch, fault):
    manifest = page_fixture(tmp_path)
    output = tmp_path / "translated.pdf"
    drawn = observe_draws(monkeypatch)
    first = build_scan.build_pdf(manifest, output)
    page_pdf = Path(first["pages"][1]["page_pdf_path"])
    if fault == "pdf":
        page_pdf.write_bytes(b"corrupt PDF")
    elif fault == "report":
        page_pdf.with_suffix(".json").write_text('{"broken": true}', encoding="utf-8")
    elif fault == "report_measurement":
        metadata_path = page_pdf.with_suffix(".json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["payload"]["report"]["changed_pixel_count"] = 0
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    elif fault == "missing":
        page_pdf.unlink()
    elif fault == "source":
        image_path = manifest["pages"][1]["render_path"]
        with Image.open(image_path) as image:
            altered = image.copy()
        altered.putpixel((250, 250), (100, 0, 0))
        altered.save(image_path)
    elif fault == "cleanup":
        manifest["blocks"][1]["background"] = [255, 255, 255]
    elif fault == "geometry":
        manifest["pages"][1]["width_pt"] = 320
    else:
        manifest["blocks"].pop(1)
        manifest["source_lines"].pop(1)
    drawn.clear()
    result = build_scan.build_pdf(manifest, output)
    assert result["page_cache_hits"] == [1, 3]
    assert result["dirty_pages"] == [2]
    assert drawn == ([] if fault == "removed" else [2])
    cold = build_scan.build_pdf(manifest, tmp_path / "cold.pdf", use_page_cache=False)
    assert page_evidence(output) == page_evidence(cold["output"])


def test_reordering_reuses_pages_in_requested_order(tmp_path, monkeypatch):
    manifest = page_fixture(tmp_path)
    output = tmp_path / "translated.pdf"
    drawn = observe_draws(monkeypatch)
    build_scan.build_pdf(manifest, output)
    manifest["selected_pages"] = [3, 1]
    drawn.clear()
    result = build_scan.build_pdf(manifest, output)
    assert drawn == []
    assert result["page_cache_hits"] == [3, 1]
    assert [page["source_page"] for page in result["pages"]] == [3, 1]
    with pymupdf.open(output) as pdf:
        assert [page.get_text().strip() for page in pdf] == ["Page 3", "Page 1"]


def test_stale_source_hash_and_failed_build_preserve_final(tmp_path):
    manifest = page_fixture(tmp_path)
    output = tmp_path / "translated.pdf"
    build_scan.build_pdf(manifest, output)
    before = output.read_bytes()
    before_report = output.with_suffix(".build-report.json").read_bytes()
    manifest["pages"][1]["render_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source render hash mismatch"):
        build_scan.build_pdf(manifest, output)
    assert output.read_bytes() == before
    manifest["pages"][1].pop("render_sha256")
    manifest["blocks"][1]["translation"] = "Impossible" * 300
    with pytest.raises(build_scan.TextOverflowError):
        build_scan.build_pdf(manifest, output)
    assert output.read_bytes() == before
    assert output.with_suffix(".build-report.json").read_bytes() == before_report


def test_target_language_invalidates_pages(tmp_path, monkeypatch):
    manifest = page_fixture(tmp_path)
    output = tmp_path / "translated.pdf"
    drawn = observe_draws(monkeypatch)
    build_scan.build_pdf(manifest, output)
    drawn.clear()
    manifest["target_language"] = "es"
    result = build_scan.build_pdf(manifest, output)
    assert drawn == [1, 2, 3]
    assert result["dirty_pages"] == [1, 2, 3]


def test_changed_registered_font_contents_invalidates_pages(tmp_path, monkeypatch):
    manifest = page_fixture(tmp_path)
    output = tmp_path / "translated.pdf"
    build_scan.register_fonts("en")
    font = build_scan.pdfmetrics.getFont(build_scan.REGULAR_FONT)
    font_path = tmp_path / "fixture-font.ttf"
    font_path.write_bytes(Path(font.face.filename).read_bytes())
    monkeypatch.setattr(font.face, "filename", str(font_path))
    drawn = observe_draws(monkeypatch)
    build_scan.build_pdf(manifest, output)
    drawn.clear()
    font_path.write_bytes(font_path.read_bytes() + b"identity-change")
    result = build_scan.build_pdf(manifest, output)
    assert drawn == [1, 2, 3]
    assert result["dirty_pages"] == [1, 2, 3]


def test_dependency_contents_invalidate_pages(tmp_path, monkeypatch):
    scripts = Path(build_scan.__file__).resolve().parent
    implementation = tmp_path / "implementation"
    implementation.mkdir()
    for name in ("build_scan.py", "contracts.py", "layout_adjustments.py"):
        (implementation / name).write_bytes((scripts / name).read_bytes())
    monkeypatch.setattr(build_scan, "__file__", str(implementation / "build_scan.py"))
    manifest = page_fixture(tmp_path)
    output = tmp_path / "translated.pdf"
    drawn = observe_draws(monkeypatch)
    build_scan.build_pdf(manifest, output)
    dependency = implementation / "contracts.py"
    dependency.write_bytes(dependency.read_bytes() + b"\n# Changed fitting implementation\n")
    drawn.clear()
    result = build_scan.build_pdf(manifest, output)
    assert drawn == [1, 2, 3]
    assert result["dirty_pages"] == [1, 2, 3]


@pytest.mark.parametrize("language", ["en", "zh"])
def test_rich_rotated_pages_match_full_document_glyphs_and_pixels(tmp_path, language):
    if language == "zh" and not any(path.exists() for path in build_scan.CJK_REGULAR_FONT_PATHS):
        pytest.skip("CJK font unavailable in this runtime")
    manifest = page_fixture(tmp_path)
    manifest["target_language"] = language
    for number, block in enumerate(manifest["blocks"]):
        rotation = (0, 90, 270)[number]
        block["rotation"] = rotation
        manifest["source_lines"][number]["rotation"] = rotation
        block["box"] = [20, 20, 260, 260]
        block["translation"] = "Before After" if language == "en" else "之前 之后"
        before, after = block["translation"].split()
        block["rich_lines"] = [[{"type": "text", "text": before + " ", "color": [0, 0, 0]},
            {"type": "source_crop", "source_box": [20, 20, 28, 28], "alt": "Original icon"},
            {"type": "text", "text": after, "color": [0, 0.4, 0.7], "bold": True}]]
    cached = build_scan.build_pdf(manifest, tmp_path / "cached.pdf")
    cold = build_scan.build_pdf(manifest, tmp_path / "cold.pdf", use_page_cache=False)
    assert page_evidence(cached["output"]) == page_evidence(cold["output"])
    assert cached["source_crop_run_count"] == 3
    assert cached["source_crop_runs"] == cold["source_crop_runs"]
    assert cached["mixed_color_block_count"] == 3
    warm = build_scan.build_pdf(manifest, tmp_path / "cached.pdf")
    assert warm["page_cache_hits"] == [1, 2, 3]
    assert warm["source_crop_runs"] == cold["source_crop_runs"]
    assert warm["changed_pixel_count"] == cold["changed_pixel_count"]


def test_assembly_failure_retains_previous_pdf_and_report(tmp_path, monkeypatch):
    manifest = page_fixture(tmp_path)
    output = tmp_path / "translated.pdf"
    build_scan.build_pdf(manifest, output)
    before = output.read_bytes()
    before_report = output.with_suffix(".build-report.json").read_bytes()

    def fail_write(writer, path):
        Path(path).write_bytes(b"partial assembled PDF")
        raise OSError("simulated assembly disk failure")

    monkeypatch.setattr(build_scan.PdfWriter, "write", fail_write)
    with pytest.raises(OSError, match="disk failure"):
        build_scan.build_pdf(manifest, output)
    assert output.read_bytes() == before
    assert output.with_suffix(".build-report.json").read_bytes() == before_report


def test_report_publication_failure_preserves_previous_final_pdf(tmp_path, monkeypatch):
    manifest = page_fixture(tmp_path)
    output = tmp_path / "translated.pdf"
    build_scan.build_pdf(manifest, output)
    before = output.read_bytes()
    manifest["blocks"][1]["translation"] = "Corrected page"
    original = Path.replace

    def fail_report(path, target):
        if str(target).endswith(".build-report.json"):
            raise PermissionError("simulated report publication failure")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", fail_report)
    with pytest.raises(PermissionError, match="publication"):
        build_scan.build_pdf(manifest, output)
    assert output.read_bytes() == before


def test_cached_output_keeps_shared_resource_size_on_first_build_and_repairs(tmp_path):
    manifest = page_fixture(tmp_path, count=8)
    output = tmp_path / "cached" / "translated.pdf"
    for revision in range(3):
        if revision:
            manifest["blocks"][revision]["translation"] = f"Repaired page {revision}"
        result = build_scan.build_pdf(manifest, output)
        full = build_scan.build_pdf(manifest, tmp_path / f"full-{revision}.pdf", use_page_cache=False)
        assert page_evidence(output) == page_evidence(full["output"])
        # Repeated embedded fonts/backgrounds must not multiply with page count.
        assert output.stat().st_size <= Path(full["output"]).stat().st_size * 1.3
        if revision:
            assert result["dirty_pages"] == [revision + 1]
            assert len(result["page_cache_hits"]) == 7


def test_cached_repair_preserves_distinct_cjk_font_subsets(tmp_path):
    if not any(path.exists() for path in build_scan.CJK_REGULAR_FONT_PATHS):
        pytest.skip("CJK font unavailable in this runtime")
    manifest = page_fixture(tmp_path, count=8)
    manifest["target_language"] = "zh"
    for index, block in enumerate(manifest["blocks"]):
        block["box"] = [20, 20, 280, 280]
        block["translation"] = ''.join(chr(0x4e00 + index * 40 + i) for i in range(40))
    output = tmp_path / "cached.pdf"
    build_scan.build_pdf(manifest, output)
    manifest["blocks"][3]["translation"] = "修订后的中文标签"
    result = build_scan.build_pdf(manifest, output)
    full = build_scan.build_pdf(manifest, tmp_path / "full.pdf", use_page_cache=False)
    assert result["dirty_pages"] == [4]
    # Similar subset font names are not evidence of identical glyph mappings.
    assert page_evidence(output) == page_evidence(full["output"])


def test_same_block_id_on_different_pages_keeps_page_local_measurements(tmp_path):
    manifest = page_fixture(tmp_path)
    for block in manifest["blocks"]:
        block["id"] = "label"
    output = tmp_path / "cached.pdf"
    full = build_scan.build_pdf(manifest, tmp_path / "full.pdf", use_page_cache=False)
    for _ in range(2):
        result = build_scan.build_pdf(manifest, output)
        assert result["rendered_block_count"] == 3
        assert result["rendered_blocks"] == full["rendered_blocks"]
        assert result["changed_pixel_count"] == full["changed_pixel_count"]
    assert result["page_cache_hits"] == [1, 2, 3]
