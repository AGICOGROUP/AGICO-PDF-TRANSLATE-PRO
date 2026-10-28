from __future__ import annotations

import json
import os
import subprocess
import shutil
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "ocr_language_guard.py"
sys.path.insert(0, str(ROOT / "scripts"))

import ocr_language_guard as guard  # noqa: E402


@pytest.mark.parametrize("name", ["ch_PP-OCRv3_rec_infer.onnx", "custom_rec.onnx"])
def test_model_path_uses_configured_recogniser(tmp_path, monkeypatch, name):
    import rapidocr_onnxruntime

    model = tmp_path / "models" / name
    model.parent.mkdir()
    model.write_bytes(b"configured recogniser")
    # A different installed model must never override the active recogniser.
    (model.parent / "ch_PP-OCRv4_rec_infer.onnx").write_bytes(b"inactive")
    (tmp_path / "config.yaml").write_text(
        f"Rec:\n  model_path: models/{name}\n", encoding="utf-8"
    )
    monkeypatch.setattr(rapidocr_onnxruntime, "__file__", str(tmp_path / "__init__.py"))
    assert guard.model_path() == model.resolve()


def test_model_path_accepts_configured_absolute_path(tmp_path, monkeypatch):
    import rapidocr_onnxruntime

    model = tmp_path / "outside_package.onnx"
    model.write_bytes(b"recogniser")
    package = tmp_path / "package"
    package.mkdir()
    (package / "config.yaml").write_text(
        f"Rec:\n  model_path: '{model.as_posix()}'\n", encoding="utf-8"
    )
    monkeypatch.setattr(rapidocr_onnxruntime, "__file__", str(package / "__init__.py"))
    assert guard.model_path() == model.resolve()


@pytest.mark.parametrize("config", [None, "Rec: {}", "Rec: []", "Rec: [", "Rec:\n  model_path: models/missing.onnx"])
def test_model_path_fails_closed_for_unverifiable_configuration(tmp_path, monkeypatch, config):
    import rapidocr_onnxruntime

    models = tmp_path / "models"
    models.mkdir()
    (models / "ch_PP-OCRv4_rec_infer.onnx").write_bytes(b"unselected")
    if config is not None:
        (tmp_path / "config.yaml").write_text(config, encoding="utf-8")
    monkeypatch.setattr(rapidocr_onnxruntime, "__file__", str(tmp_path / "__init__.py"))
    with pytest.raises(SystemExit, match="recognition"):
        guard.model_path()


def test_dictionary_reuses_metadata_without_sharing_mutable_results(tmp_path, monkeypatch):
    import onnxruntime as ort

    # Use the installed model: repeated alphabet inspection should not build
    # another ONNX session or let a caller corrupt the next safety check.
    selected = tmp_path / "recogniser.onnx"
    shutil.copyfile(guard.model_path(), selected)
    monkeypatch.setattr(guard, "model_path", lambda: selected)
    with patch.object(ort, "InferenceSession", wraps=ort.InferenceSession) as load:
        first = guard.dictionary()
        first.clear()
        second = guard.dictionary()
    assert len(second) > 1000
    assert load.call_count == 1


def test_dictionary_reload_after_model_replacement(tmp_path, monkeypatch):
    import onnxruntime as ort

    original = guard.model_path()
    selected = tmp_path / "recogniser.onnx"
    shutil.copyfile(original, selected)
    monkeypatch.setattr(guard, "model_path", lambda: selected)
    with patch.object(ort, "InferenceSession", wraps=ort.InferenceSession) as load:
        first = guard.dictionary()
        stat = selected.stat()
        os.utime(selected, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        second = guard.dictionary()
    assert first == second
    assert load.call_count == 2


@pytest.mark.parametrize("metadata", [{}, {"character": ""}, {"character": "\n"}])
def test_unverifiable_model_dictionary_is_rejected(tmp_path, monkeypatch, metadata):
    import onnxruntime as ort

    selected = tmp_path / "recogniser.onnx"
    selected.write_bytes(b"metadata fixture")
    monkeypatch.setattr(guard, "model_path", lambda: selected)
    session = SimpleNamespace(get_modelmeta=lambda: SimpleNamespace(custom_metadata_map=metadata))
    monkeypatch.setattr(ort, "InferenceSession", lambda *args, **kwargs: session)
    with pytest.raises(SystemExit, match="no character metadata"):
        guard.dictionary()


def test_repeated_cyrillic_entries_cannot_fake_a_supported_alphabet():
    table = guard.coverage(["А"] * 100)
    assert guard.unsupported_languages(["ru"], table)


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
