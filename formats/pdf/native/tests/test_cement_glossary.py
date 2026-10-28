from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "references" / "cement-terminology.md"
LOOKUP = ROOT / "scripts" / "glossary_lookup.py"
# User-supplied 2.0 glossary, canonical LF; checkout line endings are not content.
EXPECTED_SHA256 = "ecc54bab1dd8cfd63b7990e872837e15d704eac8414a5abbb1cb4adf51416a1a"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    # The lookup helper prints CJK terms. A Chinese-locale Windows host decodes a
    # pipe as GBK, so both sides are pinned to UTF-8 instead of following the
    # caller's shell (which the skill docs tell users to set to utf-8 anyway).
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, str(LOOKUP), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
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
