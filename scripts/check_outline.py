#!/usr/bin/env python3
"""S3 门禁：确定性检查 outline.md 的时间结构与覆盖率。

用法:
    python scripts/check_outline.py work/<slug>/outline.md [--slug <slug>] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    ROOT,
    ToolError,
    ensure_utf8_stdout,
    fmt_duration,
    load_config,
    path_cfg,
)

RANGE_RE = re.compile(
    r"\[\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*[–\-—~至]\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*\]"
)
INLINE_TIME_RE = re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]")


def parse_time(text: str) -> float:
    parts = [int(p) for p in text.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"无法解析时间：{text}")


def load_duration(args, conf) -> float | None:
    if args.duration:
        return float(args.duration)
    work_root = path_cfg(conf, "paths.work", "work")
    candidates = []
    if args.slug:
        candidates.append(work_root / args.slug / "meta.json")
    candidates.append(ROOT / "work" / args.slug / "meta.json" if args.slug else None)
    # 优先从 outline 同级的 meta.json 推断
    outline = Path(args.outline)
    candidates.insert(0, outline.parent / "meta.json")
    for meta_path in candidates:
        if meta_path and meta_path.exists():
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            duration = (data.get("probe") or {}).get("duration_s")
            if duration:
                return float(duration)
    return None


def parse_chapters(text: str) -> list[dict]:
    lines = text.splitlines()
    chapters: list[dict] = []
    current: dict | None = None
    for i, line in enumerate(lines):
        if line.startswith("## "):
            title = line[3:].strip()
            window = "\n".join(lines[i : i + 3])
            match = RANGE_RE.search(window)
            current = {"title": title, "start": None, "end": None, "body": [], "line": i + 1}
            if match:
                current["start"] = parse_time(match.group(1))
                current["end"] = parse_time(match.group(2))
            chapters.append(current)
        elif current is not None:
            current["body"].append(line)
    return chapters


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="S3 门禁：大纲时间结构检查")
    parser.add_argument("outline", help="outline.md 路径")
    parser.add_argument("--slug", default=None)
    parser.add_argument("--duration", type=float, default=None, help="视频时长（秒），覆盖自动检测")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    fails: list[str] = []
    warns: list[str] = []
    infos: list[str] = []

    try:
        conf = load_config()
        path = Path(args.outline)
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if not path.exists():
            raise ToolError(f"找不到大纲：{path}")

        text = path.read_text(encoding="utf-8")
        chapters = parse_chapters(text)
        duration = load_duration(args, conf)

        if not chapters:
            fails.append("没有找到 `## ` 章节标题")
        if duration is None:
            warns.append("未能读取视频时长，覆盖率与越界检查跳过")

        numbered = [c for c in chapters if c["start"] is not None]
        if len(numbered) != len(chapters):
            missing = [f"第 {c['line']} 行「{c['title']}」" for c in chapters if c["start"] is None]
            fails.append("以下章节缺少 [起–止] 时间范围：" + "；".join(missing))

        for c in numbered:
            if c["end"] <= c["start"]:
                fails.append(f"「{c['title']}」结束时间不晚于开始时间")
            if duration and c["end"] > duration + 5:
                fails.append(
                    f"「{c['title']}」超出视频时长（{fmt_duration(c['end'])} > {fmt_duration(duration)}）"
                )
            if not INLINE_TIME_RE.search("\n".join(c["body"])):
                warns.append(f"「{c['title']}」正文没有可点击的 [mm:ss] 引用")

        ordered = sorted(numbered, key=lambda c: c["start"])
        for prev, cur in zip(ordered, ordered[1:]):
            if cur["start"] < prev["start"] - 1:
                fails.append(f"章节乱序：「{cur['title']}」早于「{prev['title']}」")
            overlap = prev["end"] - cur["start"]
            if overlap > 5:
                fails.append(
                    f"章节重叠 {overlap:.0f}s：「{prev['title']}」与「{cur['title']}」"
                )
            gap = cur["start"] - prev["end"]
            if gap > 60:
                warns.append(f"时间空洞 {gap:.0f}s：{prev['title']} → {cur['title']}")

        if duration and ordered:
            merged: list[list[float]] = []
            for c in ordered:
                if merged and c["start"] <= merged[-1][1] + 5:
                    merged[-1][1] = max(merged[-1][1], c["end"])
                else:
                    merged.append([c["start"], c["end"]])
            covered = sum(end - start for start, end in merged)
            ratio = covered / duration
            if ratio < 0.95:
                fails.append(f"时间覆盖率 {ratio:.1%} < 95%")
            else:
                infos.append(f"时间覆盖率 {ratio:.1%}")

        low = text.count("低置信")
        if low:
            infos.append(f"标记了 {low} 处低置信度，需人工确认")

        status = "FAIL" if fails else "PASS"
        result = {
            "status": status,
            "chapters": len(chapters),
            "duration_s": duration,
            "fails": fails,
            "warns": warns,
            "infos": infos,
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            for item in infos:
                print(f"[info] {item}")
            for item in warns:
                print(f"[warn] {item}")
            for item in fails:
                print(f"[fail] {item}")
            print(f"OVERALL {status}")
        return 0 if status == "PASS" else 1

    except ToolError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
