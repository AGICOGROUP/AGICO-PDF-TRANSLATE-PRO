from pathlib import Path
import re
import unittest
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def numbered_gate_count(text: str, heading: str) -> int:
    section = text.split(heading, 1)[1]
    section = section.split("\n## ", 1)[0]
    return len(re.findall(r"(?m)^\d+\. ", section))


class IndependentQualityGateContractTests(unittest.TestCase):
    def test_native_and_scan_reject_empty_review_in_their_own_runtime(self):
        # The contract is independent evidence validation, not six/seven headings.
        checks = {
            'native': "from run_v6_job import validate_translation_review; validate_translation_review({}, {1: {'body'}}, 's', 'c')",
            'scan': "from verify_scan import validate_translation_review; errors=validate_translation_review({}, {'selected_pages':[1], 'source_lines':[]}, 's', 'c'); raise ValueError(errors) if errors else SystemExit(0)",
        }
        for adapter, code in checks.items():
            with self.subTest(adapter=adapter):
                scripts = ROOT / 'pdf' / adapter / 'scripts'
                result = subprocess.run([sys.executable, '-c', code], cwd=scripts, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'translation review', result.stderr)

    def test_image_has_six_independent_final_gates(self):
        skill = (ROOT / "image" / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(numbered_gate_count(skill, "## Final gates"), 6)
        self.assertNotIn("Apply the scan quality gates", skill)
        self.assertNotIn("all references it requires", skill)

    def test_visual_review_is_exception_driven(self):
        for path in (
            ROOT / "pdf" / "native" / "SKILL.md",
            ROOT / "pdf" / "scan" / "SKILL.md",
            ROOT / "image" / "SKILL.md",
        ):
            text = path.read_text(encoding="utf-8").casefold()
            self.assertIn("anomal", text)
            self.assertIn("changed", text)


if __name__ == "__main__":
    unittest.main()
