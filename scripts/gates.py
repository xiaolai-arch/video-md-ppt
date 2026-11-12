#!/usr/bin/env python3
"""一次跑完一集的所有质量门禁。

用法:
    python scripts/gates.py <slug>
    python scripts/gates.py --all
    python scripts/gates.py <slug> --strict      # 缺产物也算 FAIL
    python scripts/gates.py <slug> --only notes,factcheck

为什么有这个脚本:
    check_factcheck.py 拿到不存在的 --slides 路径时会静默跳过扩展页覆盖检查，
    曾导致 03–09 误报 PASS。本脚本统一解析课件源文件（slides.md，兼容旧的
    slides.rich.md），路径不存在直接判 FAIL，不再给“假通过”。

退出码: 0 全部 PASS（SKIP 不算失败）；1 有 FAIL；2 用法错误。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

GATES = {
    "outline": "S3 大纲",
    "notes": "S4 笔记",
    "enrichment": "S4.5 深挖",
    "factcheck": "S4.6 核查",
    "slides": "S5 课件",
}


def expected_gates(slug: str, only: set[str]) -> set[str]:
    """全量运行时，五道门禁缺一不可；01 是使用说明，按设计豁免深挖与核查。"""
    expected = set(only)
    if only == set(GATES) and slug.startswith("01_"):
        expected -= {"enrichment", "factcheck"}
    return expected


def run(args: list[str]) -> tuple[int, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [PY, *args],
        cwd=CODE_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def resolve_slides(slug_dir: Path) -> tuple[Path | None, str]:
    """返回 (课件源文件, 说明)。只认 canonical 名，兼容旧名并给出提示。"""
    canonical = slug_dir / "slides" / "slides.md"
    if canonical.exists():
        return canonical, "slides/slides.md"
    legacy = slug_dir / "slides" / "slides.rich.md"
    if legacy.exists():
        return legacy, "slides/slides.rich.md（旧名，建议改为 slides.md）"
    return None, "找不到课件源文件"


def check_one(slug: str, only: set[str], strict: bool, root: Path) -> bool:
    slug_dir = root / "output" / slug
    work_dir = root / "work" / slug
    if not slug_dir.exists():
        print(f"FAIL {slug}: output/{slug} 不存在")
        return False

    slides, slides_note = resolve_slides(slug_dir)
    print(f"\n=== {slug}")
    print(f"    课件源：{slides_note}")

    results: dict[str, str] = {}
    details: list[str] = []

    # 全量运行时，五道门禁缺一不可；01 是使用说明，没有深挖与核查，按设计豁免。
    full_run = only == set(GATES)
    expected = expected_gates(slug, only)

    def gate(name: str, argv: list[str] | None) -> None:
        if name not in only:
            return
        if argv is None:
            if full_run and name in expected:
                results[name] = "FAIL"
                details.append(f"--- {name} ---\n缺少必要产物")
            else:
                results[name] = "SKIP"
            return
        code, out = run(argv)
        results[name] = "PASS" if code == 0 else "FAIL"
        if code != 0:
            tail = "\n".join(out.strip().splitlines()[-12:])
            details.append(f"--- {name} 输出 ---\n{tail}")

    outline = work_dir / "outline.md"
    notes = slug_dir / "notes.md"
    enrichment = work_dir / "enrichment.md"
    factcheck = work_dir / "fact-check.md"
    slides_dir = slug_dir / "slides"

    gate(
        "outline",
        [str(CODE_ROOT / "scripts/check_outline.py"), str(outline), "--slug", slug]
        if outline.exists()
        else None,
    )
    gate(
        "notes",
        [str(CODE_ROOT / "scripts/verify_notes.py"), str(notes), "--slug", slug]
        if notes.exists()
        else None,
    )
    gate(
        "enrichment",
        [str(CODE_ROOT / "scripts/check_enrichment.py"), str(enrichment)]
        if enrichment.exists()
        else None,
    )
    if factcheck.exists():
        # 即使课件源缺失也要把 --slides 传进去：check_factcheck 会因此 FAIL，
        # 而不是静默跳过扩展页覆盖检查。
        slide_arg = slides or (slides_dir / "slides.md")
        argv = [
            str(CODE_ROOT / "scripts/check_factcheck.py"),
            str(factcheck),
            "--enrichment",
            str(enrichment),
            "--slides",
            str(slide_arg),
        ]
        gate("factcheck", argv)
    else:
        gate("factcheck", None)

    has_png = bool(list(slides_dir.glob("selfcheck.*"))) if slides_dir.exists() else False
    gate(
        "slides",
        [str(CODE_ROOT / "scripts/check_slides.py"), str(slides_dir)] if has_png else None,
    )

    for name in GATES:
        if name in results:
            print(f"    [{results[name]:4}] {GATES[name]}")

    if details:
        print()
        print("\n".join(details))

    failed = [k for k, v in results.items() if v == "FAIL"]
    skipped = [k for k, v in results.items() if v == "SKIP"]
    if results and len(skipped) == len(results):
        print("OVERALL FAIL: 没有任何门禁可跑（检查 slug、产物路径或 --only）")
        return False
    if skipped and strict:
        failed.extend(f"{k}(SKIP)" for k in skipped if k in expected)
    if failed:
        print(f"OVERALL FAIL: {', '.join(failed)}")
        return False
    print(f"OVERALL PASS（{len(results) - len(skipped)} 项通过，{len(skipped)} 项跳过）")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="一次跑完一集的所有门禁")
    ap.add_argument("slug", nargs="?", help="output/ 下的目录名；省略时配合 --all")
    ap.add_argument("--all", action="store_true", help="遍历 output/ 下所有课时")
    ap.add_argument("--only", default=",".join(GATES), help="逗号分隔：outline,notes,enrichment,factcheck,slides")
    ap.add_argument("--strict", action="store_true", help="缺产物也判 FAIL")
    ap.add_argument(
        "--root",
        type=Path,
        default=CODE_ROOT,
        help="数据根目录（含 output/ 与 work/），默认仓库根；测试用",
    )
    args = ap.parse_args()

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    unknown = only - set(GATES)
    if unknown:
        print(f"未知门禁：{', '.join(sorted(unknown))}")
        return 2

    root: Path = args.root.resolve()
    if args.all:
        out_dir = root / "output"
        if not out_dir.exists():
            print(f"找不到 {out_dir}")
            return 1
        slugs = sorted(p.name for p in out_dir.iterdir() if p.is_dir())
    elif args.slug:
        slugs = [args.slug]
    else:
        print("用法：python scripts/gates.py <slug> 或 --all")
        return 2

    ok = True
    summary: list[tuple[str, str]] = []
    for slug in slugs:
        passed = check_one(slug, only, args.strict, root)
        ok = ok and passed
        summary.append((slug, "PASS" if passed else "FAIL"))

    print("\n=== 汇总")
    for slug, status in summary:
        print(f"  {status:4}  {slug}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
