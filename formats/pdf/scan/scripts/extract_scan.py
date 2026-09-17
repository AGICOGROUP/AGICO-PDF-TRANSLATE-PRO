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


def recognize_with_angle_guard(engine, crops, allow_retry: bool = True):
    """Retry only rejected classifier-flipped crops in their original direction."""
    angles = [0] * len(crops)
    classified = crops
    if engine.use_angle_cls:
        classified, decisions, _ = engine.text_cls(crops)
        threshold = getattr(engine.text_cls, 'cls_thresh', .9)
        angles = [180 if str(label) == '180' and float(score) > threshold else 0
                  for label, score in decisions]
    readings, _ = engine.text_recognizer(classified)
    readings = list(readings)
    attempts = [1] * len(crops)
    retry = [i for i, ((text, score), angle) in enumerate(zip(readings, angles))
             if allow_retry and angle == 180 and (not str(text).strip() or float(score) < engine.text_score)]
    if retry:
        alternatives, _ = engine.text_recognizer([crops[i] for i in retry])
        for i, alternative in zip(retry, alternatives):
            attempts[i] = 2
            if str(alternative[0]).strip() and float(alternative[1]) > float(readings[i][1]):
                readings[i] = alternative
                angles[i] = 0
    return readings, angles, attempts


def uncovered_text_candidates(image: Image.Image, covered_boxes: list) -> list[list[float]]:
    """Cheap ink-only audit, not OCR or proof of readable text. Never edits pixels."""
    import cv2
    factor = min(1.0, 1600 / max(image.size))
    small = image.convert('L').resize((round(image.width * factor), round(image.height * factor)))
    ink = (np.asarray(small) < 160).astype(np.uint8)
    for x0, y0, x1, y1 in covered_boxes:
        ink[max(0, int(y0 * factor) - 2):min(ink.shape[0], int(y1 * factor) + 3),
            max(0, int(x0 * factor) - 2):min(ink.shape[1], int(x1 * factor) + 3)] = 0
    _, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = [i for i, (x, y, w, h, area) in enumerate(stats)
            if i and 2 <= w <= 60 and 4 <= h <= 40 and area >= 5 and w / h <= 6]
    if not keep:
        return []
    heights = [stats[i][3] for i in keep]
    chars = np.isin(labels, keep).astype(np.uint8)
    # Justified prose can have several glyph-heights between short words.
    # Joining only tight words drops the entire row at the character-count gate.
    boxes = []
    # Retain tight groups too: a wide join can touch a logo/rule and fail the
    # line-height filter. These are two cheap morphology passes, not OCR retries.
    for spacing in (1.5, 4):
        joined = cv2.dilate(chars, np.ones((3, max(9, int(np.median(heights) * spacing))), np.uint8))
        _, _, regions, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
        for x, y, w, h, area in regions[1:]:
            if w < max(100, h * 5) or h > 60:
                continue
            count = sum(x <= stats[i][0] < x+w and y <= stats[i][1] < y+h for i in keep)
            box = [round(float(v) / factor, 1) for v in (x, y, x+w, y+h)]
            if count >= 10 and not any(candidate_is_covered(box, old) for old in boxes):
                boxes = [old for old in boxes if not candidate_is_covered(old, box)]
                boxes.append(box)
    return sorted(boxes, key=lambda box: (box[1], box[0]))


def _ocr_pass(engine, image: Image.Image, scale: float) -> list[dict]:
    working = image
    if scale != 1.0:
        working = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    guarded = all(hasattr(engine, attr) for attr in
                  ('load_img', 'text_detector', 'get_crop_img_list', 'text_recognizer',
                   'text_score', 'sorted_boxes', 'use_angle_cls'))
    if guarded:
        pixels = engine.load_img(np.asarray(working))
        h, w = pixels.shape[:2]
        ratio = getattr(engine, 'width_height_ratio', -1)
        without_detector = (not getattr(engine, 'use_text_det', True)
                            or h <= getattr(engine, 'min_height', 0)
                            or (ratio != -1 and w / h > ratio))
        if without_detector:
            boxes, crops = engine.get_boxes_img_without_det(pixels, h, w)
        else:
            boxes, _ = engine.text_detector(pixels)
            if boxes is None or not len(boxes):
                return []
            boxes = engine.sorted_boxes(boxes)
            crops = engine.get_crop_img_list(pixels, boxes)
        readings, angles, attempts = recognize_with_angle_guard(
            engine, crops, allow_retry=getattr(engine, '_angle_retry_allowed', True))
        result = [(box.tolist(), text, score) for box, (text, score) in zip(boxes, readings)]
    else:
        result, _ = engine(np.asarray(working))
        angles = [0] * len(result or [])
        attempts = [1] * len(result or [])
    records = []
    for item, angle, attempt in zip(result or [], angles, attempts):
        points, text, score = item
        value = str(text).strip()
        if value or guarded:
            if angle == 180:
                points = list(points[2:]) + list(points[:2])
            records.append(
                {
                    "box": _normalize_box(points, scale),
                    "quad": _normalize_quad(points, scale),
                    "rotation": rotation_from_quad(points),
                    "text": value,
                    "score": float(score),
                    "scale": scale,
                    "ocr_attempts": attempt,
                    **({'review_required': True} if guarded and
                       (not value or float(score) < engine.text_score) else {}),
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


def candidate_is_covered(candidate_box, accepted_box) -> bool:
    """A recognized fragment must not hide a larger rejected source line."""
    x0, y0 = max(candidate_box[0], accepted_box[0]), max(candidate_box[1], accepted_box[1])
    x1, y1 = min(candidate_box[2], accepted_box[2]), min(candidate_box[3], accepted_box[3])
    area = (candidate_box[2] - candidate_box[0]) * (candidate_box[3] - candidate_box[1])
    return max(0, x1-x0) * max(0, y1-y0) / max(area, 1e-9) >= .8


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
    ocr_scales: tuple[float, ...] = (1.0,),
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
               "scales": list(ocr_scales), "run_ocr": run_ocr}
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
                if hasattr(engine, 'text_recognizer'):
                    # An explicit two-scale extraction already spends both attempts.
                    engine._angle_retry_allowed = len(ocr_scales) == 1
            with Image.open(page_record["render_path"]) as loaded:
                image = loaded.convert("RGB")
            raw = [record for scale in ocr_scales for record in _ocr_pass(engine, image, scale)]
            merged = merge_ocr_records([record for record in raw if not record.get('review_required')])
            candidates = [dict(record, reason='recognition_rejected') for record in raw
                          if record.get('review_required') and not any(
                              candidate_is_covered(record['box'], good['box']) for good in merged)]
            if len(ocr_scales) > 1:
                for candidate in candidates:
                    candidate['ocr_attempts'] = len(ocr_scales)
            candidates.extend({'box': box, 'reason': 'uncovered_ink', 'ocr_attempts': len(ocr_scales)}
                              for box in uncovered_text_candidates(image, [record['box'] for record in raw]))
            page_record['ocr_review_candidates'] = [dict(candidate, id=f'p{page_number:02d}-c{i:03d}')
                                                    for i, candidate in enumerate(candidates, 1)]
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
    parser.add_argument("--dual-scale", action="store_true", help="Retry selected uncertain pages at 1x and 3x")
    args = parser.parse_args()
    reader = PdfReader(str(Path(args.source).resolve()))
    pages = (
        list(range(1, len(reader.pages) + 1))
        if args.pages.strip().lower() == "all"
        else [int(value) for value in args.pages.split(",") if value.strip()]
    )
    report = extract_selected_pages(args.source, pages, args.output, dpi=args.dpi, resume=not args.no_resume,
                                    ocr_scales=(1.0, 3.0) if args.dual_scale else (1.0,))
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
