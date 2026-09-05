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


def _line_role(line: dict, page_height: float | None) -> str:
    if int(line.get("rotation", 0)) != 0:
        return "diagram_label"
    y0, y1 = float(line["box"][1]), float(line["box"][3])
    if page_height:
        if y1 <= page_height * 0.12:
            return "header"
        if y0 >= page_height * 0.88:
            return "footer"
    text = str(line.get("text", "")).strip()
    if re.search(r"\s{2,}", text) and len(re.findall(r"\d+(?:[.,]\d+)?", text)) >= 2:
        return "table_cell"
    if HEADING_RE.match(text) and len(text) <= 90:
        return "heading"
    if LIST_RE.match(text):
        return "list_item"
    return "body"


def _can_join(group: list[dict], line: dict, median_h: float) -> bool:
    last = group[-1]
    if last["_role"] not in {"body", "list_item"} or line["_role"] not in {"body", "list_item"}:
        return False
    if int(last.get("rotation", 0)) != int(line.get("rotation", 0)):
        return False
    lx0, ly0, lx1, ly1 = map(float, last["box"])
    x0, y0, x1, y1 = map(float, line["box"])
    gap = y0 - ly1
    overlap_x = min(lx1, x1) - max(lx0, x0)
    narrower = max(1.0, min(lx1 - lx0, x1 - x0))
    same_column = overlap_x >= 0.35 * narrower and abs(x0 - lx0) <= 2.5 * median_h
    return -0.35 * median_h <= gap <= 1.8 * median_h and same_column


def group_page_lines(lines: list[dict], page_height: float | None = None) -> list[dict]:
    rows = [line for line in lines if int(line.get("rotation", 0)) == 0]
    rotated = [line for line in lines if int(line.get("rotation", 0)) != 0]
    rows.sort(key=lambda line: (float(line["box"][1]), float(line["box"][0])))

    heights = [float(line["box"][3]) - float(line["box"][1]) for line in rows]
    heights.sort()
    median_h = heights[len(heights) // 2] if heights else 20.0

    for line in rows:
        line["_role"] = _line_role(line, page_height)

    groups: list[list[dict]] = []
    for line in rows:
        placed = False
        for group in groups:
            if _can_join(group, line, median_h):
                group.append(line)
                placed = True
                break
        if not placed:
            groups.append([line])

    out = []
    for index, group in enumerate(groups, 1):
        box = [
            min(float(line["box"][0]) for line in group),
            min(float(line["box"][1]) for line in group),
            max(float(line["box"][2]) for line in group),
            max(float(line["box"][3]) for line in group),
        ]
        heights_g = sorted(float(line["box"][3]) - float(line["box"][1]) for line in group)
        out.append(
            {
                "page": group[0]["page"],
                "line_ids": [line["id"] for line in group],
                "box": [round(v, 1) for v in box],
                "clean_boxes": [[round(float(v), 1) for v in line["box"]] for line in group],
                "median_h": round(heights_g[len(heights_g) // 2], 1),
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = load_report(Path(args.extraction))
    by_page: dict[int, list[dict]] = {}
    for line in report["source_lines"]:
        by_page.setdefault(int(line["page"]), []).append(line)
    groups: list[dict] = []
    page_heights = {int(page["source_page"]): float(page.get("pixel_height", 0)) for page in report.get("pages", [])}
    for page in sorted(by_page):
        groups.extend(group_page_lines(by_page[page], page_heights.get(page) or None))
    payload = {
        "source_sha256": report["source_sha256"],
        "group_count": len(groups),
        "groups": groups,
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"groups": len(groups), "output": str(Path(args.output).resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
