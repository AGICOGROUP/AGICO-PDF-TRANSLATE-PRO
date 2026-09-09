from pathlib import Path
import unittest
import subprocess
import sys


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


class DirectV6ContractTests(unittest.TestCase):
    def test_runner_exposes_source_bound_workflow(self):
        # Exercise the documented interface instead of pinning Skill sentences.
        runner = SKILL.parent / 'scripts' / 'run_v6_job.py'
        for command in ('init', 'resume', 'build-native', 'annotate-images', 'build-images', 'assemble', 'verify'):
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, str(runner), command, '--help'], capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
