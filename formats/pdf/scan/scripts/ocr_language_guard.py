#!/usr/bin/env python3
"""Refuse an OCR job whose script the bundled recogniser cannot actually emit.

The recogniser maps every glyph onto its own character dictionary, so an
unsupported script never produces an error or an invalid character: it produces
confident lookalike substitutions. On a Russian drawing the bundled
ch_PP-OCRv4_rec model turned "ВЛЕТНА ОБЛОГА" into "BJETHA O6JIOTA" at 0.84
confidence, which every downstream check accepted.

The dictionary is embedded in the recognition model's ONNX metadata, so the set
of scripts the engine can output is knowable exactly rather than guessed. This
guard reads it, compares each script against the alphabet it would need, and
fails before any translation work is done.

  python scripts/ocr_language_guard.py inspect
  python scripts/ocr_language_guard.py require --languages en,zh,es
  python scripts/ocr_language_guard.py require --languages ru      # exits 3
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

SCRIPT_TOKENS = ("CYRILLIC", "GREEK", "ARABIC", "HEBREW", "THAI", "HIRAGANA",
                 "KATAKANA", "HANGUL", "DEVANAGARI", "ARMENIAN", "GEORGIAN")

# Characters a usable alphabet for that script must contain. Russian alone needs
# 66 Cyrillic letters; the bundled model carries six, so the margin is wide.
MINIMUM_ALPHABET = {
    "LATIN": 60,
    "CJK": 800,
    "CYRILLIC": 30,
    "GREEK": 30,
    "ARABIC": 30,
    "HEBREW": 30,
    "THAI": 30,
    "HANGUL": 30,
    "HIRAGANA": 30,
    "KATAKANA": 30,
    "DEVANAGARI": 30,
    "ARMENIAN": 30,
    "GEORGIAN": 30,
}

LANGUAGE_SCRIPT = {
    "zh": "CJK", "ja": "CJK", "ko": "HANGUL",
    "en": "LATIN", "es": "LATIN", "fr": "LATIN", "de": "LATIN", "pt": "LATIN",
    "it": "LATIN", "nl": "LATIN", "pl": "LATIN", "tr": "LATIN", "vi": "LATIN",
    "id": "LATIN", "ms": "LATIN", "ro": "LATIN", "sv": "LATIN", "da": "LATIN",
    "ru": "CYRILLIC", "uk": "CYRILLIC", "be": "CYRILLIC", "bg": "CYRILLIC",
    "sr": "CYRILLIC", "mk": "CYRILLIC", "kk": "CYRILLIC", "mn": "CYRILLIC",
    "el": "GREEK",
    "ar": "ARABIC", "fa": "ARABIC", "ur": "ARABIC",
    "he": "HEBREW",
    "th": "THAI",
    "hi": "DEVANAGARI",
    "hy": "ARMENIAN",
    "ka": "GEORGIAN",
}

EXIT_UNSUPPORTED = 3


def script_of(character: str) -> str | None:
    if not character:
        return None
    try:
        name = unicodedata.name(character[0])
    except ValueError:
        return None
    for token in SCRIPT_TOKENS:
        if token in name:
            return token
    if "CJK" in name or "IDEOGRAPH" in name:
        return "CJK"
    if "LATIN" in name:
        return "LATIN"
    return None


def model_path() -> Path:
    import rapidocr_onnxruntime
    import yaml

    # Follow the same Rec.model_path used by RapidOCR(), rather than guessing
    # a model version or inspecting an inactive model left in the package.
    root = Path(rapidocr_onnxruntime.__file__).resolve().parent
    config_path = root / "config.yaml"
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        selected = config["Rec"]["model_path"]
        if not isinstance(selected, str) or not selected.strip():
            raise ValueError("Rec.model_path must be a nonempty string")
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"cannot determine active recognition model from {config_path}: {error}") from error
    candidate = (root / selected).resolve()
    if not candidate.is_file():
        raise SystemExit("recognition model not found at %s" % candidate)
    return candidate


def dictionary() -> list[str]:
    candidate = model_path().resolve()
    stat = candidate.stat()
    # Cache metadata only, not the heavy ONNX session. A replacement model must
    # be rechecked, and callers must not be able to mutate the cached alphabet.
    return list(_model_dictionary(str(candidate), stat.st_size, stat.st_mtime_ns))


@lru_cache(maxsize=4)
def _model_dictionary(path: str, size: int, modified_ns: int) -> tuple[str, ...]:
    import onnxruntime as ort

    session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    raw = session.get_modelmeta().custom_metadata_map.get("character")
    if not raw:
        raise SystemExit("recognition model exposes no character metadata")
    entries = tuple(entry for entry in raw.splitlines() if entry)
    if not entries:
        raise SystemExit("recognition model exposes no character metadata")
    return entries


def coverage(entries: list[str]) -> dict:
    counts = Counter()
    for entry in set(entries):
        counts[script_of(entry)] += 1
    report = {}
    for script, count in counts.items():
        if script is None:
            continue
        minimum = MINIMUM_ALPHABET.get(script)
        report[script] = {
            "characters": count,
            "minimum_required": minimum,
            "supported": bool(minimum) and count >= minimum,
        }
    return report


def unsupported_languages(languages: list[str], table: dict) -> list[dict]:
    blocked = []
    for language in languages:
        script = LANGUAGE_SCRIPT.get(language)
        if script is None:
            blocked.append({"language": language, "script": None,
                            "reason": "language is not mapped; declare its script first"})
            continue
        entry = table.get(script)
        if not entry or not entry["supported"]:
            blocked.append({
                "language": language,
                "script": script,
                "characters": (entry or {}).get("characters", 0),
                "minimum_required": (entry or {}).get("minimum_required"),
                "reason": "the bundled recogniser cannot emit this script",
            })
    return blocked


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("inspect", "require"))
    parser.add_argument("--languages", default="",
                        help="comma-separated language codes expected in the source")
    args = parser.parse_args(argv)

    table = coverage(dictionary())
    languages = [item.strip().lower() for item in args.languages.split(",") if item.strip()]

    if args.action == "inspect" or not languages:
        print(json.dumps({"passed": True, "recogniser_alphabet": table,
                          "unsupported_scripts": sorted(
                              name for name, entry in table.items() if not entry["supported"])},
                         ensure_ascii=False, indent=1))
        return 0

    blocked = unsupported_languages(languages, table)
    if blocked:
        print(json.dumps({
            "passed": False,
            "error": "unsupported_script",
            "requested": languages,
            "blocked": blocked,
            "recogniser_alphabet": table,
            "next_step": ("install a recognition model for that script, or route the job"
                          " to a human reviewer; do not translate from these OCR results"),
        }, ensure_ascii=False, indent=1))
        return EXIT_UNSUPPORTED

    print(json.dumps({"passed": True, "requested": languages,
                      "recogniser_alphabet": {name: table[name] for name in
                                              sorted({LANGUAGE_SCRIPT[lang] for lang in languages})}},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
