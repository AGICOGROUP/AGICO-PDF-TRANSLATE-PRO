#!/usr/bin/env python
"""Locate and audit raster text labels when no OCR engine is available.

Subcommands:
  detect   list text-line boxes in a source image (glyph components or projection)
  grid     write a zoomed crop with a labelled source-pixel coordinate grid
  sheet    tile detected line crops into one readable contact sheet
  residue  audit a cleaned base: report missed glyphs, erased structure, and
           pixels changed outside every declared cleanup box

The residue audit is the machine check behind "review residual hits": a cleaned
image must report zero missed glyphs before the vector overlay step.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

try:
    import cv2
except ImportError:  # pragma: no cover - fallback keeps the tool usable
    cv2 = None


def load(path):
    return np.array(Image.open(path).convert("RGB"))


def ink_mask(image, dark_below=200, sat_above=90):
    values = image.astype(np.int16)
    maximum = values.max(axis=2)
    minimum = values.min(axis=2)
    return ((maximum < dark_below) | ((maximum - minimum) > sat_above)).astype(np.uint8)


def components(mask, min_height=7, max_height=34, max_width=300,
               min_area=28, min_density=0.20):
    """Return glyph-like boxes; hatch strokes and rules fail the density test."""
    boxes = []
    if cv2 is not None:
        count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
        for index in range(1, count):
            x, y, w, h, area = (int(v) for v in stats[index])
            if min_height <= h <= max_height and 3 <= w <= max_width and area >= min_area:
                if area / float(w * h) >= min_density:
                    boxes.append([x, y, x + w, y + h])
        return boxes
    # Projection fallback: split into row bands, then column runs inside a band.
    rows = mask.sum(axis=1)
    band, bands = None, []
    for y, value in enumerate(rows):
        if value and band is None:
            band = y
        elif not value and band is not None:
            bands.append((band, y))
            band = None
    if band is not None:
        bands.append((band, mask.shape[0]))
    for top, bottom in bands:
        if not min_height <= bottom - top <= max_height:
            continue
        columns = mask[top:bottom].sum(axis=0)
        run = None
        for x, value in enumerate(columns):
            if value and run is None:
                run = x
            elif not value and run is not None:
                if x - run >= 3 and (x - run) <= max_width:
                    boxes.append([run, top, x, bottom])
                run = None
    return boxes


def group_lines(boxes, max_gap_factor=1.5, baseline_factor=0.38,
                max_span_factor=46.0):
    """Join glyphs into text lines using a shared baseline and a word-sized gap."""
    lines = []
    for box in sorted(boxes, key=lambda item: item[0]):
        ax0, ay0, ax1, ay1 = box
        aheight = ay1 - ay0
        acy = 0.5 * (ay0 + ay1)
        best, best_score = None, None
        for line in lines:
            x0, y0, x1, y1 = line["box"]
            height = max(y1 - y0, aheight)
            if abs(acy - 0.5 * (y0 + y1)) > baseline_factor * height:
                continue
            gap = ax0 - x1
            if gap > max_gap_factor * height + 4 or gap < -0.6 * aheight:
                continue
            if (ax1 - x0) > max_span_factor * height:
                continue
            score = abs(acy - 0.5 * (y0 + y1)) + max(gap, 0) * 0.1
            if best_score is None or score < best_score:
                best, best_score = line, score
        if best is None:
            lines.append({"box": list(box), "glyphs": 1})
        else:
            x0, y0, x1, y1 = best["box"]
            best["box"] = [min(x0, ax0), min(y0, ay0), max(x1, ax1), max(y1, ay1)]
            best["glyphs"] += 1
    lines.sort(key=lambda line: (line["box"][1], line["box"][0]))
    return lines


def cmd_detect(args):
    image = load(args.image)
    mask = ink_mask(image, args.dark_below, args.sat_above)
    lines = group_lines(components(mask))
    os.makedirs(args.out, exist_ok=True)
    lines_path = os.path.join(args.out, "lines.json")
    with open(lines_path, "w", encoding="utf-8") as handle:
        json.dump(lines, handle)
    print("engine", "cv2" if cv2 is not None else "projection")
    print("lines", len(lines))
    for index, line in enumerate(lines):
        x0, y0, x1, y1 = line["box"]
        print("L%03d [%4d,%4d,%4d,%4d] w=%3d h=%2d g=%d"
              % (index, x0, y0, x1, y1, x1 - x0, y1 - y0, line["glyphs"]))
    if args.annotate:
        view = Image.fromarray(image.copy())
        draw = ImageDraw.Draw(view)
        for index, line in enumerate(lines):
            x0, y0, x1, y1 = line["box"]
            draw.rectangle([x0 - 1, y0 - 2, x1 + 1, y1 + 1], outline=(255, 0, 255))
            draw.text((x0, max(0, y0 - 13)), str(index), fill=(255, 0, 0))
        target = os.path.join(args.out, "annotated.png")
        view.save(target)
        print("annotated", target)
    return 0


def cmd_grid(args):
    x0, y0, x1, y1 = args.box
    image = Image.open(args.image).convert("RGB").crop((x0, y0, x1, y1))
    image = image.resize((int(image.width * args.scale),
                          int(image.height * args.scale)), Image.LANCZOS)
    draw = ImageDraw.Draw(image)
    for sx in range(x0 - x0 % args.step + args.step, x1, args.step):
        px = int((sx - x0) * args.scale)
        major = sx % (args.step * 2) == 0
        draw.line([(px, 0), (px, image.height)],
                  fill=(255, 0, 0) if major else (255, 190, 190))
        if major:
            draw.text((px + 2, 2), str(sx), fill=(255, 0, 0))
    for sy in range(y0 - y0 % args.step + args.step, y1, args.step):
        py = int((sy - y0) * args.scale)
        major = sy % (args.step * 2) == 0
        draw.line([(0, py), (image.width, py)],
                  fill=(0, 0, 255) if major else (190, 190, 255))
        if major:
            draw.text((2, py + 2), str(sy), fill=(0, 0, 255))
    image.save(args.out)
    print(args.out, image.size, "origin", x0, y0, "scale", args.scale)
    return 0


def cmd_sheet(args):
    image = Image.open(args.image).convert("RGB")
    with open(args.lines, encoding="utf-8") as handle:
        lines = json.load(handle)
    tiles = []
    for index, line in enumerate(lines):
        bx0, by0, bx1, by1 = line["box"]
        pad = 4
        crop = image.crop((max(0, bx0 - pad), max(0, by0 - pad),
                           min(image.width, bx1 + pad),
                           min(image.height, by1 + pad)))
        crop = crop.resize((max(1, int(crop.width * args.scale)),
                            max(1, int(crop.height * args.scale))), Image.LANCZOS)
        tile = Image.new("RGB", (crop.width + 90, crop.height + 8), (255, 255, 255))
        tile.paste(crop, (88, 4))
        ImageDraw.Draw(tile).text((4, 4), "#%02d" % index, fill=(200, 0, 0))
        tiles.append(tile)
    if not tiles:
        print("no lines")
        return 1
    width = max(tile.width for tile in tiles)
    height = max(tile.height for tile in tiles)
    rows = (len(tiles) + args.columns - 1) // args.columns
    sheet = Image.new("RGB", (width * args.columns, height * rows), (245, 245, 245))
    for index, tile in enumerate(tiles):
        row, column = divmod(index, args.columns)
        sheet.paste(tile, (column * width, row * height))
    sheet.save(args.out)
    print(args.out, sheet.size)
    return 0


def sha256(path):
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def suggest_mode(image, box):
    """Pick a cleanup mode from the label's own ink colour and its surround."""
    x0, y0, x1, y1 = box
    crop = image[y0:y1, x0:x1].astype(np.int16)
    surround = image[max(0, y0 - 6):y1 + 6, max(0, x0 - 6):x1 + 6]
    near_white = float((surround.max(axis=2) >= 246).mean())
    values = crop.reshape(-1, 3)
    ink = values[(values.max(axis=1) < 200)
                 | ((values.max(axis=1) - values.min(axis=1)) > 90)]
    if len(ink) == 0:
        return "text_only_area", [0.0, 0.0, 0.0]
    median = [round(float(v) / 255.0, 3) for v in np.median(ink, axis=0)]
    red, green, blue = (float(v) for v in np.median(ink, axis=0))
    if near_white >= 0.90:
        return "text_only_area", median
    if red - green > 28 and red - blue > 28:
        return "red", median
    if green - red > 22 and blue - red > 22 and green > 105 and blue > 105:
        return "cyan", median
    return "neutral_plain", median


def inventory_entry(inventory_path, image_id):
    with open(inventory_path, encoding="utf-8") as handle:
        inventory = json.load(handle)
    items = inventory.get("images", inventory if isinstance(inventory, list) else [])
    for item in items:
        if str(item.get("id")) == image_id:
            return item
    raise SystemExit("image id %s not in %s" % (image_id, inventory_path))


def inventory_placement(entry, page):
    """Read the PDF placement straight from an inventory placement record."""
    records = entry.get("placements") or []
    if not isinstance(records, list):
        records = [records]
    chosen = None
    for record in records:
        if page is None or int(record.get("page", page or 0)) == int(page):
            chosen = record
            break
    if chosen is None:
        raise SystemExit("no placement for page %s in inventory entry %s"
                         % (page, entry.get("id")))
    x0, y0 = float(chosen["x0"]), float(chosen["y0"])
    x1, y1 = float(chosen["x1"]), float(chosen["y1"])
    # inventory y values are already PDF bottom-origin: never flip them
    return [x0, y0, x1 - x0, y1 - y0], int(chosen.get("page", page or 0))


def cmd_plan(args):
    """Emit a fill-in label plan: every detected text line with its box, a
    suggested cleanup mode, the sampled ink colour, and the PDF placement read
    straight from the image inventory, so no coordinate is hand-typed and no
    Y axis is flipped by hand."""
    entry = inventory_entry(args.inventory, args.image_id)
    source = args.image or entry.get("path")
    if not source or not os.path.exists(source):
        raise SystemExit("source image not found: %s" % source)
    image = load(source)
    mask = ink_mask(image, args.dark_below, args.sat_above)
    lines = group_lines(components(mask))
    placement, page = inventory_placement(entry, args.page)
    plan = {
        "image_id": args.image_id,
        "page": page,
        "source": os.path.abspath(source),
        "source_sha256": entry.get("sha256") or sha256(source),
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "placement": placement,
        "lines": [],
    }
    for index, line in enumerate(lines):
        mode, colour = suggest_mode(image, line["box"])
        plan["lines"].append({
            "id": "%s-L%02d" % (args.image_id, index),
            "box": line["box"],
            "glyphs": line["glyphs"],
            "suggested_mode": mode,
            "color": colour,
            "bold": False,
            "source_text": "",
            "translation": "",
            "claim": "unresolved",
        })
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(plan, handle, ensure_ascii=False, indent=1)
    print("plan_lines", len(plan["lines"]))
    print("placement", plan["placement"], "page", plan["page"])
    print("source_sha256", plan["source_sha256"])
    print("reuse_only_when_image_sha256_matches")
    return 0


def residue_report(original_path, cleaned_path, metadata_path=None,
                   dark_below=215, sat_above=60, plan_path=None):
    """Measure missed glyphs, untouched boxes and out-of-box changes.

    A text line that no declared cleanup box covers is invisible to the pixel
    audit, so passing --plan also reports lines the reviewer never claimed.
    """
    original = load(original_path)
    clean = load(cleaned_path)
    if original.shape != clean.shape:
        raise ValueError("dimensions differ: %s vs %s"
                         % (original.shape, clean.shape))
    boxes = []
    if metadata_path:
        with open(metadata_path, encoding="utf-8") as handle:
            metadata = json.load(handle)
        for item in metadata.get("images", []):
            if os.path.abspath(str(item.get("source", ""))) == os.path.abspath(original_path):
                for region in item.get("regions", []):
                    if region.get("clean_box"):
                        boxes.append([int(v) for v in region["clean_box"]])
    allowed = np.zeros(original.shape[:2], dtype=bool)
    for x0, y0, x1, y1 in boxes:
        allowed[y0:y1, x0:x1] = True
    diff = np.any(original != clean, axis=2)
    outside = int((diff & ~allowed).sum()) if boxes else -1

    mask = ink_mask(clean, dark_below, sat_above)
    source_mask = ink_mask(original, dark_below, sat_above)
    missed, structure = [], []
    for line in group_lines(components(mask)):
        x0, y0, x1, y1 = line["box"]
        before = source_mask[y0:y1, x0:x1].sum()
        after = mask[y0:y1, x0:x1].sum()
        changed = int(diff[y0:y1, x0:x1].sum())
        declared = any(allowed[max(0, min(y, allowed.shape[0] - 1)),
                               max(0, min(x, allowed.shape[1] - 1))]
                       for y in (y0, (y0 + y1) // 2, y1 - 1)
                       for x in (x0, (x0 + x1) // 2, x1 - 1))
        # Ink inside (or overlapping) a declared cleanup box is a missed glyph
        # even when the cleanup removed nothing there.
        if declared or changed >= max(12, int(0.02 * (x1 - x0) * (y1 - y0))):
            missed.append({"box": line["box"], "ink_before": int(before),
                           "ink_after": int(after), "changed": changed,
                           "declared": declared})
        else:
            structure.append({"box": line["box"], "changed": changed})
    # A declared box that removed almost nothing is misplaced: its label is
    # still on the page and now hides among the untouched "structure" hits.
    no_effect = []
    for box in boxes:
        bx0, by0, bx1, by1 = box
        source_ink = int(source_mask[by0:by1, bx0:bx1].sum())
        removed = int(diff[by0:by1, bx0:bx1].sum())
        if source_ink >= 25 and removed < max(8, int(0.05 * source_ink)):
            no_effect.append({"box": box, "source_ink": source_ink,
                              "removed": removed})
    unclaimed = []
    if plan_path:
        with open(plan_path, encoding="utf-8") as handle:
            plan = json.load(handle)
        for line in plan.get("lines", []):
            # Excluding a line is allowed, but only with a stated reason, so a
            # forgotten label cannot be waved away as "artwork".
            if line.get("claim") == "excluded_artwork" and str(
                    line.get("exclude_reason", "")).strip():
                continue
            x0, y0, x1, y1 = line["box"]
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            if not any(bx0 <= cx < bx1 and by0 <= cy < by1 for bx0, by0, bx1, by1 in boxes):
                unclaimed.append({"id": line["id"], "box": line["box"]})
    return {"missed": missed, "structure": structure, "no_effect": no_effect,
            "outside": outside, "clean_boxes": len(boxes), "unclaimed": unclaimed}


def cmd_residue(args):
    report = residue_report(args.original, args.cleaned, args.metadata,
                            args.dark_below, args.sat_above, args.plan)
    missed, structure, no_effect, outside = (
        report["missed"], report["structure"], report["no_effect"],
        report["outside"])
    print("residue_unclaimed_text_lines", len(report["unclaimed"]))
    for item in report["unclaimed"]:
        print("  UNCLAIMED", item["id"], item["box"])
    print("residue_missed_glyphs", len(missed))
    for item in missed:
        print("  MISSED%s" % ("(declared)" if item["declared"] else ""), item["box"],
              "ink %d->%d changed=%d" % (item["ink_before"], item["ink_after"],
                                         item["changed"]))
    print("structure_or_unlisted", len(structure))
    for item in structure:
        print("  check ", item["box"], "changed=%d" % item["changed"])
    print("no_effect_clean_boxes", len(no_effect))
    for item in no_effect:
        print("  NOEFFECT", item["box"], "source_ink=%d removed=%d"
              % (item["source_ink"], item["removed"]))
    if report["clean_boxes"]:
        print("pixels_changed_outside_clean_boxes", outside)
    else:
        print("pixels_changed_outside_clean_boxes unknown (pass --metadata)")
    return 1 if missed or no_effect or report["unclaimed"] or (outside > 0) else 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    detect = sub.add_parser("detect")
    detect.add_argument("image")
    detect.add_argument("--out", required=True)
    detect.add_argument("--annotate", action="store_true")
    detect.add_argument("--dark-below", type=int, default=215)
    detect.add_argument("--sat-above", type=int, default=60)
    detect.set_defaults(func=cmd_detect)

    grid = sub.add_parser("grid")
    grid.add_argument("image")
    grid.add_argument("--box", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"),
                      required=True)
    grid.add_argument("--out", required=True)
    grid.add_argument("--scale", type=float, default=2.0)
    grid.add_argument("--step", type=int, default=50)
    grid.set_defaults(func=cmd_grid)

    sheet = sub.add_parser("sheet")
    sheet.add_argument("image")
    sheet.add_argument("--lines", required=True)
    sheet.add_argument("--out", required=True)
    sheet.add_argument("--columns", type=int, default=2)
    sheet.add_argument("--scale", type=float, default=2.0)
    sheet.set_defaults(func=cmd_sheet)

    plan = sub.add_parser("plan")
    plan.add_argument("image", nargs="?", help="defaults to the inventory path")
    plan.add_argument("--image-id", required=True)
    plan.add_argument("--inventory", required=True)
    plan.add_argument("--page", type=int)
    plan.add_argument("--out", required=True)
    plan.add_argument("--dark-below", type=int, default=215)
    plan.add_argument("--sat-above", type=int, default=60)
    plan.set_defaults(func=cmd_plan)

    residue = sub.add_parser("residue")
    residue.add_argument("original")
    residue.add_argument("cleaned")
    residue.add_argument("--metadata")
    residue.add_argument("--plan", help="label plan JSON; lines no box claims "
                                        "count as untranslated")
    residue.add_argument("--dark-below", type=int, default=200)
    residue.add_argument("--sat-above", type=int, default=90)
    residue.set_defaults(func=cmd_residue)
    return parser


def main():
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
