#!/usr/bin/env python3
"""校验 S4.6 内容核查表 fact-check.md。

用法:
    python scripts/check_factcheck.py work/<slug>/fact-check.md \
        --enrichment work/<slug>/enrichment.md \
        --slides output/<slug>/slides/slides.md

    --slides 路径不存在时直接 FAIL，不会静默跳过扩展页覆盖检查。

规则:
1. 表格至少 20 行，列头必须包含：ID / 位置 / 主张 / 类型 / 判定 / 说明 / 处理
2. 判定只允许 OK / WEAK / ERROR / CONTESTED
3. ERROR 行必须有具体处理，不能是“待处理/TODO/未处理”
4. CONTESTED 行的处理必须含“标注/加注/限定/说明”
5. enrichment.md 里每张 E 卡至少被核查一次
6. slides 里每个带 `.src.ext` 角标的页面至少被核查一次（位置写 pN）
7. 扫描绝对化措辞，输出 WARN 供人工复核（不直接判 FAIL）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CARD_RE = re.compile(r"^###\s+(E\d{2})\b", re.MULTILINE)
ABSOLUTE_RE = re.compile(r"(所有|一定|永远|绝不|唯一|从不|完全|必定|百分之百)")
VERDICTS = {"OK", "WEAK", "ERROR", "CONTESTED"}
REQUIRED_HEADERS = ["ID", "位置", "主张", "类型", "判定", "说明", "处理"]


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_table(text: str) -> tuple[list[str], list[dict]]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and "判定" in line and "处理" in line:
            headers = split_row(line)
            rows: list[dict] = []
            for row_line in lines[i + 1:]:
                if not row_line.strip().startswith("|"):
                    break
                cells = split_row(row_line)
                if not cells or all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    continue
                if len(cells) < len(headers):
                    cells += [""] * (len(headers) - len(cells))
                rows.append(dict(zip(headers, cells)))
            return headers, rows
    return [], []


def deck_ext_pages(slides: Path) -> set[int]:
    if not slides.exists():
        return set()
    text = slides.read_text(encoding="utf-8")
    parts = text.split("\n---\n")
    if parts and parts[0].lstrip().startswith("---"):
        parts = parts[1:]
    return {i + 1 for i, p in enumerate(parts) if 'class="src ext' in p}


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 fact-check.md")
    ap.add_argument("path", type=Path)
    ap.add_argument("--enrichment", type=Path)
    ap.add_argument("--slides", type=Path)
    ap.add_argument("--min-rows", type=int, default=20)
    args = ap.parse_args()

    if not args.path.exists():
        print(f"FAIL 文件不存在：{args.path}")
        return 2

    text = args.path.read_text(encoding="utf-8")
    headers, rows = parse_table(text)
    errors: list[str] = []
    warnings: list[str] = []

    if not headers:
        print("FAIL 找不到核查表（需要 | ID | 位置 | 主张 | 类型 | 判定 | 说明 | 处理 |）")
        return 1
    missing_headers = [h for h in REQUIRED_HEADERS if h not in headers]
    if missing_headers:
        errors.append(f"表头缺列：{', '.join(missing_headers)}")
    if len(rows) < args.min_rows:
        errors.append(f"核查行数 {len(rows)} < 下限 {args.min_rows}")

    for idx, row in enumerate(rows, start=1):
        verdict = (row.get("判定") or "").strip().upper()
        if verdict not in VERDICTS and verdict:
            errors.append(f"第 {idx} 行判定非法：{verdict}")
        treatment = (row.get("处理") or "").strip()
        if verdict == "ERROR":
            if not treatment or any(k in treatment for k in ("待处理", "TODO", "未处理", "待定")):
                errors.append(f"第 {idx} 行 ERROR 未处理：{row.get('主张', '')[:30]}")
        if verdict == "CONTESTED" and treatment and not any(
            k in treatment for k in ("标注", "加注", "限定", "说明", "有争议")
        ):
            errors.append(f"第 {idx} 行 CONTESTED 未标注争议：{row.get('主张', '')[:30]}")
        if verdict == "WEAK" and not treatment:
            warnings.append(f"第 {idx} 行 WEAK 无处理说明")

    body = "\n".join(" ".join(r.values()) for r in rows)

    if args.enrichment and args.enrichment.exists():
        cards = CARD_RE.findall(args.enrichment.read_text(encoding="utf-8"))
        missing = [c for c in cards if c not in body]
        if missing:
            errors.append(f"未核查的深挖卡：{', '.join(missing)}")

    if args.slides:
        if not args.slides.exists():
            errors.append(f"--slides 路径不存在：{args.slides}（不会跳过页面覆盖检查）")
        else:
            pages = deck_ext_pages(args.slides)
            missing_pages = sorted(p for p in pages if not re.search(rf"\bp{p}\b", body))
            if missing_pages:
                errors.append(f"未核查的扩展页：{', '.join(f'p{p}' for p in missing_pages)}")

    scan_text = args.path.read_text(encoding="utf-8")
    for i, line in enumerate(scan_text.splitlines(), start=1):
        if ABSOLUTE_RE.search(line) and line.strip().startswith("|"):
            warnings.append(f"第 {i} 行含绝对化措辞，人工确认：{line.strip()[:80]}")

    print(f"核查行数：{len(rows)}")
    for w in warnings:
        print(f"WARN {w}")
    if errors:
        for e in errors:
            print(f"FAIL {e}")
        print(f"OVERALL FAIL ({len(errors)} 项)")
        return 1
    print("OVERALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())