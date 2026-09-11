from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_scan import clean_background
from contracts import validate_manifest


def fixture_manifest():
    return {
        "source": "original.pdf", "source_sha256": "a" * 64,
        "selected_pages": [1],
        "pages": [{"source_page": 1, "pixel_width": 120, "pixel_height": 80}],
        "source_lines": [{"id": "p01-l001", "page": 1,
                          "box": [10, 10, 40, 20], "text": "Aumentar", "rotation": 0}],
        "blocks": [{"id": "p01-r001", "page": 1, "source_line_ids": ["p01-l001"],
                    "source": "Aumentar", "translation": "逐步增至 6000 daN。",
                    "role": "body", "status": "translated", "action": "replace",
                    "box": [10, 10, 110, 28], "clean_box": [10, 10, 41, 21],
                    "background": [255, 255, 255]}],
    }


def fixture_supplements():
    return {"source_sha256": "a" * 64, "supplements": [{
        "block_id": "p01-r001", "source": "Aumentar progresivamente hasta 6000 daN.",
        "translation": "逐步增至 6000 daN。",
        "source_lines": [{"id": "p01-visual-001", "page": 1,
                          "box": [10, 40, 101, 51], "rotation": 0,
                          "text": "progresivamente hasta 6000 daN."}],
    }]}


def invoke(tmp_path, manifest, supplements):
    original = tmp_path / "manifest.json"
    patch = tmp_path / "supplements.json"
    output = tmp_path / "updated.json"
    original.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    patch.write_text(json.dumps(supplements, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "register_source_supplements.py"),
         "--manifest", str(original), "--supplements", str(patch), "--output", str(output)],
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc, original, output


def test_missing_second_line_is_registered_and_erased_without_duplicate_translation(tmp_path):
    manifest = fixture_manifest()
    source_image = Image.new("RGB", (120, 80), "white")
    draw = ImageDraw.Draw(source_image)
    draw.rectangle((10, 10, 40, 20), fill="black")
    draw.line((0, 30, 119, 30), fill="red", width=2)
    draw.rectangle((10, 40, 100, 50), fill="black")
    before, _ = clean_background(source_image, manifest["blocks"])
    assert before.getpixel((20, 45)) == (0, 0, 0)  # Original failure: invisible to inventory coverage.

    proc, original, output = invoke(tmp_path, manifest, fixture_supplements())
    assert proc.returncode == 0, proc.stderr
    updated = json.loads(output.read_text(encoding="utf-8"))
    validate_manifest(updated)
    assert json.loads(original.read_text(encoding="utf-8")) == manifest
    assert len(updated["blocks"]) == 1
    block = updated["blocks"][0]
    assert block["translation"] == "逐步增至 6000 daN。"
    assert block["box"] == [10, 10, 110, 28]
    assert block["source_line_ids"] == ["p01-l001", "p01-visual-001"]
    assert block["clean_boxes"] == [[10, 10, 41, 21], [10, 40, 101, 51]]
    assert "clean_box" not in block
    assert updated["source_lines"][-1]["origin"] == "visual_supplement"
    cleaned, report = clean_background(source_image, updated["blocks"])
    assert cleaned.getpixel((20, 45)) == (255, 255, 255)
    assert cleaned.getpixel((20, 30)) == (255, 0, 0)
    assert report["outside_approved_pixel_changes"] == 0
    summary = json.loads(proc.stdout)
    assert summary["pages_requiring_review"] == [1]
    assert not list(tmp_path.glob("*review*.json"))


def test_can_replace_incomplete_translation_with_complete_region_text(tmp_path):
    manifest = fixture_manifest()
    manifest["blocks"][0]["translation"] = "增加"
    manifest["blocks"][0]["clean_boxes"] = [manifest["blocks"][0].pop("clean_box")]
    proc, _, output = invoke(tmp_path, manifest, fixture_supplements())
    assert proc.returncode == 0, proc.stderr
    updated = json.loads(output.read_text(encoding="utf-8"))
    assert updated["blocks"][0]["translation"] == "逐步增至 6000 daN。"
    assert updated["blocks"][0]["source"] == "Aumentar progresivamente hasta 6000 daN."


@pytest.mark.parametrize("problem", ["wrong_source", "wrong_page", "duplicate_id", "out_of_bounds",
                                     "nonfinite", "wrong_rotation", "bilingual", "blank_translation",
                                     "missing_box", "unknown_block"])
def test_invalid_supplement_does_not_overwrite_output(tmp_path, problem):
    manifest, patch = fixture_manifest(), fixture_supplements()
    item = patch["supplements"][0]
    line = item["source_lines"][0]
    if problem == "wrong_source":
        patch["source_sha256"] = "b" * 64
    elif problem == "wrong_page":
        line["page"] = 2
    elif problem == "duplicate_id":
        line["id"] = "p01-l001"
    elif problem == "out_of_bounds":
        line["box"] = [10, 40, 121, 51]
    elif problem == "nonfinite":
        line["box"][0] = float("nan")
    elif problem == "wrong_rotation":
        line["rotation"] = 90
    elif problem == "bilingual":
        manifest["blocks"][0]["action"] = "add_bilingual"
    elif problem == "blank_translation":
        item["translation"] = " "
    elif problem == "missing_box":
        del line["box"]
    elif problem == "unknown_block":
        item["block_id"] = "unknown"
    output = tmp_path / "updated.json"
    output.write_bytes(b"previous valid manifest")
    proc, original, _ = invoke(tmp_path, manifest, patch)
    assert proc.returncode != 0
    assert "invalid supplement" in proc.stderr
    assert output.read_bytes() == b"previous valid manifest"
    assert json.loads(original.read_text(encoding="utf-8")) == manifest


def test_batch_failure_does_not_save_earlier_valid_supplement(tmp_path):
    patch = fixture_supplements()
    bad = copy.deepcopy(patch["supplements"][0])
    bad["source_lines"][0]["id"] = "another-line"
    bad["source_lines"][0]["page"] = 2
    patch["supplements"].append(bad)
    proc, _, output = invoke(tmp_path, fixture_manifest(), patch)
    assert proc.returncode != 0
    assert not output.exists()


def test_in_place_save_and_rejected_reapplication_keep_registered_manifest(tmp_path):
    proc, original, output = invoke(tmp_path, fixture_manifest(), fixture_supplements())
    assert proc.returncode == 0, proc.stderr
    command = [sys.executable, str(SCRIPTS / "register_source_supplements.py"),
               "--manifest", str(original), "--supplements", str(tmp_path / "supplements.json"),
               "--output", str(original)]
    saved = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert saved.returncode == 0, saved.stderr
    assert original.read_bytes() == output.read_bytes()
    registered_bytes = original.read_bytes()
    retry = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert retry.returncode != 0
    assert "source ID must be new" in retry.stderr
    assert original.read_bytes() == registered_bytes
