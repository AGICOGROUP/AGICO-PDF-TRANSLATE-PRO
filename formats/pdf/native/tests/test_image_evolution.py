
import importlib.util
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("clean_evolution", SCRIPTS / "build_clean_image_bases.py")
clean = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clean)


def test_vectorized_run_mask_matches_reference():
    rng = np.random.default_rng(20261113)
    for height, width in [(0, 10), (5, 0), (1, 1), (20, 180)]:
        mask = rng.random((height, width)) < .65
        for minimum in (1, 4, 12, 200):
            expected = np.zeros_like(mask)
            for y, row in enumerate(mask):
                start = None
                for x, value in enumerate(np.append(row, False)):
                    if value and start is None:
                        start = x
                    elif not value and start is not None:
                        if x - start >= minimum:
                            expected[y, start:x] = True
                        start = None
            assert np.array_equal(clean.horizontal_runs(mask, minimum), expected)


def test_bound_external_edit_is_limited_to_reviewed_boxes(tmp_path):
    source = np.full((32, 60, 3), 230, dtype=np.uint8)
    source[8:20, 12:32] = 15
    candidate = np.full_like(source, 100)
    original = tmp_path / "source.png"
    edited = tmp_path / "edited.png"
    Image.fromarray(source).save(original)
    Image.fromarray(candidate).save(edited)
    item = dict(id="image", source=str(original), output="clean.png",
                method="constrained_clean_base", clean_base_candidate=str(edited),
                regions=[dict(box=[12, 8, 32, 20])], protected_boxes=[[20, 8, 24, 20]],
                image_edit_evidence=dict(tool="image_gen",
                    source_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
                    candidate_sha256=hashlib.sha256(edited.read_bytes()).hexdigest(),
                    structural_review_complete=True))
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(dict(images=[item])), encoding="utf8")
    report = clean.build(metadata)["images"][0]
    actual = np.asarray(Image.open(tmp_path / "clean.png"))
    expected = source.copy()
    expected[8:20, 12:32] = 100
    expected[8:20, 20:24] = source[8:20, 20:24]
    assert np.array_equal(actual, expected)
    assert report["outside_region_pixel_changes"] == 0
    assert report["protected_pixel_changes"] == 0
    item["image_edit_evidence"]["candidate_sha256"] = "stale"
    metadata.write_text(json.dumps(dict(images=[item])), encoding="utf8")
    with pytest.raises(ValueError, match="bound image-edit"):
        clean.build(metadata)


@pytest.mark.parametrize("kind", ["flowchart", "screenshot", "site_photo", "unknown"])
def test_zero_label_claim_needs_source_inspection(kind):
    import sys
    sys.path.insert(0, str(SCRIPTS))
    from run_v6_job import _validate_image_localization_review
    item = dict(id="image", content_kind=kind, contains_source_text=False,
                expected_label_count=0, translated_label_count=0,
                preserved_label_count=0, confirm_count=0, labels=[])
    with pytest.raises(ValueError, match="source image review required"):
        _validate_image_localization_review(dict(images=[item]), dict(images=[]), {"image"})


def test_scene_photo_may_preserve_incidental_text_but_screenshot_may_not():
    import sys
    sys.path.insert(0, str(SCRIPTS))
    from run_v6_job import _validate_image_localization_review
    item = dict(id="image", content_kind="scene_photo", method="preserve_photo",
                contains_source_text=True, original_asset_preserved=True,
                source_review_complete=True,
                source_review_reason="Actual scene photograph with incidental shop signs.",
                expected_label_count=0, translated_label_count=0,
                preserved_label_count=0, confirm_count=0, labels=[])
    _validate_image_localization_review(dict(images=[item]), dict(images=[]), {"image"})
    item["content_kind"] = "screenshot"
    with pytest.raises(ValueError, match="original photograph"):
        _validate_image_localization_review(dict(images=[item]), dict(images=[]), {"image"})


def test_constrained_review_requires_candidate_in_builder_metadata():
    import sys
    sys.path.insert(0, str(SCRIPTS))
    from run_v6_job import _validate_image_localization_review
    label = dict(id="label", status="translated", translation="Target")
    item = dict(id="image", method="constrained_clean_base", asset_type="raster_complex",
                expected_label_count=1, translated_label_count=1,
                preserved_label_count=0, confirm_count=0, labels=[label],
                structural_review_complete=True)
    with pytest.raises(ValueError, match="image-edit candidate metadata"):
        _validate_image_localization_review(dict(images=[item]),
                                           dict(images=[dict(id="image", regions=[])]), {"image"})
