"""测试公用工具：调用 scripts/ 下的脚本。

测试只依赖标准库 + Pillow；不读取真实 work/ 与 output/。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_script(script: str, *args: object) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def output_of(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


FACTCHECK_HEADER = "| ID | 位置 | 主张 | 类型 | 判定 | 说明 | 处理 |"
FACTCHECK_SEP = "|---|---|---|---|---|---|---|"


def factcheck_table(rows: list[str] | None = None) -> str:
    """生成一张合法的 20 行核查表，覆盖 E01 / E02 / p2。"""
    if rows is None:
        rows = [f"| F{i:02d} | 笔记 | 通用主张 {i} | 事实 | OK | 抽查通过 | — |" for i in range(1, 18)]
        rows += [
            "| F18 | E01 | 深挖卡 01 | 事实 | OK | 与视频一致 | — |",
            "| F19 | E02 | 深挖卡 02 | 事实 | OK | 与视频一致 | — |",
            "| F20 | 课件 p2 | 扩展页主张 | 扩展 | OK | 已核对 | — |",
        ]
    return "\n".join([FACTCHECK_HEADER, FACTCHECK_SEP, *rows]) + "\n"


def write_enrichment(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "### E01 第一张卡\n\n"
        "- 对应视频：[01:00]\n- 一句话：示例\n- 原理：示例\n- 例：示例\n"
        "- 易错：示例\n- 迁移：示例\n- 来源：〔视频〕[01:00]\n\n"
        "### E02 第二张卡\n\n"
        "- 对应视频：[02:00]\n- 一句话：示例\n- 原理：示例\n- 例：示例\n"
        "- 易错：示例\n- 迁移：示例\n- 来源：〔视频〕[02:00]\n",
        encoding="utf-8",
    )


def write_deck(path: Path, ext_on_page_two: bool = True) -> None:
    """写一个最小 Marp 源文件：两页，第二页带 src ext。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = '\n<span class="src ext">扩展</span>\n' if ext_on_page_two else ""
    path.write_text(
        "---\nmarp: true\n---\n\n# 第一页\n\n正文\n\n---\n\n# 第二页\n\n正文\n" + ext,
        encoding="utf-8",
    )