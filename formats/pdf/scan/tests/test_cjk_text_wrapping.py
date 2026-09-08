import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from contracts import _wrap_paragraph


class CjkTextWrappingTests(unittest.TestCase):
    def test_wraps_chinese_without_spaces_at_character_boundaries(self):
        lines = _wrap_paragraph("绝缘限位块供应商", "Helvetica", 10, 25)
        self.assertGreater(len(lines), 1)
        self.assertEqual("".join(lines), "绝缘限位块供应商")


if __name__ == "__main__":
    unittest.main()
