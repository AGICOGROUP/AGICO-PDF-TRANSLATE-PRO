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


def decide(inventory: dict[str, object]) -> dict[str, object]:
    if inventory.get("document_kind") != "engineering-drawing":
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
    complete = (
        chinese > 0
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
    args = parser.parse_args()
    try:
        raw = (
            args.inventory_file.read_text(encoding="utf-8")
            if args.inventory_file
            else args.inventory_json
        )
        inventory = json.loads(raw)
        result = decide(inventory)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
