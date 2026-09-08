from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import re
import sys
import math
import time
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfReader


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_pdftoppm() -> str:
    # The bundled .CMD shim cannot reliably forward non-ASCII Windows paths.
    # Prefer the real executable so Chinese source filenames remain intact.
    bundled = (
        Path(sys.executable).resolve().parent.parent
        / "native"
        / "poppler"
        / "Library"
        / "bin"
        / "pdftoppm.exe"
    )
    if bundled.exists():
        return str(bundled)
    discovered = shutil.which("pdftoppm")
    if discovered:
        return discovered
    raise RuntimeError("pdftoppm is unavailable")


def _normalize_box(points, scale: float) -> list[float]:
    xs = [float(point[0]) / scale for point in points]
    ys = [float(point[1]) / scale for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _normalize_quad(points, scale: float) -> list[list[float]]:
    return [[float(point[0]) / scale, float(point[1]) / scale] for point in points]


def rotation_from_quad(points) -> int:
    """Return the nearest cardinal reading direction from an OCR quadrilateral."""
    if not isinstance(points, (list, tuple)) or len(points) < 3:
        raise ValueError("OCR quadrilateral requires at least three points")
    edges = []
    for start, end in ((points[0], points[1]), (points[1], points[2])):
        dx = float(end[0]) - float(start[0])
        dy = float(end[1]) - float(start[1])
        edges.append((dx * dx + dy * dy, dx, dy))
    _, dx, dy = max(edges, key=lambda item: item[0])
    if abs(dx) + abs(dy) < 1e-9:
        raise ValueError("OCR quadrilateral has no readable baseline")
    angle = math.degrees(math.atan2(dy, dx)) % 360
    return int((round(angle / 90) * 90) % 360)


def _ocr_pass(engine, image: Image.Image, scale: float) -> list[dict]:
    working = image
    if scale != 1.0:
        working = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    result, _ = engine(np.asarray(working))
    records = []
    for item in result or []:
        points, text, score = item
        value = str(text).strip()
        if value:
            records.append(
                {
                    "box": _normalize_box(points, scale),
                    "quad": _normalize_quad(points, scale),
                    "rotation": rotation_from_quad(points),
                    "text": value,
                    "score": float(score),
                    "scale": scale,
                }
            )
    return records


def configure_page_detector(engine) -> None:
    detector = getattr(engine, "text_detector", None) or getattr(engine, "text_det", None)
    if detector is None:
        return
    preprocess = getattr(detector, "preprocess_op", None)
    if isinstance(preprocess, (list, tuple)) and preprocess:
        first = preprocess[0]
        if hasattr(first, "limit_side_len"):
            first.limit_side_len = 8000
            first.limit_type = "max"
            return
    if hasattr(detector, "limit_side_len"):
        detector.limit_side_len = 8000
        detector.limit_type = "max"


def _iou(first: list[float], second: list[float]) -> float:
    x0 = max(first[0], second[0])
    y0 = max(first[1], second[1])
    x1 = min(first[2], second[2])
    y1 = min(first[3], second[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    a = (first[2] - first[0]) * (first[3] - first[1])
    b = (second[2] - second[0]) * (second[3] - second[1])
    return intersection / max(a + b - intersection, 1e-9)


def _intersection_over_smaller(first: list[float], second: list[float]) -> float:
    x0 = max(first[0], second[0])
    y0 = max(first[1], second[1])
    x1 = min(first[2], second[2])
    y1 = min(first[3], second[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    a = (first[2] - first[0]) * (first[3] - first[1])
    b = (second[2] - second[0]) * (second[3] - second[1])
    return intersection / max(min(a, b), 1e-9)


def merge_ocr_records(records: list[dict]) -> list[dict]:
    chosen: list[dict] = []
    for record in sorted(records, key=lambda item: item["score"], reverse=True):
        duplicate = None
        contained_fragments = []
        for index, existing in enumerate(chosen):
            same_text = record["text"] == existing["text"]
            overlap = _iou(record["box"], existing["box"])
            record_text = " ".join(record["text"].casefold().split())
            existing_text = " ".join(existing["text"].casefold().split())
            contained_text = record_text in existing_text or existing_text in record_text
            contained_box = _intersection_over_smaller(record["box"], existing["box"]) >= 0.8
            same_rotation = record["rotation"] == existing["rotation"]
            record_width = record["box"][2] - record["box"][0]
            record_height = record["box"][3] - record["box"][1]
            existing_width = existing["box"][2] - existing["box"][0]
            existing_height = existing["box"][3] - existing["box"][1]
            area_ratio = max(record_width * record_height, existing_width * existing_height) / max(
                min(record_width * record_height, existing_width * existing_height), 1e-9
            )
            height_ratio = min(record_height, existing_height) / max(record_height, existing_height, 1e-9)
            cross_scale_fragment = (
                record["scale"] != existing["scale"] and area_ratio >= 1.8 and height_ratio >= 0.6
            )
            if contained_box and same_rotation and (contained_text or cross_scale_fragment):
                if len(record_text) > len(existing_text):
                    contained_fragments.append(index)
                    continue
                duplicate = index
                break
            if overlap >= 0.55 or (same_text and overlap >= 0.25):
                duplicate = index
                break
        if duplicate is None:
            for index in reversed(contained_fragments):
                chosen.pop(index)
            chosen.append(record)
    return sorted(chosen, key=lambda item: (item["box"][1], item["box"][0]))


def extract_selected_pages(
    source: str | Path,
    pages: list[int],
    output_dir: str | Path,
    dpi: int = 400,
    run_ocr: bool = True,
    expected_sha256: str | None = None,
    resume: bool = True,
) -> dict:
    started = time.perf_counter()
    source_path = Path(source).resolve()
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    actual_hash = sha256_file(source_path)
    if expected_sha256 and actual_hash.lower() != expected_sha256.lower():
        raise ValueError(
            f"source SHA-256 mismatch: expected {expected_sha256}, actual {actual_hash}"
        )

    reader = PdfReader(str(source_path))
    if any(page < 1 or page > len(reader.pages) for page in pages):
        raise ValueError(f"selected pages must be within 1..{len(reader.pages)}")

    render_dir = output_path / f"source-pages-{dpi}dpi"
    render_dir.mkdir(parents=True, exist_ok=True)
    pdftoppm = find_pdftoppm()
    page_records = []
    rendered_paths: dict[int, Path] = {}
    cache_path = output_path / "page-checkpoints"
    cache_path.mkdir(exist_ok=True)
    implementation = sha256_file(Path(__file__))
    try:
        ocr_version = version("rapidocr-onnxruntime")
    except PackageNotFoundError:
        ocr_version = "unavailable"
    engine = None
    source_lines = []
    for page_number in pages:
        page_started = time.perf_counter()
        key = {"source": actual_hash, "page": page_number, "dpi": dpi,
               "implementation": implementation, "ocr_version": ocr_version,
               "scales": [1.0, 3.0], "run_ocr": run_ocr}
        checkpoint = cache_path / f"page-{page_number:04d}.json"
        cached = None
        if resume and checkpoint.exists():
            try:
                candidate = json.loads(checkpoint.read_text(encoding="utf-8"))
                if candidate["key"] == key and sha256_file(Path(candidate["page"]["render_path"])) == candidate["page"]["render_sha256"]:
                    cached = candidate
            except (OSError, ValueError, KeyError):
                pass
        if cached:
            page_record = cached["page"]
            page_record["ocr_cache_hit"] = True
            page_records.append(page_record)
            source_lines.extend(cached["source_lines"])
            print(json.dumps({"stage": "ocr", "page": page_number, "cache_hit": True}), flush=True)
            continue
        page = reader.pages[page_number - 1]
        width_pt = float(page.mediabox.width)
        height_pt = float(page.mediabox.height)
        render_path = rendered_paths.get(page_number)
        if render_path is None:
            prefix = render_dir / f"source-page-{page_number:02d}"
            command = [
                pdftoppm, "-f", str(page_number), "-l", str(page_number),
                "-r", str(dpi), "-png", "-singlefile",
                str(source_path), str(prefix),
            ]
            subprocess.run(command, check=True, capture_output=True)
            render_path = prefix.with_suffix(".png")
        with Image.open(render_path) as image:
            pixel_width, pixel_height = image.size
        page_records.append(
            {
                "source_page": page_number,
                "width_pt": width_pt,
                "height_pt": height_pt,
                "rotation": int(page.get("/Rotate", 0) or 0),
                "media_box": [float(value) for value in page.mediabox],
                "crop_box": [float(value) for value in page.cropbox],
                "render_path": str(render_path),
                "render_sha256": sha256_file(render_path),
                "pixel_width": pixel_width,
                "pixel_height": pixel_height,
                "dpi": dpi,
            }
        )

        page_record = page_records[-1]
        lines = []
        if run_ocr:
            if engine is None:
                from rapidocr_onnxruntime import RapidOCR
                engine = RapidOCR()
                configure_page_detector(engine)
            with Image.open(page_record["render_path"]) as loaded:
                image = loaded.convert("RGB")
            raw = _ocr_pass(engine, image, 1.0) + _ocr_pass(engine, image, 3.0)
            merged = merge_ocr_records(raw)
            for index, record in enumerate(merged, 1):
                lines.append(
                    {
                        "id": f"p{page_record['source_page']:02d}-l{index:03d}",
                        "page": page_record["source_page"],
                        **record,
                    }
                )
            image.close()
        source_lines.extend(lines)
        page_record["ocr_cache_hit"] = False
        page_record["elapsed_seconds"] = round(time.perf_counter() - page_started, 3)
        temporary = checkpoint.with_suffix(".tmp.json")
        temporary.write_text(json.dumps({"key": key, "page": page_record, "source_lines": lines}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(checkpoint)
        print(json.dumps({"stage": "ocr", "page": page_number, "seconds": page_record["elapsed_seconds"], "lines": len(lines), "cache_hit": False}), flush=True)

    report = {
        "source": str(source_path),
        "source_sha256": actual_hash,
        "source_page_count": len(reader.pages),
        "selected_pages": pages,
        "pages": page_records,
        "source_lines": source_lines,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    (output_path / "extraction-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--pages", default="all", help="all or comma-separated 1-based pages")
    parser.add_argument("--output", required=True)
    parser.add_argument("--dpi", type=int, default=400)
    parser.add_argument("--no-resume", action="store_true", help="Ignore page checkpoints")
    args = parser.parse_args()
    reader = PdfReader(str(Path(args.source).resolve()))
    pages = (
        list(range(1, len(reader.pages) + 1))
        if args.pages.strip().lower() == "all"
        else [int(value) for value in args.pages.split(",") if value.strip()]
    )
    report = extract_selected_pages(args.source, pages, args.output, dpi=args.dpi, resume=not args.no_resume)
    print(
        json.dumps(
            {
                "pages": len(report["pages"]),
                "ocr_lines": len(report["source_lines"]),
                "output": str(Path(args.output).resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
