#!/usr/bin/env python3
"""Choose automatic translation behavior from a reviewed drawing inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


COUNT_FIELDS = (
    "clear_chinese_label_count",
    "clear_foreign_label_count",
    "matched_bilingual_pair_count",
    "unmatched_chinese_label_count",
    "unmatched_foreign_label_count",
)


def language_pair(value: object) -> frozenset[str]:
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(v, str) for v in value):
        return frozenset()
    pair = frozenset(v.strip().replace('_', '-').casefold() for v in value)
    return pair if len(pair) == 2 and '' not in pair else frozenset()


def decide(inventory: dict[str, object], route_report: dict | None = None) -> dict[str, object]:
    context = route_report if route_report is not None else inventory
    if context.get("error"):
        raise ValueError("resolve the PDF routing error before checking language coverage")
    kind = context.get("document_kind")
    if kind not in ("document", "engineering-drawing"):
        raise ValueError("document_kind is missing or invalid; supply the saved --route-report")
    mode = context.get("translation_mode")
    if mode is None and route_report is None:
        mode = "add_bilingual" if kind == "engineering-drawing" else "replace"
    if mode not in ("replace", "add_bilingual"):
        raise ValueError("translation_mode must come from a successful router result")
    if mode == "replace":
        return {
            "status": "translation_required",
            "action": "replace",
            "preserve_source_pdf": False,
            "user_input_required": False,
        }
    counts = {field: int(inventory.get(field, 0)) for field in COUNT_FIELDS}
    if any(value < 0 for value in counts.values()):
        raise ValueError("drawing language-inventory counts must be non-negative")
    chinese = counts["clear_chinese_label_count"]
    foreign = counts["clear_foreign_label_count"]
    matched = counts["matched_bilingual_pair_count"]
    present_pair = language_pair(inventory.get('language_pair'))
    requested_pair = language_pair(context.get('requested_language_pair',
                                              inventory.get('requested_language_pair')))
    complete = (
        kind == "engineering-drawing"
        and bool(present_pair)
        and present_pair == requested_pair
        and all(field in inventory for field in COUNT_FIELDS)
        and chinese > 0
        and foreign > 0
        and matched == chinese == foreign
        and counts["unmatched_chinese_label_count"] == 0
        and counts["unmatched_foreign_label_count"] == 0
    )
    if complete:
        return {
            "status": "already_bilingual_complete",
            "action": "skip_translation",
            "preserve_source_pdf": True,
            "user_input_required": False,
        }
    return {
        "status": "translation_required",
        "action": "add_bilingual",
        "preserve_source_pdf": True,
        "user_input_required": False,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--inventory-json")
    source.add_argument("--inventory-file", type=Path)
    parser.add_argument("--route-report", type=Path,
                        help="saved router JSON; authoritative output mode and document kind")
    args = parser.parse_args()
    try:
        raw = (
            args.inventory_file.read_text(encoding="utf-8")
            if args.inventory_file
            else args.inventory_json
        )
        inventory = json.loads(raw)
        route_report = json.loads(args.route_report.read_text(encoding="utf-8-sig")) if args.route_report else None
        result = decide(inventory, route_report)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
