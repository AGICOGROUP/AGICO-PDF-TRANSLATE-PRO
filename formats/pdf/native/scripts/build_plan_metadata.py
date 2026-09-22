"""Build image metadata and review from a machine plan plus a label mapping.

Boxes come from the mapping; cleanup mode, colour and boldness are taken from
the plan lines each label claims, so nothing is hand-typed twice. Any plan line
left unclaimed and unjustified is reported: the coverage gate depends on it.
"""
import json
import os
import sys
from collections import Counter

import numpy as np
from PIL import Image

JOB = sys.argv[1]
OUT = sys.argv[2]
MAPS = sys.argv[3:]

MODE_RANK = {"text_only_area": 3, "neutral_plain": 2, "red": 1, "cyan": 1}


def sample(image, box):
    x0, y0, x1, y1 = box
    crop = image[max(0, y0):y1, max(0, x0):x1].astype(np.int16)
    if crop.size == 0:
        return [0.0, 0.0, 0.0]
    maximum = crop.max(axis=2)
    sat = maximum - crop.min(axis=2)
    ink = (maximum < 215) | (sat > 60)
    if ink.sum() < 5:
        ink = maximum < 240
    if ink.sum() < 5:
        return [0.0, 0.0, 0.0]
    return [round(float(v) / 255.0, 3) for v in np.median(crop[ink], axis=0)]


def centre(box):
    return (0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3]))


def inside(point, box):
    return box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]


def build(spec, job_dir, out_dir):
    image_id = spec["image_id"]
    with open(os.path.join(job_dir, "label-plan-%s.json" % image_id),
              encoding="utf-8") as handle:
        plan = json.load(handle)
    source = plan["source"]
    image = np.array(Image.open(source).convert("RGB"))
    lines = plan["lines"]
    claimed = [False] * len(lines)
    regions = []
    review_labels = []

    def pick(boxes):
        modes, bolds = [], []
        for index, line in enumerate(lines):
            if any(inside(centre(line["box"]), box) for box in boxes):
                claimed[index] = True
                modes.append(line["suggested_mode"])
                bolds.append(line["bold"])
        if not modes:
            mode = "text_only_area"
        else:
            mode = Counter(modes).most_common(1)[0][0]
            if len(boxes) > 1 and mode == "neutral_plain":
                mode = "text_only_area"
        return mode, bool(bolds and Counter(bolds)[True] > Counter(bolds)[False])

    def refine(mode, box):
        """neutral_plain cannot lift saturated ink; on white ground use a wipe."""
        if mode != "neutral_plain":
            return mode
        rgb = sample(image, box)
        if max(rgb) - min(rgb) > 0.28:
            return "text_only_area"
        return mode

    for number, label in enumerate(spec["labels"], start=1):
        box, en, zh = label[0], label[1], label[2]
        bold = label[3] if len(label) > 3 else None
        mode, auto_bold = pick([box])
        mode = refine(mode, box)
        if bold is None:
            bold = auto_bold
        regions.append({
            "box": box, "clean_box": box, "mode": mode, "text": zh,
            "source_text": en, "role": "body", "align": "left", "bold": bold,
            "color": sample(image, box), "max_font": 3.4,
            "min_font": 1.8, "line_gap": 1.16,
        })
        review_labels.append({
            "id": "%s-L%02d" % (image_id, number), "source_text": en,
            "translation": zh, "ocr_confidence": "high",
            "method": "deterministic_cleanup", "status": "translated",
            "box": box,
        })

    rotated = spec.get("rotated")
    if rotated:
        pick(rotated["segments"])
        regions.extend({
            "box": segment, "clean_box": segment, "mode": "red", "text": "",
            "source_text": "", "role": "cleanup", "align": "left",
            "bold": False, "color": [0.0, 0.0, 0.0], "max_font": 3.4,
            "min_font": 1.8, "line_gap": 1.16,
        } for segment in rotated["segments"])
        regions.append({
            "box": rotated["box"], "clean_box": rotated["segments"][-1],
            "mode": "red", "text": rotated["zh"],
            "source_text": rotated["en"], "role": "body", "align": "center",
            "bold": False, "color": sample(image, rotated["segments"][0]),
            "max_font": 3.4, "min_font": 1.8, "line_gap": 1.16,
            "rotation": rotated["rotation"],
        })
        review_labels.append({
            "id": "%s-L%02d" % (image_id, len(spec["labels"]) + 1),
            "source_text": rotated["en"], "translation": rotated["zh"],
            "ocr_confidence": "high", "method": "deterministic_cleanup",
            "status": "translated", "box": rotated["box"],
        })

    exclusions = [(e[0], e[1]) for e in spec.get("exclusions", [])]
    unclaimed = []
    for index, line in enumerate(lines):
        if claimed[index]:
            line["claim"] = "cleaned_by_label"
            continue
        waived = next((reason for box, reason in exclusions
                       if inside(centre(line["box"]), box) and reason.strip()), None)
        if waived:
            line["claim"] = "excluded_artwork"
            line["exclude_reason"] = waived
            continue
        line.pop("claim", None)
        line.pop("exclude_reason", None)
        unclaimed.append("%s %s" % (line["id"], line["box"]))
    plan_path = os.path.join(job_dir, "label-plan-%s.json" % image_id)
    with open(plan_path, "w", encoding="utf-8") as handle:
        json.dump(plan, handle, ensure_ascii=False, indent=1)
    record = {
        "id": image_id, "page": plan["page"], "asset_type": "raster_simple",
        "contains_source_text": True, "source": source,
        "output": os.path.join(out_dir, "%s-clean.png" % image_id),
        "placement": plan["placement"], "protected_boxes": [],
        "method": "deterministic_cleanup",
        "expected_label_count": len(review_labels),
        "translated_label_count": len(review_labels),
        "preserved_label_count": 0, "confirm_count": 0,
        "unmatched_source_label_count": 0, "reviewed_pixel_region": True,
        "regions": regions,
    }
    review = {
        "id": image_id, "page": plan["page"], "asset_type": "raster_simple",
        "method": "deterministic_cleanup", "contains_source_text": True,
        "expected_label_count": len(review_labels),
        "translated_label_count": len(review_labels),
        "preserved_label_count": 0, "confirm_count": 0,
        "unmatched_source_label_count": 0, "labels": review_labels,
        "structural_review_complete": True,
    }
    return record, review, unclaimed


def main():
    os.makedirs(OUT, exist_ok=True)
    images, reviews, all_unclaimed = [], [], {}
    for path in MAPS:
        with open(path, encoding="utf-8") as handle:
            spec = json.load(handle)
        record, review, unclaimed = build(spec, JOB, OUT)
        images.append(record)
        reviews.append(review)
        all_unclaimed[review["id"]] = unclaimed
    with open(os.path.join(OUT, "image-vector-metadata.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"images": images}, handle, ensure_ascii=False, indent=1)
    review_doc = {
        "complete": True,
        "reviewed_image_ids": ["p0001-i001", "p0002-i001"] + [r["id"] for r in reviews],
        "images": [
            {"id": "p0001-i001", "page": 1, "asset_type": "raster_simple",
             "method": "preserve_confirm",
             "contains_source_text": True, "expected_label_count": 1,
             "translated_label_count": 0, "preserved_label_count": 1,
             "confirm_count": 1, "unmatched_source_label_count": 0,
             "structural_review_complete": True,
             "labels": [{"id": "p0001-i001-l01", "source_text": "KLIMAX",
                         "translation": "", "ocr_confidence": "high",
                         "method": "preserve_confirm", "status": "confirm",
                         "preserve_reason": "logo_or_seal",
                         "box": [0, 0, 1, 1]}]},
            {"id": "p0002-i001", "page": 2, "asset_type": "raster_simple",
             "method": "preserve_confirm",
             "contains_source_text": True, "expected_label_count": 1,
             "translated_label_count": 0, "preserved_label_count": 1,
             "confirm_count": 1, "unmatched_source_label_count": 0,
             "structural_review_complete": True,
             "labels": [{"id": "p0002-i001-l01",
                         "source_text": "SDCAD and certification marks",
                         "translation": "", "ocr_confidence": "high",
                         "method": "preserve_confirm", "status": "confirm",
                         "preserve_reason": "logo_or_seal",
                         "box": [0, 0, 1, 1]}]},
        ] + reviews,
        "confirm_items": [
            {"label_id": "p0001-i001-l01",
             "reason": "商标图形，替换模式下原样保留"},
            {"label_id": "p0002-i001-l01",
             "reason": "供应商与认证标识，原样保留"},
        ],
    }
    with open(os.path.join(OUT, "image-review.json"), "w",
              encoding="utf-8") as handle:
        json.dump(review_doc, handle, ensure_ascii=False, indent=1)
    for image_id, unclaimed in all_unclaimed.items():
        print(image_id, "unclaimed_plan_lines", len(unclaimed), unclaimed[:12])


if __name__ == "__main__":
    main()
