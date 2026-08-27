from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent


def numbered_gate_count(text: str, heading: str) -> int:
    section = text.split(heading, 1)[1]
    section = section.split("\n## ", 1)[0]
    return len(re.findall(r"(?m)^\d+\. ", section))


class IndependentQualityGateContractTests(unittest.TestCase):
    def test_native_has_six_internal_final_gates(self):
        skill = (ROOT / "pdf" / "native" / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(numbered_gate_count(skill, "## Final gates"), 6)
        self.assertNotIn("Render and inspect every page", skill)

    def test_scan_has_seven_internal_final_gates(self):
        gates = (ROOT / "pdf" / "scan" / "references" / "quality-gates.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(numbered_gate_count(gates, "## Seven final gates"), 7)
        self.assertNotIn("every page and every image region reviewed", gates)

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
