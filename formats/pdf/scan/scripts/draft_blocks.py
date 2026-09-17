"""Draft semantic-block grouping from a scan extraction report.

Groups OCR lines into provisional blocks by vertical proximity so a human/
agent review pass can assign translations. Output: draft-groups.json with
geometry (union box, padded clean box, median line height) per group.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


HEADING_RE = re.compile(r"^(?:[IVXLCDM]+|\d+)(?:[.\-]?\d+)*(?:[.)\-]+|\s+-)\s*", re.IGNORECASE)
LIST_RE = re.compile(r"^(?:[-•]|[a-zA-Z]\)|\d+[.)])\s+")
LETTER_MARKER_RE = re.compile(r"^\.?\s*[a-zA-Z]\)(?:\s|$)")


def _line_role(line: dict, page_height: float | None) -> str:
    if int(line.get("rotation", 0)) != 0:
        return "diagram_label"
    y0, y1 = float(line["box"][1]), float(line["box"][3])
    if page_height:
        if y1 <= page_height * 0.06:
            return "header"
        if y0 >= page_height * 0.84:
            return "footer"
    text = str(line.get("text", "")).strip()
    if re.search(r"\s{2,}", text) and len(re.findall(r"\d+(?:[.,]\d+)?", text)) >= 2:
        return "table_cell"
    if LETTER_MARKER_RE.match(text):
        return "list_item"
    if HEADING_RE.match(text) and len(text) <= 90:
        return "heading"
    if LIST_RE.match(text):
        return "list_item"
    return "body"


def _can_join(group: list[dict], line: dict, median_h: float) -> bool:
    last = group[-1]
    if last["_role"] not in {"body", "list_item"} or line["_role"] not in {"body", "list_item"}:
        return False
    if line['_role'] == 'list_item':
        return False
    if int(last.get("rotation", 0)) != int(line.get("rotation", 0)):
        return False
    lx0, ly0, lx1, ly1 = map(float, last["box"])
    x0, y0, x1, y1 = map(float, line["box"])
    gap = y0 - ly1
    overlap_x = min(lx1, x1) - max(lx0, x0)
    narrower = max(1.0, min(lx1 - lx0, x1 - x0))
    same_column = overlap_x >= 0.35 * narrower and abs(x0 - last.get('_body_x0', lx0)) <= 2.5 * median_h
    return -0.35 * median_h <= gap <= 1.8 * median_h and same_column


def _coalesce_same_baseline_fragments(rows: list[dict], median_h: float) -> list[dict]:
    """Join nearby OCR fragments that belong to one physical text line."""
    bands: list[list[dict]] = []
    for source in sorted(rows, key=lambda line: (float(line["box"][1]), float(line["box"][0]))):
        y0, y1 = float(source["box"][1]), float(source["box"][3])
        band = next(
            (
                item
                for item in bands
                if min(max(float(member["box"][3]) for member in item), y1)
                - max(min(float(member["box"][1]) for member in item), y0)
                >= 0.7 * max(1.0, min(y1 - y0, median_h))
            ),
            None,
        )
        (band if band is not None else bands.append([]) or bands[-1]).append(source)

    logical: list[dict] = []
    for band in bands:
        for source in sorted(band, key=lambda line: float(line["box"][0])):
            line = dict(source)
            line["_line_ids"] = [source["id"]]
            line["_clean_boxes"] = [list(map(float, source["box"]))]
            candidate = logical[-1] if logical and logical[-1].get("_band") is band else None
            gap_x = float(line["box"][0]) - float(candidate["box"][2]) if candidate else float("inf")
            is_marker = candidate is not None and re.fullmatch(r'\.?\s*[a-zA-Z]\)', str(candidate.get('text', '')).strip())
            max_gap = (4 if is_marker else 1.5) * median_h
            if candidate is None or not (-0.15 * median_h <= gap_x <= max_gap):
                line["_band"] = band
                logical.append(line)
                continue
            if is_marker:
                candidate['_body_x0'] = float(line['box'][0])
            candidate["text"] = f'{str(candidate.get("text", "")).strip()} {str(line.get("text", "")).strip()}'.strip()
            candidate["box"] = [min(float(candidate["box"][0]), float(line["box"][0])), min(float(candidate["box"][1]), float(line["box"][1])), max(float(candidate["box"][2]), float(line["box"][2])), max(float(candidate["box"][3]), float(line["box"][3]))]
            candidate["score"] = min(float(candidate.get("score", 0)), float(line.get("score", 0)))
            candidate["_line_ids"].extend(line["_line_ids"])
            candidate["_clean_boxes"].extend(line["_clean_boxes"])
    return logical


def group_page_lines(lines: list[dict], page_height: float | None = None) -> list[dict]:
    rows = [line for line in lines if int(line.get("rotation", 0)) == 0]
    rotated = [line for line in lines if int(line.get("rotation", 0)) != 0]
    rows.sort(key=lambda line: (float(line["box"][1]), float(line["box"][0])))

    heights = [float(line["box"][3]) - float(line["box"][1]) for line in rows]
    heights.sort()
    median_h = heights[len(heights) // 2] if heights else 20.0
    rows = _coalesce_same_baseline_fragments(rows, median_h)
    rows.sort(key=lambda line: (float(line["box"][1]), float(line["box"][0])))

    for line in rows:
        line["_role"] = _line_role(line, page_height)

    groups: list[list[dict]] = []
    for line in rows:
        placed = False
        # A later row may continue only the nearest preceding group in its
        # column. Skipping a heading/new paragraph steals its continuation.
        for group in sorted(groups, key=lambda g: float(g[-1]['box'][1]), reverse=True):
            previous = group[-1]['box']
            overlap = min(previous[2], line['box'][2]) - max(previous[0], line['box'][0])
            if overlap < .35 * min(previous[2] - previous[0], line['box'][2] - line['box'][0]):
                continue
            if _can_join(group, line, median_h):
                group.append(line)
                placed = True
            break
        if not placed:
            groups.append([line])

    out = []
    for index, group in enumerate(groups, 1):
        raw_box = [
            min(float(line["box"][0]) for line in group),
            min(float(line["box"][1]) for line in group),
            max(float(line["box"][2]) for line in group),
            max(float(line["box"][3]) for line in group),
        ]
        heights_g = sorted(float(line["box"][3]) - float(line["box"][1]) for line in group)
        group_median_h = heights_g[len(heights_g) // 2]
        pad = 0.25 * group_median_h
        box = [
            max(0.0, raw_box[0] - pad),
            max(0.0, raw_box[1] - pad),
            raw_box[2] + pad,
            min(page_height, raw_box[3] + pad) if page_height else raw_box[3] + pad,
        ]
        out.append(
            {
                "page": group[0]["page"],
                "line_ids": [line_id for line in group for line_id in line.get("_line_ids", [line["id"]])],
                "box": [round(v, 1) for v in box],
                "clean_boxes": [
                    [round(float(v), 1) for v in clean_box]
                    for line in group
                    for clean_box in line.get("_clean_boxes", [line["box"]])
                ],
                "median_h": round(group_median_h, 1),
                "text": " ".join(str(line.get("text", "")).strip() for line in group),
                "min_score": round(min(float(line.get("score", 0)) for line in group), 3),
                "rotation": 0,
                "role": group[0]["_role"],
                "grouping_reason": "page-aware-continuation" if len(group) > 1 else "structural-boundary",
            }
        )

    for line in sorted(rotated, key=lambda item: (item["page"], float(item["box"][0]))):
        box = [round(float(v), 1) for v in line["box"]]
        out.append(
            {
                "page": line["page"],
                "line_ids": [line["id"]],
                "box": box,
                "clean_boxes": [box],
                "median_h": round(float(box[3]) - float(box[1]), 1),
                "text": str(line.get("text", "")).strip(),
                "min_score": round(float(line.get("score", 0)), 3),
                "rotation": int(line.get("rotation", 0)),
                "role": "diagram_label",
                "grouping_reason": "rotation-isolated",
            }
        )
    return out


def translation_payload(report: dict) -> dict:
    by_page: dict[int, list[dict]] = {}
    for line in report["source_lines"]:
        by_page.setdefault(int(line["page"]), []).append(line)
    groups: list[dict] = []
    page_heights = {int(page["source_page"]): float(page.get("pixel_height", 0)) for page in report.get("pages", [])}
    pages = []
    for page in report.get("selected_pages", sorted(by_page)):
        ordered = sorted(by_page.get(page, []), key=lambda row: (row["box"][1], row["box"][0]))
        page_groups = group_page_lines([dict(row) for row in ordered], page_heights.get(page) or None)
        for index, group in enumerate(page_groups, 1):
            group["id"] = f"p{page:02d}-r{index:03d}"
        groups.extend(page_groups)
        pages.append({"source_page": page, "ordered_source_ids": [line_id for group in page_groups for line_id in group["line_ids"]],
                      "page_context": "\n".join(group["text"] for group in page_groups),
                      "region_ids": [group["id"] for group in page_groups],
                      "ocr_review_candidates": next((p.get('ocr_review_candidates', []) for p in report.get('pages', [])
                                                       if p['source_page'] == page), [])})
    return {
        "source_sha256": report["source_sha256"],
        "group_count": len(groups),
        "groups": groups,
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = translation_payload(load_report(Path(args.extraction)))
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"groups": payload["group_count"], "output": str(Path(args.output).resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
