from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
DECIDER = ROOT / "formats" / "pdf" / "scripts" / "decide_drawing_translation.py"


class DrawingTranslationModeTests(unittest.TestCase):
    def decide(self, payload: dict) -> dict:
        result = subprocess.run(
            [sys.executable, str(DECIDER), "--inventory-json", json.dumps(payload)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def test_complete_chinese_foreign_bilingual_drawing_is_skipped(self):
        decision = self.decide({
            "document_kind": "engineering-drawing",
            "clear_chinese_label_count": 4,
            "clear_foreign_label_count": 4,
            "matched_bilingual_pair_count": 4,
            "unmatched_chinese_label_count": 0,
            "unmatched_foreign_label_count": 0,
        })
        self.assertEqual("already_bilingual_complete", decision["status"])
        self.assertEqual("skip_translation", decision["action"])
        self.assertTrue(decision["preserve_source_pdf"])
        self.assertFalse(decision["user_input_required"])

    def test_partial_bilingual_drawing_continues_additive_translation(self):
        decision = self.decide({
            "document_kind": "engineering-drawing",
            "clear_chinese_label_count": 4,
            "clear_foreign_label_count": 3,
            "matched_bilingual_pair_count": 3,
            "unmatched_chinese_label_count": 1,
            "unmatched_foreign_label_count": 0,
        })
        self.assertEqual("translation_required", decision["status"])
        self.assertEqual("add_bilingual", decision["action"])
        self.assertFalse(decision["user_input_required"])

    def test_monolingual_drawing_continues_additive_translation(self):
        decision = self.decide({
            "document_kind": "engineering-drawing",
            "clear_chinese_label_count": 0,
            "clear_foreign_label_count": 6,
            "matched_bilingual_pair_count": 0,
            "unmatched_chinese_label_count": 0,
            "unmatched_foreign_label_count": 6,
        })
        self.assertEqual("add_bilingual", decision["action"])
        self.assertFalse(decision["user_input_required"])

    def test_inventory_file_supports_path_safe_automation(self):
        payload = {
            "document_kind": "engineering-drawing",
            "clear_chinese_label_count": 2,
            "clear_foreign_label_count": 2,
            "matched_bilingual_pair_count": 2,
            "unmatched_chinese_label_count": 0,
            "unmatched_foreign_label_count": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "drawing inventory.json"
            inventory.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(DECIDER), "--inventory-file", str(inventory)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("skip_translation", json.loads(result.stdout)["action"])


if __name__ == "__main__":
    unittest.main()
