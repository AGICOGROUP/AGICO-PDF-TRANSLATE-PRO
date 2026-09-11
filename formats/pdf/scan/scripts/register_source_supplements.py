"""Bind visually confirmed OCR omissions to replacement blocks and glyph cleanup.

This edits a manifest, not a PDF or review. It does not detect/translate text,
guess geometry, enlarge target boxes, or establish semantic/visual acceptance.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import tempfile

from contracts import validate_manifest


def register_supplements(manifest: dict, payload: dict) -> dict:
    source_hash = manifest.get("source_sha256")
    if not source_hash or payload.get("source_sha256") != source_hash:
        raise ValueError("supplement source_sha256 does not match manifest")
    items = payload.get("supplements")
    if not isinstance(items, list) or not items:
        raise ValueError("supplements must be a nonempty list")
    result = copy.deepcopy(manifest)
    pages = {page["source_page"]: page for page in result["pages"]}
    blocks = {block["id"]: block for block in result["blocks"]}
    known_ids = {line["id"] for line in result["source_lines"]}
    for item in items:
        block = blocks.get(item.get("block_id"))
        if block is None or block.get("action") != "replace" or block.get("status") != "translated":
            raise ValueError("supplement requires an existing translated replacement block")
        for field in ("source", "translation"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"supplement requires complete nonblank {field}")
        lines = item.get("source_lines")
        if not isinstance(lines, list) or not lines:
            raise ValueError("supplement source_lines must locate the missing glyphs")
        page = pages[block["page"]]
        if "clean_boxes" not in block:
            block["clean_boxes"] = [block.pop("clean_box")]
        for raw_line in lines:
            line_id = raw_line.get("id")
            if not isinstance(line_id, str) or not line_id.strip() or line_id in known_ids:
                raise ValueError("supplement source ID must be new and nonblank; do not reapply a saved patch")
            if raw_line.get("page") != block["page"]:
                raise ValueError("supplement page must match its replacement block")
            if raw_line.get("rotation") != block.get("rotation", 0):
                raise ValueError("supplement rotation must match its replacement block")
            if not isinstance(raw_line.get("text"), str) or not raw_line["text"].strip():
                raise ValueError("supplement requires visually confirmed source text")
            box = raw_line.get("box")
            if (not isinstance(box, list) or len(box) != 4
                    or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in box)):
                raise ValueError("supplement box must have four finite pixel coordinates")
            x0, y0, x1, y1 = box
            if not (0 <= x0 < x1 <= page["pixel_width"] and 0 <= y0 < y1 <= page["pixel_height"]):
                raise ValueError("supplement glyph box is outside its source-render page")
            line = copy.deepcopy(raw_line)
            line["origin"] = "visual_supplement"
            result["source_lines"].append(line)
            block["source_line_ids"].append(line_id)
            block["clean_boxes"].append(list(box))
            known_ids.add(line_id)
        # Caller supplies the complete passage in reading order. Appending just the
        # translation would duplicate content already supplemented during translation.
        block["source"] = item["source"]
        block["translation"] = item["translation"]
    validate_manifest(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--supplements", required=True)
    parser.add_argument("--output", required=True, help="Updated JSON manifest; may equal --manifest")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
    payload = json.loads(Path(args.supplements).read_text(encoding="utf-8-sig"))
    try:
        updated = register_supplements(manifest, payload)
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(f"invalid supplement: {exc}")
    output = Path(args.output).resolve()
    if output.suffix.lower() != ".json":
        parser.error("output must be a JSON manifest, not the source PDF")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(updated, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print(json.dumps({
        "output": str(output),
        "registered_source_lines": len(updated["source_lines"]) - len(manifest["source_lines"]),
        "pages_requiring_review": sorted({line["page"] for item in payload["supplements"]
                                           for line in item["source_lines"]}),
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
