"""Fresh synthetic raster cover apply checks; never touches translation jobs."""
import json
import copy
import sys
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import native_cad_pipeline as pipeline


def raster_job(tmp_path):
    if not pipeline.DEFAULT_FONT.is_file():
        pytest.skip("Native CAD default font unavailable")
    image = Image.new("RGB", (400, 200), (225, 240, 205))
    draw = ImageDraw.Draw(image)
    draw.text((30, 30), "SOURCE SOIL", fill="black")
    draw.rectangle((250, 100, 300, 150), fill=(20, 60, 120))
    image_path = tmp_path / "new-source.png"
    image.save(image_path)
    source = tmp_path / pipeline.SOURCE_NAME
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=200)
        page.insert_image(page.rect, filename=str(image_path))
        document.save(source)
    record = dict(id="p0001-o00001", page=0, source="SOURCE SOIL",
                  bbox=[20, 20, 140, 60], kind="outline", status="pending",
                  rotation=0, color=0, font_size=12)
    inventory = dict(source_sha256=pipeline.sha256(source), records=[record])
    with pymupdf.open(source) as document:
        proof = pipeline.raster_cover_evidence(document[0], [record["bbox"]])
    translated = dict(record, status="translated", translation="Translated soil",
                      cover_review=dict(approved=True, text_only=True,
                                        white_background=False,
                                        note="Visually inspected printed text on plain pale green.",
                                        raster_text_cover=proof))
    packet = dict(source_sha256=inventory["source_sha256"], records=[translated])
    pipeline.write_json(tmp_path / pipeline.INVENTORY_NAME, inventory)
    packet_path = tmp_path / pipeline.PACKET_NAME
    pipeline.write_json(packet_path, packet)
    return source, packet_path, packet


def test_apply_verified_colored_raster_keeps_original_image_and_other_pixels(tmp_path):
    source, packet_path, _ = raster_job(tmp_path)
    before = source.read_bytes()
    assert pipeline.apply(tmp_path, packet_path, pipeline.DEFAULT_FONT) == 0
    assert source.read_bytes() == before
    with pymupdf.open(source) as original, pymupdf.open(tmp_path / pipeline.OUTPUT_NAME) as result:
        old_xref = original[0].get_images()[0][0]
        new_xref = result[0].get_images()[0][0]
        assert original.extract_image(old_xref)["image"] == result.extract_image(new_xref)["image"]
        clip = pymupdf.Rect(240, 90, 320, 160)
        assert original[0].get_pixmap(clip=clip).samples == result[0].get_pixmap(clip=clip).samples
        # The formerly black printed raster glyphs are now light background.
        assert result[0].get_pixmap(clip=pymupdf.Rect(20, 20, 140, 60)).samples != original[0].get_pixmap(clip=pymupdf.Rect(20, 20, 140, 60)).samples
        assert "Translated soil" in result[0].get_text()


@pytest.mark.parametrize("field,value", [("approved", False), ("text_only", False), ("note", "")])
def test_apply_raster_pixel_proof_cannot_replace_explicit_source_review(tmp_path, field, value):
    _, packet_path, packet = raster_job(tmp_path)
    packet["records"][0]["cover_review"][field] = value
    pipeline.write_json(packet_path, packet)
    assert pipeline.apply(tmp_path, packet_path, pipeline.DEFAULT_FONT) == 2
    report = json.loads((tmp_path / pipeline.APPLY_REPORT_NAME).read_text(encoding="utf-8"))
    assert "unsafe_outline_regions" in report["failures"]
    assert not (tmp_path / pipeline.OUTPUT_NAME).exists()


def test_apply_rejects_stale_raster_bbox_proof(tmp_path):
    _, packet_path, packet = raster_job(tmp_path)
    packet["records"][0]["cover_boxes"] = [[20, 20, 150, 60]]
    pipeline.write_json(packet_path, packet)
    assert pipeline.apply(tmp_path, packet_path, pipeline.DEFAULT_FONT) == 2
    report = json.loads((tmp_path / pipeline.APPLY_REPORT_NAME).read_text(encoding="utf-8"))
    assert "unsafe_outline_regions" in report["failures"]
    assert any("stale_or_unsafe_raster_text_cover" in r["reasons"] for r in report["regions"])


def test_apply_keeps_raster_pixel_cache_bounded_to_current_page(tmp_path, monkeypatch):
    source, packet_path, packet = raster_job(tmp_path)
    with pymupdf.open(source) as one, pymupdf.open() as two:
        two.insert_pdf(one)
        two.insert_pdf(one)
        content = two.tobytes()
    source.write_bytes(content)
    inventory = json.loads((tmp_path / pipeline.INVENTORY_NAME).read_text(encoding='utf-8'))
    record = copy.deepcopy(inventory['records'][0])
    record.update(id='p0002-o00001', page=1)
    inventory['records'].append(record)
    inventory['source_sha256'] = pipeline.sha256(source)
    translated = copy.deepcopy(packet['records'][0])
    translated.update(id=record['id'], page=1)
    packet['records'].append(translated)
    packet['source_sha256'] = inventory['source_sha256']
    pipeline.write_json(tmp_path / pipeline.INVENTORY_NAME, inventory)
    pipeline.write_json(packet_path, packet)
    original = pipeline.raster_cover_evidence
    cached_page_counts = []

    def measured(page, boxes, page_images=None):
        evidence = original(page, boxes, page_images)
        cached_page_counts.append(len(page_images))
        return evidence

    monkeypatch.setattr(pipeline, 'raster_cover_evidence', measured)
    assert pipeline.apply(tmp_path, packet_path, pipeline.DEFAULT_FONT) == 0
    assert max(cached_page_counts) == 1
