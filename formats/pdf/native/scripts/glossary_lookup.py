"""Adapter-local entry point for the shared terminology lookup implementation."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from glossary_lookup import parse_glossary, scan_text, lookup_english, scan_english, page_terms, main

DEFAULT_GLOSSARY = Path(__file__).resolve().parents[1] / "references" / "cement-terminology.md"

if __name__ == "__main__":
    main(DEFAULT_GLOSSARY)
