from pathlib import Path
import unittest


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


class DirectV6ContractTests(unittest.TestCase):
    def test_skill_declares_original_only_runner_contract(self):
        text = SKILL.read_text(encoding="utf-8")
        for required in (
            "only user-supplied artifact",
            "run_v6_job.py init",
            "run_v6_job.py resume",
            "run_v6_job.py verify",
            "stage is `verified`",
            "selectable PDF vector text",
            "Never use v5 or v6",
            "reviewed_changed_regions",
            "reviewed_anomaly_pages",
            "untranslated_clear_image_labels",
            "text_overlap_failures",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
