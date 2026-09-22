#!/usr/bin/env python3
"""Recover light-grey "ghost" artwork that normal OCR cannot see, in one pass.

CAD plots often carry a whole layer (parts lists, notes, title-block fields)
drawn within a few grey levels of its own fill, e.g. 244 on a 249 background.
A normal render and the tiled OCR pass both miss it silently. This tool renders
at 600 dpi, applies a fixed threshold, re-runs OCR, back-projects the boxes to
page points, and inserts every credible label into the job inventory and packet
so the agent only has to decide translated vs preserved.

Run it once, immediately after prepare, for any sparse or drawing-like page.

  python scripts/recover_faint.py <job-dir>
  python scripts/recover_faint.py <job-dir> --dry-run
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

import pymupdf
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cad_cache import LazyOCR  # noqa: E402

LETTER = re.compile(r"[A-Za-z\u00c0-\u00ff\u0400-\u04ff]")
ID_PREFIX = "f"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def thresholded(page: pymupdf.Page, clip: pymupdf.Rect, dpi: int, level: int) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    grey = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    return grey.point(lambda value: 0 if value < level else 255)


def ocr_image(image: Image.Image, engine) -> list:
    import numpy as np

    result, _ = engine(np.array(image.convert("RGB")))
    return list(result or [])


def tile_rects(width: float, height: float, columns: int, rows: int, overlap: float):
    for row in range(rows):
        for column in range(columns):
            x0 = column * width / columns
            y0 = row * height / rows
            yield pymupdf.Rect(x0, y0, min(x0 + width / columns + overlap, width),
                               min(y0 + height / rows + overlap, height))


def union(a: list, b: list) -> list:
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def contains(outer: list, inner: list) -> bool:
    return (outer[0] <= inner[0] + 0.5 and outer[1] <= inner[1] + 0.5
            and outer[2] >= inner[2] - 0.5 and outer[3] >= inner[3] - 0.5)


def cross_overlap(a: list, b: list, axis: int) -> float:
    lo = max(a[axis], b[axis])
    hi = min(a[axis + 2], b[axis + 2])
    smaller = min(a[axis + 2] - a[axis], b[axis + 2] - b[axis])
    return max(0.0, hi - lo) / max(smaller, 1e-6)


def along_gap(a: list, b: list, axis: int) -> float:
    return max(a[axis], b[axis]) - min(a[axis + 2], b[axis + 2])


def merge_fragments(found: list) -> list:
    """Join fragments of one label without fusing two separate labels.

    Fragments must run along the same text direction: they need strong
    cross-axis alignment and a small along-axis gap. Two identical labels in
    different columns, rows, or far apart on the sheet never satisfy both.
    """
    merged = True
    while merged:
        merged = False
        for i, left in enumerate(found):
            for j in range(i + 1, len(found)):
                right = found[j]
                if left["source"].split() != right["source"].split():
                    continue
                vertical = (left["bbox"][3] - left["bbox"][1] > 3 * (left["bbox"][2] - left["bbox"][0])
                            and right["bbox"][3] - right["bbox"][1] >
                            3 * (right["bbox"][2] - right["bbox"][0]))
                along, cross = (1, 0) if vertical else (0, 1)
                if cross_overlap(left["bbox"], right["bbox"], cross) < 0.6:
                    continue
                limit = max(2.5 * min(abs(left["bbox"][along + 2] - left["bbox"][along]),
                                      abs(right["bbox"][along + 2] - right["bbox"][along])), 6.0)
                if along_gap(left["bbox"], right["bbox"], along) > limit:
                    continue
                left["bbox"] = union(left["bbox"], right["bbox"])
                left["source"] = " ".join(sorted({left["source"], right["source"]},
                                                  key=len, reverse=True))
                left["confidence"] = max(left["confidence"], right["confidence"])
                found.pop(j)
                merged = True
                break
            if merged:
                break
    return found


def resolve_rotation(page: pymupdf.Page, rect: pymupdf.Rect, dpi: int, level: int, engine) -> int:
    """Choose 90 or 270 for a tall narrow label.

    OCR reads vertical text in place, so an unrotated score cannot discriminate
    the two directions. Rotating the crop so the reading direction becomes
    left-to-right scores well; the opposite rotation turns it upside down.
    """
    def score(rotate: int) -> float:
        image = thresholded(page, rect, dpi, level).rotate(rotate, expand=True)
        return sum(len(LETTER.findall(text)) * float(conf)
                   for _, text, conf in ocr_image(image, engine))

    clockwise, counter = score(270), score(90)
    if max(clockwise, counter) < 1.0:
        return 0
    # `score` rotates the *image* until the label reads left-to-right. The packet
    # field is the opposite: the rotation needed to draw target text *like* the
    # source, so the winning image rotation is inverted here.
    return 270 if counter > clockwise else 90


def scan_page(page: pymupdf.Page, page_number: int, known: list, args, engine) -> list:
    scale = args.dpi / 72.0
    found: list[dict] = []
    for clip in tile_rects(page.rect.width, page.rect.height, args.columns, args.rows, args.overlap):
        image = thresholded(page, clip, args.dpi, args.threshold)
        for box, text, confidence in ocr_image(image, engine):
            text = str(text).strip()
            if len(LETTER.findall(text)) < args.min_letters or float(confidence) < args.min_confidence:
                continue
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            bbox = [round(clip.x0 + min(xs) / scale, 2), round(clip.y0 + min(ys) / scale, 2),
                    round(clip.x0 + max(xs) / scale, 2), round(clip.y0 + max(ys) / scale, 2)]
            if any(bbox[0] < k[2] and k[0] < bbox[2] and bbox[1] < k[3] and k[1] < bbox[3]
                   for k in known):
                continue
            found.append({"page": page_number, "source": text, "bbox": bbox,
                          "confidence": round(float(confidence), 3)})
    return merge_fragments(found)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("job_dir", type=Path)
    parser.add_argument("--dpi", type=int, default=600, help="600 is the floor; 300/400 still miss this layer")
    parser.add_argument("--threshold", type=int, default=246, help="grey level below which a pixel is ink")
    parser.add_argument("--min-letters", type=int, default=3)
    parser.add_argument("--min-confidence", type=float, default=0.60)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--overlap", type=float, default=20.0)
    parser.add_argument("--dry-run", action="store_true", help="report candidates without touching the job")
    args = parser.parse_args(argv)

    job = args.job_dir
    inventory_path = job / "source-inventory.json"
    packet_path = job / "translation-packet.json"
    if not (job / "SOURCE.pdf").exists() or not inventory_path.exists():
        print(json.dumps({"passed": False, "error": "run prepare first"}))
        return 2

    inventory = load_json(inventory_path)
    packet = load_json(packet_path) if packet_path.exists() else {"records": [], "page_context": []}
    # Idempotent: drop candidates added by an earlier run of this tool.
    recovered_id = re.compile(r"^p\d{4}-f\d{5}$")
    inventory["records"] = [r for r in inventory["records"]
                            if not recovered_id.match(str(r["id"]))]
    packet["records"] = [r for r in packet.get("records", [])
                         if not recovered_id.match(str(r["id"]))]

    engine = LazyOCR()
    document = pymupdf.open(job / "SOURCE.pdf")
    added: list[dict] = []
    counters: dict[int, int] = {}
    for index, page in enumerate(document):
        known = [record["bbox"] for record in inventory["records"] if record["page"] == index]
        for candidate in scan_page(page, index, known, args, engine):
            box = candidate["bbox"]
            width, height = box[2] - box[0], box[3] - box[1]
            rotation = 0
            vertical = height > width * 3 and len(LETTER.findall(candidate["source"])) > 3
            if vertical:
                rotation = resolve_rotation(page, pymupdf.Rect(*box), args.dpi, args.threshold, engine)
            counters[index] = counters.get(index, 0) + 1
            record_id = "p{0:04d}-{1}{2:05d}".format(index + 1, ID_PREFIX, counters[index])
            record = {"id": record_id, "page": index, "source": candidate["source"],
                      "bbox": box, "font_size": round(min(height, 6.0), 2), "color": 0,
                      "rotation": rotation, "status": "pending", "kind": "outline"}
            inventory["records"].append(record)
            packet["records"].append({
                # Empty string, never None: `str(None)` is "None", which would
                # satisfy the "translation present" check and print the word.
                "id": record_id, "source": candidate["source"], "translation": "",
                "status": "needs_translation", "page": index, "bbox": box,
                "kind": "outline", "role": "body", "rotation": rotation,
                "review_note": "recovered by recover_faint.py from the light-grey layer",
            })
            for context in packet.get("page_context", []):
                if context.get("page") == index:
                    context.setdefault("records", []).append(
                        {"id": record_id, "source": candidate["source"], "page": index,
                         "rotation": rotation})
            added.append({"id": record_id, "source": candidate["source"], "bbox": box,
                          "rotation": rotation, "confidence": candidate["confidence"],
                          "rotation_review_required": bool(vertical)})

    report = {"passed": True, "tool": "recover_faint", "dpi": args.dpi,
              "threshold": args.threshold, "recovered": len(added),
              "vertical_labels": sum(1 for a in added if a["rotation"]),
              "labels": added, "dry_run": args.dry_run}
    write_json(job / "faint-labels.json", report)
    if not args.dry_run:
        write_json(inventory_path, inventory)
        write_json(packet_path, packet)
    print(json.dumps({k: v for k, v in report.items() if k != "labels"}, ensure_ascii=False))
    for entry in added:
        print("  {id} {rotation} {confidence} {source!r} {bbox}".format(**entry))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
