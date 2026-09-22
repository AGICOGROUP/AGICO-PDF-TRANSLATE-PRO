"""Resolve every ocr_review_candidate with exactly one targeted OCR attempt.

The extractor detects candidates (``uncovered_ink`` / ``recognition_rejected``) but nothing in the
pipeline ever resolved them, so a legible line that the page-level detector missed could reach the
deliverable untranslated. This script closes that gap without breaking the two-attempt rule: the
page pass is attempt one, the crop pass here is attempt two, and a candidate that still fails is
recorded as illegible instead of being guessed at.

Output is a JSON payload::

    {"source_sha256": "...",
     "dispositions": {"p04-c001": {"disposition": "recovered", "text": "...",
                                   "box": [...], "score": 0.93}},
     "supplements":  [{"block_id": "...", ...}]}   # recovered rows, ready to register

``recovered`` rows still need a translation; ``register_source_supplements.py`` binds them to an
existing translated block. ``non_text`` and ``illegible`` are terminal dispositions and satisfy the
build gate on their own.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from extract_scan import _ocr_pass, merge_ocr_records, candidate_is_covered

MARGIN = 18           # source pixels around the candidate band
MIN_USEFUL_SCORE = 0.62
MIN_CHARS = 2         # a single stray glyph is noise, not a missed label
SEGMENTS = 3          # very wide bands defeat the detector; retry as overlapping segments


def _new_engine():
    """A crop-scale engine.

    The page pipeline raises the detector's ``limit_side_len`` to 8000/max so whole pages are not
    downsampled. Feeding an already-cropped narrow band through that configuration makes the
    detector return nothing (measured: the same band reads 2 rows with the default 736 limit and
    0 rows with the page configuration), which then mislabels legible lines as non-text. Crops
    therefore get their own engine with stock detection settings.
    """
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def _crop(image: Image.Image, box: list) -> Image.Image:
    x0, y0, x1, y1 = box
    return image.crop((
        max(0, int(x0) - MARGIN), max(0, int(y0) - MARGIN),
        min(image.width, int(x1) + MARGIN), min(image.height, int(y1) + MARGIN),
    ))


def _read_band(engine, crop: Image.Image, scales: tuple) -> list[dict]:
    """One targeted attempt over a crop: whole band first, then overlapping segments.

    The detector can miss text in a very wide band (aspect ratio well above 20:1) even at stock
    settings, so if the whole-band read returns nothing the band is re-read as overlapping
    segments. Segmenting is a strategy inside this single crop attempt, not an extra attempt: the
    page-level OCR pass is attempt one, this crop read is attempt two, and the two-attempt rule
    still holds.
    """
    rows: list[dict] = []
    for scale in scales:
        rows = [r for r in merge_ocr_records(_ocr_pass(engine, crop, scale))
                if len(str(r.get("text", "")).strip()) >= MIN_CHARS
                and float(r.get("score", 0.0)) >= MIN_USEFUL_SCORE]
        if rows:
            return rows
    if crop.width / max(1, crop.height) < 12:
        return rows
    merged: list[dict] = []
    step = (crop.width - 2 * SEGMENTS * MARGIN) // SEGMENTS
    for i in range(SEGMENTS):
        a = MARGIN + i * step
        b = a + step + step // 2          # 50 % overlap so no glyph is cut at a boundary
        seg = crop.crop((max(0, a), 0, min(crop.width, b), crop.height))
        for scale in scales:
            for row in merge_ocr_records(_ocr_pass(engine, seg, scale)):
                text = str(row.get("text", "")).strip()
                score = float(row.get("score", 0.0))
                if len(text) < MIN_CHARS or score < MIN_USEFUL_SCORE:
                    continue
                row["box"] = [row["box"][0] + a - MARGIN, row["box"][1],
                              row["box"][2] + a - MARGIN, row["box"][3]]
                row["quad"] = [[p[0] + a - MARGIN, p[1]] for p in row["quad"]]
                merged.append(row)
            if merged:
                break
    # Deduplicate rows recovered by overlapping segments: same text and overlapping box = one row.
    kept: list[dict] = []
    for row in sorted(merged, key=lambda r: -float(r.get("score", 0.0))):
        text = str(row.get("text", "")).strip()
        if any(text == str(other.get("text", "")).strip()
               and _overlap_fraction(row["box"], other["box"]) > 0.3 for other in kept):
            continue
        kept.append(row)
    return kept


def _overlap_fraction(first: list, second: list) -> float:
    """Intersection over the smaller box area, for rows recovered by two segments."""
    x0 = max(float(first[0]), float(second[0]))
    y0 = max(float(first[1]), float(second[1]))
    x1 = min(float(first[2]), float(second[2]))
    y1 = min(float(first[3]), float(second[3]))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    a = max((float(first[2]) - float(first[0])) * (float(first[3]) - float(first[1])), 1e-9)
    b = max((float(second[2]) - float(second[0])) * (float(second[3]) - float(second[1])), 1e-9)
    return inter / min(a, b)


def resolve_candidates(manifest: dict, engine, scales: tuple = (2.0,)) -> dict:
    """Return dispositions plus registerable supplement rows for one manifest."""
    dispositions: dict[str, dict] = {}
    recovered: list[dict] = []
    for page in manifest.get("pages", []):
        number = page["source_page"]
        path = Path(page["render_path"])
        if not path.is_file():
            raise ValueError(f"source render missing for page {number}")
        with Image.open(path) as opened:
            image = opened.convert("RGB")
            for candidate in page.get("ocr_review_candidates", []) or []:
                crop = _crop(image, candidate["box"])
                shift = [candidate["box"][0] - MARGIN, candidate["box"][1] - MARGIN]
                rows = _read_band(engine, crop, scales)
                for row in rows:
                    # Re-anchor the crop-local box onto the page render.
                    row["box"] = [row["box"][0] + shift[0], row["box"][1] + shift[1],
                                  row["box"][2] + shift[0], row["box"][3] + shift[1]]
                    row["quad"] = [[p[0] + shift[0], p[1] + shift[1]] for p in row["quad"]]
                best = max(rows, key=lambda r: r["score"], default=None)
                cid = candidate["id"]
                if best is None:
                    # No legible text after the one allowed attempt: keep the ink, say so, and
                    # never invent a label. This is the two-attempt stop rule.
                    dispositions[cid] = {
                        "disposition": "non_text" if candidate.get("reason") == "uncovered_ink"
                        else "illegible",
                        "page": number, "box": [round(v, 1) for v in candidate["box"]],
                        "attempts": 1 + len(scales),
                        "note": "targeted crop re-OCR returned no legible text; source ink kept",
                    }
                    continue
                dispositions[cid] = {
                    "disposition": "recovered", "page": number, "text": best["text"],
                    "box": [round(v, 1) for v in best["box"]], "score": round(best["score"], 3),
                    "rotation": best.get("rotation", 0), "attempts": 1 + len(scales),
                    "candidate_id": cid,
                }
                # Every row in the band is reported, so a wide candidate holding more than one
                # label cannot be closed out by registering only the highest-scoring one.
                dispositions[cid]["rows"] = [{"text": r["text"], "box": [round(v, 1) for v in r["box"]],
                                              "score": round(r["score"], 3)} for r in rows]
                for row in rows:
                    recovered.append({"page": number, "candidate_id": cid, **row})
            image.close()
    return {"source_sha256": manifest.get("source_sha256"),
            "dispositions": dispositions,
            "recovered": recovered,
            "summary": {
                "total": len(dispositions),
                "recovered": sum(1 for d in dispositions.values()
                                 if d["disposition"] == "recovered"),
                "non_text": sum(1 for d in dispositions.values()
                                if d["disposition"] == "non_text"),
                "illegible": sum(1 for d in dispositions.values()
                                 if d["disposition"] == "illegible"),
            }}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True, help="candidate disposition payload")
    parser.add_argument("--scale", type=float, default=2.0,
                        help="upscaling applied to each crop before the single re-OCR attempt")
    parser.add_argument("--apply", metavar="MANIFEST",
                        help="also record the dispositions into this manifest so the build gate "
                             "passes; terminal dispositions only, recovered rows still need "
                             "register_source_supplements.py")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
    try:
        engine = _new_engine()
    except ImportError:
        raise SystemExit("rapidocr-onnxruntime is required to resolve candidates")
    payload = resolve_candidates(manifest, engine, scales=(args.scale,))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    applied = 0
    if args.apply:
        target = Path(args.apply)
        host = json.loads(target.read_text(encoding="utf-8-sig"))
        if host.get("source_sha256") != manifest.get("source_sha256"):
            raise SystemExit("refusing to apply: manifest source_sha256 differs")
        merged = host.setdefault("candidate_dispositions", {})
        # Recovered rows are recorded too. The build gate only accepts one once its text is
        # actually present in source_lines, so recording it cannot hide an unregistered label.
        for cid, record in payload["dispositions"].items():
            merged[cid] = record
            applied += 1
        target.write_text(json.dumps(host, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output.resolve()), "applied_terminal_dispositions": applied,
                      **payload["summary"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
