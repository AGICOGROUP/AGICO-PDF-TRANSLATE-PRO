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
    def test_complete_bilingual_requires_requested_languages_and_all_counts(self):
        complete = {
            'document_kind': 'engineering-drawing',
            'translation_mode': 'add_bilingual',
            'language_pair': ['zh', 'en'], 'requested_language_pair': ['zh', 'es'],
            'clear_chinese_label_count': 4, 'clear_foreign_label_count': 4,
            'matched_bilingual_pair_count': 4,
            'unmatched_chinese_label_count': 0, 'unmatched_foreign_label_count': 0,
        }
        for patch in ({}, {'language_pair': None}, {'requested_language_pair': None}):
            with self.subTest(patch=patch):
                self.assertEqual('add_bilingual', self.decide({**complete, **patch})['action'])
        complete['requested_language_pair'] = ['en', 'zh']
        for field in ('language_pair', 'requested_language_pair', 'unmatched_chinese_label_count'):
            with self.subTest(missing=field):
                payload = {key: value for key, value in complete.items() if key != field}
                self.assertEqual('add_bilingual', self.decide(payload)['action'])
        self.assertEqual('skip_translation', self.decide(complete)['action'])

    def test_saved_route_overrides_missing_or_wrong_inventory_kind_and_mode(self):
        # Complete bilingual counts must never skip an explicit replacement.
        for kind in (None, "document"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                route = Path(directory) / "route.json"
                route.write_text(json.dumps({"document_kind": "engineering-drawing",
                                             "translation_mode": "replace", "error": None}), encoding="utf-8")
                payload = {"document_kind": kind, "translation_mode": "add_bilingual",
                           "clear_chinese_label_count": 2, "clear_foreign_label_count": 2,
                           "matched_bilingual_pair_count": 2}
                result = subprocess.run(
                    [sys.executable, str(DECIDER), "--inventory-json", json.dumps(payload),
                     "--route-report", str(route)], capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("replace", json.loads(result.stdout)["action"])

    def test_missing_kind_does_not_silently_select_replacement(self):
        result = subprocess.run([sys.executable, str(DECIDER), "--inventory-json", "{}"],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(2, result.returncode)
        self.assertIn("route-report", json.loads(result.stdout)["error"])

    def test_explicit_bilingual_document_keeps_additive_mode(self):
        decision = self.decide({"document_kind": "document", "translation_mode": "add_bilingual"})
        self.assertEqual("add_bilingual", decision["action"])

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
            "language_pair": ["zh-CN", "es"],
            "requested_language_pair": ["es", "ZH_cn"],
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
            "language_pair": ["zh", "en"],
            "requested_language_pair": ["zh", "en"],
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
