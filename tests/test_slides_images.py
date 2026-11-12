"""check_slides.py 的图片完整性回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from _helpers import output_of, run_script


class SlideImageGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.slides = self.root / "slides"
        self.assets = self.root / "assets"
        self.slides.mkdir()
        self.assets.mkdir()
        Image.new("RGB", (1280, 720), "white").save(self.slides / "selfcheck.001", format="PNG")
        Image.new("RGB", (100, 100), "navy").save(self.assets / "a.png")
        self.write_deck("![w:50 示例图](../assets/a.png)")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_deck(self, image_markdown: str) -> None:
        (self.slides / "slides.md").write_text(
            "---\nmarp: true\n---\n\n# 一页\n\n" + image_markdown + "\n",
            encoding="utf-8",
        )

    def run_check(self, *extra: object):
        return run_script("check_slides.py", self.slides, *extra)

    def test_valid_image_passes(self) -> None:
        proc = self.run_check()
        self.assertEqual(proc.returncode, 0, output_of(proc))
        self.assertIn("OVERALL PASS", output_of(proc))
        self.assertIn("0 image error(s)", output_of(proc))
        self.assertIn("0 warning(s)", output_of(proc))

    def test_missing_image_fails(self) -> None:
        self.write_deck("![w:50 缺图](../assets/missing.png)")
        proc = self.run_check()
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("图片不存在", output_of(proc))

    def test_external_image_fails(self) -> None:
        self.write_deck("![w:50 外链](https://example.com/a.png)")
        proc = self.run_check()
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertIn("外链图片", output_of(proc))

    def test_upscaled_image_warns_but_passes(self) -> None:
        self.write_deck("![w:200 放大](../assets/a.png)")
        proc = self.run_check()
        self.assertEqual(proc.returncode, 0, output_of(proc))
        self.assertIn("WARN image", output_of(proc))
        self.assertIn("被放大", output_of(proc))

    def test_upscaled_image_fails_under_strict_images(self) -> None:
        self.write_deck("![w:200 放大](../assets/a.png)")
        proc = self.run_check("--strict-images")
        self.assertEqual(proc.returncode, 1, output_of(proc))

    def test_missing_alt_warns(self) -> None:
        self.write_deck("![w:50](../assets/a.png)")
        proc = self.run_check()
        self.assertEqual(proc.returncode, 0, output_of(proc))
        self.assertIn("缺少 alt 文本", output_of(proc))

    def test_data_uri_is_not_external(self) -> None:
        self.write_deck("![w:50 内联](data:image/png;base64,AAAA)")
        proc = self.run_check()
        self.assertEqual(proc.returncode, 0, output_of(proc))
        self.assertNotIn("外链图片", output_of(proc))


if __name__ == "__main__":
    unittest.main()