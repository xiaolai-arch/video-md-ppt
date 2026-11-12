"""S4.6 核查门禁的回归测试。

重点守住历史事故：--slides 路径缺失时静默跳过扩展页覆盖，导致假 PASS。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _helpers import factcheck_table, output_of, run_script, write_deck, write_enrichment


class FactcheckGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.factcheck = self.root / "fact-check.md"
        self.enrichment = self.root / "enrichment.md"
        self.slides = self.root / "slides" / "slides.md"
        self.factcheck.write_text(factcheck_table(), encoding="utf-8")
        write_enrichment(self.enrichment)
        write_deck(self.slides)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_gate(self, *extra: object):
        return run_script(
            "check_factcheck.py",
            self.factcheck,
            "--enrichment",
            self.enrichment,
            *extra,
        )

    def test_requires_slides_or_explicit_skip(self) -> None:
        proc = self.run_gate()
        self.assertEqual(proc.returncode, 2, output_of(proc))
        self.assertIn("--allow-no-slides", output_of(proc))

    def test_missing_slides_path_fails_instead_of_skipping(self) -> None:
        missing = self.root / "nope" / "slides.md"
        proc = self.run_gate("--slides", missing)
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("不会跳过页面覆盖检查", output_of(proc))

    def test_uncovered_ext_page_fails(self) -> None:
        rows = [
            f"| F{i:02d} | 笔记 | 通用主张 {i} | 事实 | OK | 抽查通过 | — |"
            for i in range(1, 19)
        ]
        rows += [
            "| F19 | E01 | 深挖卡 01 | 事实 | OK | 与视频一致 | — |",
            "| F20 | E02 | 深挖卡 02 | 事实 | OK | 与视频一致 | — |",
        ]
        self.factcheck.write_text(factcheck_table(rows), encoding="utf-8")
        proc = self.run_gate("--slides", self.slides)
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("未核查的扩展页", output_of(proc))
        self.assertIn("p2", output_of(proc))

    def test_covered_deck_passes(self) -> None:
        proc = self.run_gate("--slides", self.slides)
        self.assertEqual(proc.returncode, 0, output_of(proc))
        self.assertIn("OVERALL PASS", output_of(proc))

    def test_allow_no_slides_passes(self) -> None:
        proc = self.run_gate("--allow-no-slides")
        self.assertEqual(proc.returncode, 0, output_of(proc))

    def test_error_with_todo_treatment_fails(self) -> None:
        table = factcheck_table().replace(
            "| F01 | 笔记 | 通用主张 1 | 事实 | OK | 抽查通过 | — |",
            "| F01 | 笔记 | 通用主张 1 | 事实 | ERROR | 有误 | 待处理 |",
        )
        self.factcheck.write_text(table, encoding="utf-8")
        proc = self.run_gate("--slides", self.slides)
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("ERROR 未处理", output_of(proc))

    def test_contested_without_marking_fails(self) -> None:
        table = factcheck_table().replace(
            "| F01 | 笔记 | 通用主张 1 | 事实 | OK | 抽查通过 | — |",
            "| F01 | 笔记 | 通用主张 1 | 事实 | CONTESTED | 两派说法 | 不管 |",
        )
        self.factcheck.write_text(table, encoding="utf-8")
        proc = self.run_gate("--slides", self.slides)
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("CONTESTED 未标注争议", output_of(proc))

    def test_empty_verdict_fails(self) -> None:
        table = factcheck_table().replace(
            "| F01 | 笔记 | 通用主张 1 | 事实 | OK | 抽查通过 | — |",
            "| F01 | 笔记 | 通用主张 1 | 事实 |  | 漏判 | — |",
        )
        self.factcheck.write_text(table, encoding="utf-8")
        proc = self.run_gate("--slides", self.slides)
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("判定为空", output_of(proc))

    def test_missing_enrichment_path_fails(self) -> None:
        proc = self.run_gate("--slides", self.slides, "--enrichment", self.root / "missing.md")
        # --enrichment 重复传入时 argparse 取最后一个。
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("--enrichment 路径不存在", output_of(proc))

    def test_missing_deep_card_fails(self) -> None:
        self.enrichment.write_text(
            self.enrichment.read_text(encoding="utf-8") + "\n### E03 未核查卡\n",
            encoding="utf-8",
        )
        proc = self.run_gate("--slides", self.slides)
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("未核查的深挖卡", output_of(proc))
        self.assertIn("E03", output_of(proc))


if __name__ == "__main__":
    unittest.main()