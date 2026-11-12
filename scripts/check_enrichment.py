#!/usr/bin/env python3
"""校验 S4.5 知识深挖稿 enrichment.md 的结构与来源标注。

用法:
    python scripts/check_enrichment.py work/<slug>/enrichment.md [--min-cards 12]

每张卡片以 `### E01 标题` 开头，必须包含以下字段：
    对应视频 / 一句话 / 原理 / 例 / 易错 / 迁移 / 来源
`来源` 必须出现 〔视频〕、〔推演〕、〔扩展〕 之一；含时间戳的卡片必须带 `[mm:ss]`。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CARD_RE = re.compile(r"^###\s+E\d{2}\s+(.+)$", re.MULTILINE)
FIELD_RE = re.compile(r"^[-*]\s*\*\*(对应视频|一句话|原理|例|易错|迁移|来源)\*\*[：:]\s*(.+)$", re.MULTILINE)
TS_RE = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]")
BADGE_RE = re.compile(r"〔(视频|推演|扩展)[^〕]*〕")

REQUIRED = ["对应视频", "一句话", "原理", "例", "易错", "迁移", "来源"]


def parse_cards(text: str) -> list[dict]:
    matches = list(CARD_RE.finditer(text))
    cards = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        fields = {k: v.strip() for k, v in FIELD_RE.findall(body)}
        cards.append({"title": m.group(1).strip(), "body": body, "fields": fields})
    return cards


def check(path: Path, min_cards: int) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    cards = parse_cards(text)
    errors: list[str] = []
    warnings: list[str] = []

    if len(cards) < min_cards:
        errors.append(f"卡片数 {len(cards)} < 下限 {min_cards}")

    seen: set[str] = set()
    for card in cards:
        title = card["title"]
        if title in seen:
            errors.append(f"重复卡片标题：{title}")
        seen.add(title)
        f = card["fields"]
        missing = [k for k in REQUIRED if not f.get(k)]
        if missing:
            errors.append(f"E「{title}」缺字段：{', '.join(missing)}")
            continue
        if not BADGE_RE.search(f["来源"]):
            errors.append(f"E「{title}」来源未标 〔视频〕/〔推演〕/〔扩展〕")
        if f["对应视频"] != "无" and not TS_RE.search(f["对应视频"]):
            if "〔扩展〕" not in f["来源"]:
                errors.append(f"E「{title}」有视频字段但无 [mm:ss] 时间戳")
        if len(f["原理"]) < 30:
            warnings.append(f"E「{title}」原理偏短（{len(f['原理'])} 字）")
        if len(f["例"]) < 8:
            warnings.append(f"E「{title}」例子偏短")

    # 覆盖度：既要有讲者原意的推演，也要有视频外的扩展
    infer = sum(1 for c in cards if "〔推演〕" in c["fields"].get("来源", ""))
    ext = sum(1 for c in cards if "〔扩展〕" in c["fields"].get("来源", ""))
    video = sum(1 for c in cards if "〔视频〕" in c["fields"].get("来源", ""))
    if infer < 4:
        errors.append(f"〔推演〕卡片只有 {infer} 张，至少 4 张")
    if ext < 4:
        errors.append(f"〔扩展〕卡片只有 {ext} 张，至少 4 张")
    if video < 4:
        errors.append(f"〔视频〕卡片只有 {video} 张，至少 4 张")

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 enrichment.md")
    ap.add_argument("path", type=Path)
    ap.add_argument("--min-cards", type=int, default=12)
    args = ap.parse_args()

    if not args.path.exists():
        print(f"FAIL 文件不存在：{args.path}")
        return 2

    errors, warnings = check(args.path, args.min_cards)
    cards = parse_cards(args.path.read_text(encoding="utf-8"))
    print(f"卡片数：{len(cards)}")
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