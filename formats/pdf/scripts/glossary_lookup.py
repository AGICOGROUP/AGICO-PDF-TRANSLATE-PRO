from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_GLOSSARY = Path(__file__).resolve().parents[1] / "scan" / "references" / "cement-terminology.md"


def parse_glossary(path: Path) -> tuple[dict[str, dict], dict[str, list[str]]]:
    entries: dict[str, dict] = {}
    history: dict[str, list[str]] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        metadata = {}
        for comment in re.findall(r"<!--(.*?)-->", line):
            try:
                value = json.loads(comment.strip())
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                if isinstance(value.get("aliases"), list):
                    metadata["aliases"] = [a for a in value["aliases"] if isinstance(a, str)]
                if isinstance(value.get("context"), str):
                    metadata["context"] = value["context"]
        line = re.sub(r"<!--.*?-->", "", line)
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        source, translation = cells[0], cells[1]
        if (
            not source
            or not translation
            or source == "中文术语"
            or set(source) <= {"-", ":", " "}
            or set(translation) <= {"-", ":", " "}
        ):
            continue
        history.setdefault(source, []).append(translation)
        entries[source] = {
            "source": source,
            "translation": translation,
            "line": line_number,
            **metadata,
        }
    return entries, history


def scan_text(text: str, entries: dict[str, dict]) -> list[dict]:
    occupied: list[tuple[int, int]] = []
    matches: list[dict] = []
    for source in sorted(entries, key=lambda value: (-len(value), value)):
        start = text.find(source)
        while start >= 0:
            end = start + len(source)
            if not any(start < right and end > left for left, right in occupied):
                matches.append({**entries[source], "start": start, "end": end})
                occupied.append((start, end))
            start = text.find(source, start + 1)
    return sorted(matches, key=lambda item: (item["start"], -len(item["source"])))



def _english_key(text: str) -> str:
    # Match Python's Unicode IGNORECASE equivalence for I variants as well.
    return " ".join(text.casefold().replace("i\u0307", "i").replace("\u0131", "i").split())


def lookup_english(term: str, entries: dict[str, dict]) -> list[dict]:
    """Return every exact preferred/alias sense; never silently choose a sense."""
    key = _english_key(term)
    return [dict(entry) for entry in entries.values()
            if any(_english_key(word) == key for word in
                   [entry["translation"], *entry.get("aliases", [])])]


def scan_english(text: str, entries: dict[str, dict]) -> list[dict]:
    """Longest whole-phrase matches with all contextual senses retained."""
    index = {}
    for entry in entries.values():
        for phrase in [entry["translation"], *entry.get("aliases", [])]:
            key = _english_key(phrase)
            if len(key) < 3:
                continue
            choices = index.setdefault(key, {})
            choices[entry["source"]] = entry
    if not index or not text:
        return []
    phrases = sorted(index, key=lambda p: (-len(p), p))
    pattern = r"(?<![\w])(?:" + "|".join(
        r"\s+".join(re.escape(part) for part in p.split()) for p in phrases) + r")(?![\w])"
    matches = []
    for match in re.finditer(pattern, text, re.IGNORECASE):
        for entry in index[_english_key(match.group())].values():
            matches.append({**entry, "start": match.start(), "end": match.end()})
    return matches


def page_terms(text: str, entries: dict[str, dict]) -> list[dict]:
    """Context candidates, not automatic replacements or semantic approval."""
    found = {m["source"]: {k: v for k, v in m.items() if k not in {"start", "end"}}
             for m in [*scan_text(text, entries), *scan_english(text, entries)]}
    return list(found.values())

def main(default_glossary: Path = DEFAULT_GLOSSARY) -> None:
    parser = argparse.ArgumentParser(description="Query the bundled cement terminology table")
    parser.add_argument("--glossary", type=Path, default=default_glossary)
    subparsers = parser.add_subparsers(dest="command", required=True)
    lookup = subparsers.add_parser("lookup")
    lookup.add_argument("term")
    lookup.add_argument("--source-language", choices=("zh", "en"), default="zh")
    scan = subparsers.add_parser("scan")
    scan.add_argument("text")
    scan.add_argument("--source-language", choices=("zh", "en"), default="zh")
    args = parser.parse_args()

    entries, history = parse_glossary(args.glossary)
    if args.source_language == "en":
        matches = (lookup_english(args.term, entries) if args.command == "lookup"
                   else scan_english(args.text, entries))
        print(json.dumps({"found": bool(matches), "matches": matches}, ensure_ascii=False))
        if args.command == "lookup" and not matches:
            raise SystemExit(4)
        return
    if args.command == "lookup":
        term = args.term.strip()
        entry = entries.get(term)
        if entry is None:
            print(json.dumps({"found": False, "source": term}, ensure_ascii=False))
            raise SystemExit(4)
        alternatives = list(dict.fromkeys(history[term]))
        print(
            json.dumps(
                {"found": True, **entry, "alternatives": alternatives},
                ensure_ascii=False,
            )
        )
        return

    print(
        json.dumps(
            {"matches": scan_text(args.text, entries)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
