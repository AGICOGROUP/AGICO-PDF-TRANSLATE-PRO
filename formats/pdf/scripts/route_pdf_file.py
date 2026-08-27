#!/usr/bin/env python3
"""Classify a PDF and select exactly one independent PDF translation skill."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from pypdf import PdfReader
from pypdf.errors import PdfReadError


PDF_SIGNATURE = b"%PDF-"
NATIVE_ADAPTER = "formats/pdf/native/SKILL.md"
SCAN_ADAPTER = "formats/pdf/scan/SKILL.md"
BILINGUAL_ADAPTER = "formats/pdf/bilingual/SKILL.md"


def report(
    *,
    pdf_type: str | None = None,
    adapter: str | None = None,
    page_count: int = 0,
    native_text_pages: int = 0,
    native_char_counts: list[int] | None = None,
    rotated_pages: list[int] | None = None,
    encrypted: bool = False,
    extension_mismatch: bool = False,
    document_kind: str | None = None,
    translation_mode: str | None = None,
    next_action: str | None = None,
    drawing_evidence: list[str] | None = None,
    error: str | None = None,
) -> dict[str, object]:
    return {
        "format": "pdf" if pdf_type or adapter else None,
        "pdf_type": pdf_type,
        "adapter": adapter,
        "page_count": page_count,
        "native_text_pages": native_text_pages,
        "native_char_counts": native_char_counts or [],
        "rotated_pages": rotated_pages or [],
        "encrypted": encrypted,
        "extension_mismatch": extension_mismatch,
        "document_kind": document_kind,
        "translation_mode": translation_mode,
        "next_action": next_action,
        "drawing_evidence": drawing_evidence or [],
        "error": error,
    }


def classify_document_kind(
    page_sizes: list[tuple[float, float]], native_char_counts: list[int]
) -> tuple[str, list[str]]:
    """Return a fail-safe drawing classification from strong sheet evidence."""
    large_landscape_pages = [
        index
        for index, (width, height) in enumerate(page_sizes, start=1)
        if width > height and width >= 1000 and width * height >= 1_000_000
    ]
    low_prose_density = max(native_char_counts or [0]) <= 3000
    if large_landscape_pages and low_prose_density:
        return "engineering-drawing", [
            "large_landscape_sheet",
            "low_prose_density",
        ]
    image_internal_rotation_candidates = [
        index
        for index, (width, height) in enumerate(page_sizes, start=1)
        if max(width, height) / max(min(width, height), 1) >= 1.9
        and width * height >= 1_400_000
    ]
    if image_internal_rotation_candidates and low_prose_density:
        return "engineering-drawing", [
            "large_extreme_aspect_sheet",
            "image_internal_rotation_candidate",
            "low_prose_density",
        ]
    return "document", []


def route(source: Path) -> tuple[int, dict[str, object]]:
    if not source.is_file():
        return 2, report(error="source file not found")

    try:
        with source.open("rb") as stream:
            signature = stream.read(len(PDF_SIGNATURE))
    except OSError as exc:
        return 2, report(error=f"cannot inspect source: {exc}")

    if signature != PDF_SIGNATURE:
        return 2, report(error="file does not have a valid PDF signature")
    if source.suffix.lower() != ".pdf":
        return 2, report(
            extension_mismatch=True,
            error=f"file extension {source.suffix or '<none>'} does not match detected pdf container",
        )

    try:
        reader = PdfReader(source, strict=False)
        if reader.is_encrypted:
            return 2, report(encrypted=True, error="encrypted PDF requires decryption before routing")

        counts: list[int] = []
        rotated: list[int] = []
        page_sizes: list[tuple[float, float]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            counts.append(len("".join(text.split())))
            page_sizes.append((float(page.mediabox.width), float(page.mediabox.height)))
            if int(page.rotation or 0) % 360:
                rotated.append(page_number)
    except (OSError, PdfReadError, ValueError, TypeError) as exc:
        return 2, report(error=f"cannot read PDF: {exc}")

    page_count = len(counts)
    if page_count == 0:
        return 2, report(error="PDF contains no pages")
    native_text_pages = sum(count > 0 for count in counts)
    document_kind, drawing_evidence = classify_document_kind(page_sizes, counts)
    drawing = document_kind == "engineering-drawing"
    if native_text_pages == 0:
        if rotated:
            return 2, report(
                pdf_type="scan-only",
                page_count=page_count,
                native_char_counts=counts,
                rotated_pages=rotated,
                document_kind=document_kind,
                translation_mode="add_bilingual" if drawing else "replace",
                next_action="inspect_bilingual_coverage" if drawing else "translate",
                drawing_evidence=drawing_evidence,
                error="normalize rotated scan pages before translation routing",
            )
        return 0, report(
            pdf_type="scan-only",
            adapter=SCAN_ADAPTER,
            page_count=page_count,
            native_char_counts=counts,
            document_kind=document_kind,
            translation_mode="add_bilingual" if drawing else "replace",
            next_action="inspect_bilingual_coverage" if drawing else "translate",
            drawing_evidence=drawing_evidence,
        )

    pdf_type = "native-text" if native_text_pages == page_count else "mixed"
    return 0, report(
        pdf_type=pdf_type,
        adapter=BILINGUAL_ADAPTER if drawing else NATIVE_ADAPTER,
        page_count=page_count,
        native_text_pages=native_text_pages,
        native_char_counts=counts,
        rotated_pages=rotated,
        document_kind=document_kind,
        translation_mode="add_bilingual" if drawing else "replace",
        next_action="inspect_bilingual_coverage" if drawing else "translate",
        drawing_evidence=drawing_evidence,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    exit_code, result = route(args.source)
    print(json.dumps(result, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
