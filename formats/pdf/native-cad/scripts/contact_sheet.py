#!/usr/bin/env python3
"""Build one contact sheet covering every changed region, with lost/gained counts.

Visual review of a replaced drawing otherwise costs many separate renders and
image reads. This produces a single PNG: for each applied record the source crop
above the candidate crop, captioned with the label pair and the bidirectional
pixel difference, so one look plus one JSON summary replaces the whole sweep.

  python scripts/contact_sheet.py <job-dir>
  python scripts/contact_sheet.py <job-dir> --candidate <job-dir>/translated-native-cad.pdf
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFont

CELL_WIDTH = 560
CAPTION = 58
PAD = 6
DPI = 220
INK_SUM = 300
STATUSES = ("translated", "cover_only")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def crop(page: pymupdf.Page, rect: pymupdf.Rect, width: int, height: int) -> Image.Image:
    pix = page.get_pixmap(dpi=DPI, clip=rect)
    image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    factor = min(width / image.width, height / image.height, 1.0) if image.width else 1.0
    if factor < 1.0:
        image = image.resize((max(1, int(image.width * factor)),
                              max(1, int(image.height * factor))), Image.LANCZOS)
    return image


def cover_mask(rects, clip, shape, sx, sy) -> np.ndarray:
    """Boolean mask of the given page rects projected onto a crop."""
    mask = np.zeros(shape, dtype=bool)
    for item in rects:
        x0 = max(0, int((item.x0 - clip.x0) * sx))
        y0 = max(0, int((item.y0 - clip.y0) * sy))
        x1 = min(shape[1], int((item.x1 - clip.x0) * sx))
        y1 = min(shape[0], int((item.y1 - clip.y0) * sy))
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = True
    return mask


def ink(page: pymupdf.Page, rect: pymupdf.Rect) -> np.ndarray:
    pix = page.get_pixmap(dpi=DPI, clip=rect)
    array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return array[:, :, :3].astype(int).sum(axis=2) < INK_SUM


def font(size: int = 15):
    for name in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("job_dir", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--max", type=int, default=60, help="cap on cells; 0 lists every record")
    parser.add_argument("--pad", type=float, default=PAD)
    parser.add_argument("--slot", type=int, default=150,
                        help="pixel height reserved for each of the source/candidate crops")
    parser.add_argument("--all", action="store_true",
                        help="render every applied region, not only the suspect ones")
    args = parser.parse_args()

    job = args.job_dir
    candidate_path = args.candidate or job / "translated-native-cad.pdf"
    if not candidate_path.exists():
        print(json.dumps({"passed": False, "error": "candidate missing; run apply first"}))
        return 2

    inventory = load_json(job / "source-inventory.json")
    packet = load_json(job / "translation-packet.json")
    supplied = {str(record["id"]): record for record in packet["records"]}
    source_document = pymupdf.open(job / "SOURCE.pdf")
    candidate_document = pymupdf.open(candidate_path)

    slot = args.slot
    row_height = CAPTION + 2 * slot + 14
    applied_by_page: dict[int, dict[str, list]] = {}
    for record in inventory["records"]:
        decision = supplied.get(str(record["id"]))
        if not decision or decision.get("status") not in STATUSES:
            continue
        bucket = applied_by_page.setdefault(int(record["page"]), {"bboxes": [], "targets": []})
        bucket["bboxes"].append(pymupdf.Rect(record["bbox"]) + (-1.5, -1.5, 1.5, 1.5))
        bucket["targets"].append(
            pymupdf.Rect(decision.get("layout_box", record["bbox"])) + (-1.0, -1.0, 1.0, 1.0))

    cells = []
    for record in inventory["records"]:
        decision = supplied.get(str(record["id"]))
        if not decision or decision.get("status") not in STATUSES:
            continue
        applied = applied_by_page[int(record["page"])]
        if decision["status"] == "translated" and not str(decision.get("translation") or "").strip():
            continue
        rect = pymupdf.Rect(decision.get("layout_box", record["bbox"])) + (-args.pad, -args.pad,
                                                                          args.pad, args.pad)
        rect = rect & source_document[int(record["page"])].rect
        if rect.is_empty:
            continue
        source_page = source_document[int(record["page"])]
        candidate_page = candidate_document[int(record["page"])]
        before, after = ink(source_page, rect), ink(candidate_page, rect)
        if before.shape != after.shape:
            after = np.pad(after, ((0, max(0, before.shape[0] - after.shape[0])),
                                   (0, max(0, before.shape[1] - after.shape[1]))),
                           constant_values=False)[:before.shape[0], :before.shape[1]]
        lost, gained = int((before & ~after).sum()), int((after & ~before).sum())
        sx = sy = DPI / 72.0
        # Exclude every applied footprint, not just this record's: neighbouring
        # labels' inserted text otherwise reads as unexplained ink.
        own_mask = cover_mask(applied["bboxes"], rect, before.shape, sx, sy)
        target_mask = cover_mask(applied["targets"], rect, before.shape, sx, sy)
        lost_outside = int((before & ~after & ~own_mask).sum())
        gained_outside = int((after & ~before & ~target_mask).sum())
        verdict = []
        if decision["status"] == "translated" and gained == 0:
            verdict.append("no_target_ink")
        if lost_outside > 40:
            verdict.append("erased_graphic")
        if gained_outside > 120:
            verdict.append("resurrected_path")
        cells.append({
            "lost_outside": lost_outside,
            "gained_outside": gained_outside,
            "suspect": bool(verdict),
            "flags": verdict,
            "id": str(record["id"]),
            "source": str(record["source"]),
            "translation": str(decision.get("translation") or decision.get("target_present") or ""),
            "status": decision["status"],
            "rect": [round(value, 1) for value in rect],
            "lost": lost,
            "gained": gained,
            "source_image": crop(source_page, rect, CELL_WIDTH - 12, slot),
            "candidate_image": crop(candidate_page, rect, CELL_WIDTH - 12, slot),
        })

    cells.sort(key=lambda cell: (not cell["suspect"], -cell["lost_outside"],
                                 -cell["lost"], -cell["gained"]))
    suspects = [cell for cell in cells if cell["suspect"]]
    shown = cells if args.all else suspects
    if args.max:
        shown = shown[:args.max]
    columns = max(1, args.columns)
    rows = (len(shown) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * CELL_WIDTH, max(1, rows) * row_height), (250, 250, 250))
    draw = ImageDraw.Draw(sheet)
    typeface, small = font(15), font(13)
    for position, cell in enumerate(shown):
        column, row = position % columns, position // columns
        x0, y0 = column * CELL_WIDTH, row * row_height
        draw.text((x0 + 6, y0 + 4), "%s %s lost=%d outside=%d gained=%d" % (
            cell["id"], ",".join(cell["flags"]) or "ok", cell["lost"],
            cell["lost_outside"], cell["gained"]), fill=(120, 0, 0), font=typeface)
        draw.text((x0 + 6, y0 + 24), "%s -> %s" % (cell["source"][:46], cell["translation"][:34]),
                  fill=(20, 20, 20), font=small)
        sheet.paste(cell["source_image"], (x0 + 6, y0 + 44))
        sheet.paste(cell["candidate_image"], (x0 + 6, y0 + 44 + slot + 6))
        draw.line([(x0 + 4, y0 + 42 + slot + 3), (x0 + CELL_WIDTH - 4, y0 + 42 + slot + 3)],
                  fill=(205, 205, 205))
        draw.line([(x0, y0), (x0 + CELL_WIDTH, y0)], fill=(190, 190, 190))

    out = args.out or job / "contact-sheet.png"
    sheet.save(out)
    summary = {"passed": not suspects, "tool": "contact_sheet", "image": str(out),
               "cells": len(cells), "suspects": len(suspects), "shown": len(shown),
               "clean": len(cells) - len(suspects),
               "flags": [{"id": cell["id"], "flags": cell["flags"], "source": cell["source"],
                          "lost_outside": cell["lost_outside"], "gained": cell["gained"]}
                         for cell in suspects[:12]]}
    (job / "contact-sheet.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
