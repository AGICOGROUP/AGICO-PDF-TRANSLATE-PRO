#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


BLOCK_ID_RE = re.compile(r"p\d{4}-b\d{4}")


def load_pipeline(path: Path):
    spec = importlib.util.spec_from_file_location("pdf_translation_pipeline_qa", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import translation pipeline: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def minimum_body_font_size(style: dict[str, Any]) -> float:
    raw = max(9.5, float(style.get("size", 9)) * 0.6)
    return math.floor(raw * 4) / 4


def bound_cell_failures(source_blocks, rebuild, pipeline):
    """Check actual cell rendering, independently of a claimed visual pass."""
    draws_by_id = {}
    for item in rebuild.get('blocks', []):
        for block_id in set(BLOCK_ID_RE.findall(str(item.get('id', '')))):
            draws_by_id.setdefault(block_id, []).extend(item.get('draws', []))
    failures = []
    canonical = lambda text: re.sub(r'\s+', '', pipeline.normalized_anchor_text(text))
    for block_id, block in source_blocks.items():
        cell = block.get('source_cell_bbox')
        if cell is None:
            continue
        draws = draws_by_id.get(block_id, [])
        reason = None
        if len(draws) != 1:
            reason = 'cell must be rendered exactly once'
        elif canonical(draws[0].get('rendered', '')) != canonical(pipeline.prepared_translation(block)):
            reason = 'rendered cell text differs from its translation'
        else:
            boxes = draws[0].get('drawn_boxes', [])
            if not boxes:
                reason = 'missing cell line geometry'
            elif any(b[0] < cell[0] - 0.5 or b[1] < cell[1] - 0.5
                     or b[2] > cell[2] + 0.5 or b[3] > cell[3] + 0.5 for b in boxes):
                reason = 'text extends outside its physical cell'
        if reason:
            failures.append({'id': block_id, 'reason': reason})
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("manifest")
    parser.add_argument("rebuild_report")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    manifest_path = Path(args.manifest).resolve()
    report_path = Path(args.rebuild_report).resolve()
    pipeline = load_pipeline(Path(__file__).with_name("pdf_translation_pipeline.py"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pipeline.enrich_manifest_layout(source, manifest)
    source_blocks = {
        block["id"]: block
        for page in manifest["pages"]
        for block in page["blocks"]
    }
    rebuild = json.loads(report_path.read_text(encoding="utf-8"))

    bold_mismatches = []
    mixed_weight_flows = []
    body_floor_violations = []
    header_footer_size_mismatches = []
    checked_draws = 0
    drawn_ids = set()

    for item in rebuild.get("blocks", []):
        block_ids = list(dict.fromkeys(BLOCK_ID_RE.findall(str(item.get("id", "")))))
        blocks = [source_blocks[block_id] for block_id in block_ids if block_id in source_blocks]
        if not blocks:
            continue
        if item.get('draws'):
            drawn_ids.update(block_ids)
            checked_draws += len(item['draws'])
        role = str(item.get("role", ""))
        is_cell = str(item.get("id", "")).startswith("cell:")
        expected_weights = {bool(block["style"].get("bold")) for block in blocks}
        if len(expected_weights) > 1 and not is_cell:
            mixed_weight_flows.append({"id": item["id"], "page": item["page"]})
            continue
        expected_bold = next(iter(expected_weights)) if len(expected_weights) == 1 else None
        source_size = max(float(block["style"].get("size", 9)) for block in blocks)
        for draw in item.get("draws", []):
            actual_bold = bool(draw.get("bold"))
            if expected_bold is not None and actual_bold != expected_bold:
                bold_mismatches.append(
                    {
                        "id": item["id"],
                        "page": item["page"],
                        "expected_bold": expected_bold,
                        "actual_bold": actual_bold,
                    }
                )
            actual_size = float(draw.get("font_size", 0))
            if role.startswith("body-") and not is_cell:
                floor = minimum_body_font_size({"size": source_size})
                if actual_size + 0.01 < floor:
                    body_floor_violations.append(
                        {
                            "id": item["id"],
                            "page": item["page"],
                            "font_size": actual_size,
                            "required_floor": floor,
                        }
                    )
            if role in {"running-header", "footer"} and actual_size + 0.5 < source_size:
                header_footer_size_mismatches.append(
                    {
                        "id": item["id"],
                        "page": item["page"],
                        "font_size": actual_size,
                        "source_size": source_size,
                    }
                )

    result = {
        "source": str(source),
        "rebuild_report": str(report_path),
        "checked_draws": checked_draws,
        "bold_mismatches": bold_mismatches,
        "mixed_weight_flows": mixed_weight_flows,
        "body_floor_violations": body_floor_violations,
        "header_footer_size_mismatches": header_footer_size_mismatches,
    }
    result["typography_matches_source"] = not any(
        result[key]
        for key in (
            "bold_mismatches",
            "mixed_weight_flows",
            "body_floor_violations",
            "header_footer_size_mismatches",
        )
    )
    # Source-relative metrics diagnose style differences, not actual legibility.
    # Missing glyphs, obscured content and unreadability remain visual blockers.
    result["warnings"] = {
        key: result[key] for key in (
            "bold_mismatches", "mixed_weight_flows", "body_floor_violations",
            "header_footer_size_mismatches",
        ) if result[key]
    }
    expected_ids = {key for key, block in source_blocks.items()
                    if str(block.get('source_text', '')).strip()}
    result['undrawn_source_ids'] = sorted(expected_ids - drawn_ids)
    result['status'] = 'checked' if checked_draws else 'unverified' if expected_ids else 'not_applicable'
    if not checked_draws:
        result['typography_matches_source'] = None
    result['bound_cell_failures'] = bound_cell_failures(source_blocks, rebuild, pipeline)
    result["passed"] = not result['undrawn_source_ids'] and not result['bound_cell_failures']
    Path(args.report).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
