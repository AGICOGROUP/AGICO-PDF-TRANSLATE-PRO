from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "ocr_language_guard.py"
sys.path.insert(0, str(ROOT / "scripts"))

import ocr_language_guard as guard  # noqa: E402


def run(*args: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        capture_output=True, text=True, encoding="utf-8", env=environment
    )


class RecogniserAlphabetTests(unittest.TestCase):
    """The bundled ch model must be known exactly, not assumed."""

    @classmethod
    def setUpClass(cls):
        cls.table = guard.coverage(guard.dictionary())

    def test_latin_and_cjk_are_supported(self):
        self.assertTrue(self.table["LATIN"]["supported"])
        self.assertTrue(self.table["CJK"]["supported"])
        self.assertGreaterEqual(self.table["LATIN"]["characters"], 60)

    def test_cyrillic_greek_and_kana_are_not_supported(self):
        for script in ("CYRILLIC", "GREEK", "KATAKANA", "HANGUL", "HIRAGANA"):
            with self.subTest(script=script):
                self.assertFalse(self.table[script]["supported"])

    def test_cyrillic_coverage_is_far_below_a_usable_alphabet(self):
        # Six letters cannot express Russian, which needs sixty-six.
        self.assertLess(self.table["CYRILLIC"]["characters"], 30)


class LanguageRequirementTests(unittest.TestCase):
    def setUp(self):
        self.table = guard.coverage(guard.dictionary())

    def test_common_three_pass(self):
        self.assertEqual([], guard.unsupported_languages(["en", "zh", "es"], self.table))

    def test_russian_is_blocked(self):
        blocked = guard.unsupported_languages(["ru"], self.table)
        self.assertEqual(1, len(blocked))
        self.assertEqual("CYRILLIC", blocked[0]["script"])

    def test_mixed_request_reports_only_the_unsupported_language(self):
        blocked = guard.unsupported_languages(["en", "ru", "zh"], self.table)
        self.assertEqual(["ru"], [item["language"] for item in blocked])

    def test_unmapped_language_is_not_silently_allowed(self):
        blocked = guard.unsupported_languages(["xx"], self.table)
        self.assertEqual(1, len(blocked))
        self.assertIsNone(blocked[0]["script"])


class GuardCliTests(unittest.TestCase):
    def test_supported_languages_exit_zero(self):
        result = run("require", "--languages", "en,zh,es")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_unsupported_language_exits_three_with_reason(self):
        result = run("require", "--languages", "ru")
        self.assertEqual(guard.EXIT_UNSUPPORTED, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("unsupported_script", payload["error"])
        self.assertEqual("CYRILLIC", payload["blocked"][0]["script"])
        self.assertIn("next_step", payload)

    def test_inspect_reports_the_whole_alphabet(self):
        result = run("inspect")
        self.assertEqual(0, result.returncode)
        payload = json.loads(result.stdout)
        for script in ("LATIN", "CJK", "CYRILLIC"):
            self.assertIn(script, payload["recogniser_alphabet"])
        self.assertIn("CYRILLIC", payload["unsupported_scripts"])


if __name__ == "__main__":
    unittest.main()
