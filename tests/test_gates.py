"""gates.py 的回归测试：退出码、01 豁免、缺产物与“不许静默跳过”。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from _helpers import ROOT, factcheck_table, output_of, run_script, write_enrichment

sys.path.insert(0, str(ROOT / "scripts"))
import gates  # noqa: E402


class ExpectedGatesTest(unittest.TestCase):
    def test_01_exempts_enrichment_and_factcheck(self) -> None:
        expected = gates.expected_gates("01_使用说明_abcd1234", set(gates.GATES))
        self.assertEqual(expected, {"outline", "notes", "slides"})

    def test_other_lessons_require_all_five(self) -> None:
        expected = gates.expected_gates("02_名词_abcd1234", set(gates.GATES))
        self.assertEqual(expected, set(gates.GATES))

    def test_single_gate_run_is_not_exempted(self) -> None:
        expected = gates.expected_gates("01_使用说明_abcd1234", {"enrichment"})
        self.assertEqual(expected, {"enrichment"})


class GatesCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "output").mkdir()
        (self.root / "work").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_gates(self, *args: object):
        return run_script("gates.py", "--root", self.root, *args)

    def test_unknown_gate_is_usage_error(self) -> None:
        proc = self.run_gates("x", "--only", "nope")
        self.assertEqual(proc.returncode, 2, output_of(proc))
        self.assertIn("未知门禁", output_of(proc))

    def test_no_slug_is_usage_error(self) -> None:
        proc = self.run_gates()
        self.assertEqual(proc.returncode, 2, output_of(proc))

    def test_missing_slug_fails(self) -> None:
        proc = self.run_gates("nope_1234")
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("不存在", output_of(proc))

    def test_all_skipped_is_failure(self) -> None:
        (self.root / "output" / "02_empty_abcd1234").mkdir()
        proc = self.run_gates("02_empty_abcd1234", "--only", "notes")
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("没有任何门禁可跑", output_of(proc))

    def test_full_run_missing_artifacts_fails(self) -> None:
        (self.root / "output" / "02_empty_abcd1234").mkdir()
        proc = self.run_gates("02_empty_abcd1234")
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("缺少必要产物", output_of(proc))
        self.assertIn("OVERALL FAIL", output_of(proc))

    def test_factcheck_without_slides_fails_not_skips(self) -> None:
        slug = "02_名词_abcd1234"
        (self.root / "output" / slug).mkdir()
        work = self.root / "work" / slug
        work.mkdir(parents=True)
        (work / "fact-check.md").write_text(factcheck_table(), encoding="utf-8")
        write_enrichment(work / "enrichment.md")

        proc = self.run_gates(slug, "--only", "factcheck")
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("不会跳过页面覆盖检查", output_of(proc))


if __name__ == "__main__":
    unittest.main()