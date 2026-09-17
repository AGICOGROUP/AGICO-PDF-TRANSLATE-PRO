from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "references" / "cement-terminology.md"
LOOKUP = ROOT / "scripts" / "glossary_lookup.py"
# User-supplied revised glossary, canonical LF; checkout line endings are not content.
EXPECTED_SHA256 = "4e80bb57ff929cb76f6596edaaee8f5e096626a73622411e06af2f9918a4dd88"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LOOKUP), *args], capture_output=True, text=True
    )


class CementGlossaryTests(unittest.TestCase):
    def test_bundles_exact_user_glossary_and_documents_precedence(self):
        self.assertTrue(GLOSSARY.is_file())
        self.assertEqual(hashlib.sha256(GLOSSARY.read_bytes().replace(b'\r\n', b'\n')).hexdigest(), EXPECTED_SHA256)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("cement-terminology.md", skill)
        self.assertIn("glossary_lookup.py", skill)
        self.assertIn("model", skill.lower())

    def test_lookup_keeps_revised_term_separate_from_context_and_aliases(self):
        result = run("lookup", "窑头罩")
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = json.loads(result.stdout)
        self.assertEqual(entry["translation"], "Kiln hood")
        self.assertIn("Firing hood", entry["aliases"])
        self.assertIn("语境", entry["context"])
        self.assertNotIn("<!--", " ".join(entry["alternatives"]))

    def test_scan_returns_only_terms_found_in_source_text(self):
        result = run("scan", "本项目采用篦冷机和高压辊磨机。")
        self.assertEqual(result.returncode, 0, result.stderr)
        matches = {item["source"]: item["translation"] for item in json.loads(result.stdout)["matches"]}
        self.assertEqual(matches["篦冷机"], "Grate Cooler")
        self.assertEqual(matches["高压辊磨机"], "High pressure grinding roll (HPGR)")

    def test_absent_term_is_not_invented(self):
        result = run("lookup", "不存在于词表的测试术语")
        self.assertEqual(result.returncode, 4)
        self.assertEqual(json.loads(result.stdout)["found"], False)


if __name__ == "__main__":
    unittest.main()
