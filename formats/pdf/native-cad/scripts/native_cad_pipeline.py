#!/usr/bin/env python3
"""Source-bound coordinate replacement pipeline for native CAD PDFs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
from typing import Any

import pymupdf


SOURCE_NAME = "SOURCE.pdf"
INVENTORY_NAME = "source-inventory.json"
PACKET_NAME = "translation-packet.json"
OUTPUT_NAME = "translated-native-cad.pdf"
APPLY_REPORT_NAME = "apply-report.json"
FINAL_QA_NAME = "final-qa.json"
DEFAULT_FONT = Path(r"C:\Windows\Fonts\simhei.ttf")
PROTECTED_PATTERNS = (
    re.compile(r"^[ØRrMm]?\s*[+\-±]?\d[\d.,/×x°'\s-]*(?:mm|cm|kg|kW|W|V|A)?$", re.I),
    re.compile(r"^(?:ISO|DIN|EN|GB)\s*[-:]?\s*[A-Z0-9./-]+$", re.I),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_protected(text: str) -> bool:
    value = " ".join(text.split())
    if not value:
        return True
    return any(pattern.fullmatch(value) for pattern in PROTECTED_PATTERNS)


def cardinal_rotation(direction: tuple[float, float]) -> int:
    angle = round(math.degrees(math.atan2(-direction[1], direction[0]))) % 360
    return min((0, 90, 180, 270), key=lambda value: abs((angle - value + 180) % 360 - 180))


def page_snapshot(page: pymupdf.Page) -> dict[str, object]:
    return {
        "width": round(page.rect.width, 4),
        "height": round(page.rect.height, 4),
        "rotation": int(page.rotation),
        "image_count": len(page.get_images(full=True)),
        "vector_count": len(page.get_drawings()),
    }


def extract_records(document: pymupdf.Document) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for page_index, page in enumerate(document):
        span_index = 0
        blocks = page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                direction = tuple(line.get("dir", (1.0, 0.0)))
                rotation = cardinal_rotation(direction)
                for span in line.get("spans", []):
                    text = " ".join(str(span.get("text", "")).split())
                    if not text:
                        continue
                    span_index += 1
                    protected = is_protected(text)
                    records.append(
                        {
                            "id": f"p{page_index + 1:04d}-s{span_index:05d}",
                            "page": page_index,
                            "source": text,
                            "bbox": [round(float(value), 4) for value in span["bbox"]],
                            "font_size": round(float(span.get("size", 8.0)), 3),
                            "color": int(span.get("color", 0)),
                            "rotation": rotation,
                            "status": "protected" if protected else "pending",
                        }
                    )
    return records


def prepare(source: Path, job_dir: Path) -> int:
    if not source.is_file():
        print("source file not found", file=sys.stderr)
        return 2
    job_dir.mkdir(parents=True, exist_ok=True)
    bound_source = job_dir / SOURCE_NAME
    shutil.copyfile(source, bound_source)
    try:
        document = pymupdf.open(bound_source)
    except Exception as exc:
        print(f"cannot open source PDF: {exc}", file=sys.stderr)
        return 2
    if document.needs_pass or document.page_count == 0:
        document.close()
        print("source PDF is encrypted or contains no pages", file=sys.stderr)
        return 2
    inventory = {
        "schema_version": 1,
        "source_sha256": sha256(bound_source),
        "page_count": document.page_count,
        "pages": [page_snapshot(page) for page in document],
        "records": extract_records(document),
    }
    document.close()
    packet = {
        "schema_version": 1,
        "source_sha256": inventory["source_sha256"],
        "records": [
            {
                "id": record["id"],
                "source": record["source"],
                "translation": "",
                "status": "pending",
            }
            for record in inventory["records"]
            if record["status"] == "pending"
        ],
    }
    write_json(job_dir / INVENTORY_NAME, inventory)
    write_json(job_dir / PACKET_NAME, packet)
    print(json.dumps({"stage": "prepared", "job_dir": str(job_dir)}, ensure_ascii=False))
    return 0


def validate_packet(
    inventory: dict[str, object], packet: dict[str, object]
) -> tuple[dict[str, dict[str, object]], list[str]]:
    expected = {
        str(record["id"]): record
        for record in inventory["records"]
        if record["status"] == "pending"
    }
    supplied = {str(record.get("id")): record for record in packet.get("records", [])}
    incomplete: list[str] = []
    for record_id, source_record in expected.items():
        translated = supplied.get(record_id)
        if (
            translated is None
            or translated.get("source") != source_record["source"]
            or translated.get("status") != "translated"
            or not str(translated.get("translation", "")).strip()
        ):
            incomplete.append(record_id)
    return supplied, incomplete


def rgb_from_int(value: int) -> tuple[float, float, float]:
    return (
        ((value >> 16) & 255) / 255,
        ((value >> 8) & 255) / 255,
        (value & 255) / 255,
    )


def insert_fitted_text(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    text: str,
    source_size: float,
    color: tuple[float, float, float],
    rotation: int,
    font_file: Path,
) -> float | None:
    size = max(source_size, 4.0)
    while size >= 4.0:
        spare = page.insert_textbox(
            rect,
            text,
            fontname="nativecad-cjk",
            fontfile=str(font_file),
            fontsize=size,
            color=color,
            rotate=rotation,
            overlay=True,
        )
        if spare >= 0:
            return round(size, 3)
        size = round(size - 0.5, 3)
    return None


def apply(job_dir: Path, packet_path: Path, font_file: Path) -> int:
    inventory_path = job_dir / INVENTORY_NAME
    bound_source = job_dir / SOURCE_NAME
    report_path = job_dir / APPLY_REPORT_NAME
    if not inventory_path.is_file() or not bound_source.is_file() or not packet_path.is_file():
        write_json(report_path, {"passed": False, "error": "missing prepared job or packet"})
        return 2
    inventory = read_json(inventory_path)
    packet = read_json(packet_path)
    failures: list[str] = []
    if sha256(bound_source) != inventory.get("source_sha256"):
        failures.append("source_hash_mismatch")
    if packet.get("source_sha256") != inventory.get("source_sha256"):
        failures.append("packet_source_hash_mismatch")
    supplied, incomplete = validate_packet(inventory, packet)
    if incomplete:
        failures.append("incomplete_translations")
    if not font_file.is_file():
        failures.append("font_file_not_found")
    if failures:
        write_json(
            report_path,
            {
                "passed": False,
                "failures": failures,
                "incomplete_records": incomplete,
                "fit_failures": [],
            },
        )
        return 2

    document = pymupdf.open(bound_source)
    pending = [record for record in inventory["records"] if record["status"] == "pending"]
    by_page: dict[int, list[dict[str, object]]] = {}
    for record in pending:
        by_page.setdefault(int(record["page"]), []).append(record)
    for page_index, records in by_page.items():
        page = document[page_index]
        for record in records:
            page.add_redact_annot(pymupdf.Rect(record["bbox"]), fill=None, cross_out=False)
        page.apply_redactions(images=0, graphics=0, text=0)

    fit_failures: list[str] = []
    applied_records: list[dict[str, object]] = []
    for record in pending:
        translated = supplied[str(record["id"])]
        page = document[int(record["page"])]
        fitted_size = insert_fitted_text(
            page,
            pymupdf.Rect(record["bbox"]),
            str(translated["translation"]).strip(),
            float(record["font_size"]),
            rgb_from_int(int(record["color"])),
            int(record["rotation"]),
            font_file,
        )
        if fitted_size is None:
            fit_failures.append(str(record["id"]))
        else:
            applied_records.append({"id": record["id"], "font_size": fitted_size})

    output = job_dir / OUTPUT_NAME
    if fit_failures:
        document.close()
        write_json(
            report_path,
            {
                "passed": False,
                "failures": ["text_fit_failure"],
                "incomplete_records": [],
                "fit_failures": fit_failures,
                "applied_records": applied_records,
            },
        )
        return 2
    document.save(output, garbage=4, deflate=True)
    document.close()
    write_json(
        report_path,
        {
            "passed": True,
            "source_sha256": inventory["source_sha256"],
            "candidate_sha256": sha256(output),
            "failures": [],
            "incomplete_records": [],
            "fit_failures": [],
            "applied_records": applied_records,
        },
    )
    print(json.dumps({"stage": "applied", "output": str(output)}, ensure_ascii=False))
    return 0


def same_page_structure(expected: dict[str, object], actual: dict[str, object]) -> bool:
    stable_fields_match = all(
        expected[key] == actual[key]
        for key in ("width", "height", "rotation", "image_count")
    )
    return stable_fields_match and int(actual["vector_count"]) >= int(expected["vector_count"])


def verify(
    job_dir: Path, candidate: Path, visual_review_path: Path | None
) -> int:
    inventory_path = job_dir / INVENTORY_NAME
    apply_report_path = job_dir / APPLY_REPORT_NAME
    failures: list[str] = []
    if not inventory_path.is_file() or not apply_report_path.is_file() or not candidate.is_file():
        failures.append("missing_job_evidence")
        write_json(job_dir / FINAL_QA_NAME, {"passed": False, "failures": failures})
        return 2
    inventory = read_json(inventory_path)
    apply_report = read_json(apply_report_path)
    bound_source = job_dir / SOURCE_NAME
    if sha256(bound_source) != inventory.get("source_sha256"):
        failures.append("source_hash_mismatch")
    candidate_hash = sha256(candidate)
    if not apply_report.get("passed") or apply_report.get("candidate_sha256") != candidate_hash:
        failures.append("candidate_not_bound_to_apply_report")
    try:
        document = pymupdf.open(candidate)
        if document.page_count != inventory.get("page_count"):
            failures.append("page_count_mismatch")
        elif any(
            not same_page_structure(expected, page_snapshot(document[index]))
            for index, expected in enumerate(inventory["pages"])
        ):
            failures.append("page_structure_mismatch")
        preview_dir = job_dir / "review"
        preview_dir.mkdir(exist_ok=True)
        for index, page in enumerate(document):
            page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(
                preview_dir / f"page-{index + 1:04d}.png"
            )
        document.close()
    except Exception as exc:
        failures.append(f"candidate_read_error:{exc}")

    if visual_review_path is None or not visual_review_path.is_file():
        failures.append("visual_review_required")
    else:
        review = read_json(visual_review_path)
        if review.get("candidate_sha256") != candidate_hash:
            failures.append("visual_review_hash_mismatch")
        if not review.get("all_pages_reviewed"):
            failures.append("not_all_pages_reviewed")
        if not review.get("all_changed_regions_reviewed"):
            failures.append("not_all_changed_regions_reviewed")
        for key in (
            "visible_foreign_descriptive_text",
            "text_overlap_failures",
            "line_or_graphic_damage",
        ):
            if review.get(key) != []:
                failures.append(key)

    qa = {
        "passed": not failures,
        "source_sha256": inventory.get("source_sha256"),
        "candidate_sha256": candidate_hash,
        "failures": failures,
    }
    write_json(job_dir / FINAL_QA_NAME, qa)
    print(json.dumps(qa, ensure_ascii=False))
    return 0 if not failures else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("source", type=Path)
    prepare_parser.add_argument("--job-dir", required=True, type=Path)
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("job_dir", type=Path)
    apply_parser.add_argument("--packet", required=True, type=Path)
    apply_parser.add_argument("--font-file", type=Path, default=DEFAULT_FONT)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("job_dir", type=Path)
    verify_parser.add_argument("--candidate", required=True, type=Path)
    verify_parser.add_argument("--visual-review", type=Path)
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    if args.command == "prepare":
        return prepare(args.source, args.job_dir)
    if args.command == "apply":
        return apply(args.job_dir, args.packet, args.font_file)
    return verify(args.job_dir, args.candidate, args.visual_review)


if __name__ == "__main__":
    raise SystemExit(main())
