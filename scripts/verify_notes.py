#!/usr/bin/env python3
"""S4 门禁：确定性检查 notes.md 的时间戳、图片、术语与空话。

用法:
    python scripts/verify_notes.py output/<slug>/notes.md [--slug <slug>] [--json]
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
TIME_RE = re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
HTML_IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)

NON_CHAPTER = ("目录", "速览", "TL;DR", "术语表", "待确认", "延伸", "附录")
FORBIDDEN = ("根据视频内容", "本视频介绍", "视频中提到", "综上所述，本视频")


def parse_time(text: str) -> float:
    parts = [int(p) for p in text.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(text)


def read_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    data: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip().strip("\"'")
    return data


def split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = ""
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((current_title, "\n".join(buf)))
            current_title = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    sections.append((current_title, "\n".join(buf)))
    return sections


def resolve_paths(args, conf) -> tuple[Path, Path | None]:
    target = Path(args.target)
    if target.suffix.lower() == ".md":
        notes = target if target.is_absolute() else (ROOT / target)
    else:
        output_root = path_cfg(conf, "paths.output", "output")
        notes = output_root / args.target / "notes.md"
    notes = notes.resolve()
    slug = args.slug or notes.parent.name
    work_root = path_cfg(conf, "paths.work", "work")
    transcript = args.transcript or (work_root / slug / "transcript" / "transcript.txt")
    transcript_path = Path(transcript)
    if not transcript_path.is_absolute():
        transcript_path = ROOT / transcript_path
    return notes, transcript_path if transcript_path.exists() else None


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="S4 门禁：笔记检查")
    parser.add_argument("target", help="notes.md 路径或 slug")
    parser.add_argument("--slug", default=None)
    parser.add_argument("--transcript", default=None, help="转写文本路径")
    parser.add_argument("--duration", type=float, default=None, help="视频时长（秒）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    fails: list[str] = []
    warns: list[str] = []
    infos: list[str] = []

    try:
        conf = load_config()
        notes, transcript = resolve_paths(args, conf)
        if not notes.exists():
            raise ToolError(f"找不到笔记：{notes}")
        text = notes.read_text(encoding="utf-8")

        # 时长
        duration = args.duration
        if duration is None:
            slug_for_meta = args.slug or notes.parent.name
            meta_path = path_cfg(conf, "paths.work", "work") / slug_for_meta / "meta.json"
            if meta_path.exists():
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                duration = (data.get("probe") or {}).get("duration_s")
        duration = float(duration) if duration else None

        # frontmatter
        fm = read_frontmatter(text)
        for key in ("title", "duration"):
            if key not in fm:
                warns.append(f"frontmatter 缺少 `{key}`")

        # 章节与时间范围
        sections = split_sections(text)
        if not sections:
            fails.append("没有 `##` 章节")
        chapters: list[dict] = []
        for title, body in sections:
            if not title or any(title.startswith(x) for x in NON_CHAPTER):
                continue
            match = RANGE_RE.search(title + "\n" + body[:200])
            if match:
                chapters.append(
                    {
                        "title": title,
                        "start": parse_time(match.group(1)),
                        "end": parse_time(match.group(2)),
                    }
                )
            else:
                warns.append(f"章节「{title}」缺少 [起–止] 时间范围")

        if not chapters:
            fails.append("没有任何带时间范围的正文章节")

        # 时间戳越界与覆盖率
        all_times = [parse_time(t) for t in TIME_RE.findall(text)]
        all_times += [parse_time(t) for t in RANGE_RE.findall(text) for t in t]
        if duration:
            outside = [t for t in all_times if t > duration + 5]
            if outside:
                fails.append(
                    f"{len(outside)} 个时间戳超出视频时长（最晚 {fmt_duration(max(outside))}）"
                )
            covered = 0.0
            ordered = sorted(chapters, key=lambda c: c["start"])
            for prev, cur in zip(ordered, ordered[1:]):
                if cur["start"] < prev["end"] - 5:
                    fails.append(f"章节时间重叠：「{prev['title']}」与「{cur['title']}」")
            for c in chapters:
                if c["end"] > c["start"]:
                    covered += c["end"] - c["start"]
            ratio = min(covered, duration) / duration
            if ratio < 0.95:
                fails.append(f"章节时间覆盖率 {ratio:.1%} < 95%")

        # 图片
        images = IMAGE_RE.findall(text) + HTML_IMG_RE.findall(text)
        for src in images:
            if src.startswith(("http://", "https://")):
                fails.append(f"图片使用了外链：{src}")
                continue
            path = (notes.parent / src).resolve()
            if not path.exists():
                fails.append(f"图片不存在：{src}")

        # 术语表
        glossary_terms: list[str] = []
        for title, body in sections:
            if "术语表" not in title:
                continue
            for line in body.splitlines():
                if not line.strip().startswith("|"):
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if not cells:
                    continue
                term = cells[0]
                if set(term) <= {"-", ":", " "} or term in ("术语", "Term"):
                    continue
                if term:
                    glossary_terms.append(term)
        body_text = "\n".join(
            body for title, body in sections if "术语表" not in title
        )
        for term in glossary_terms:
            if term and term not in body_text:
                warns.append(f"术语表条目未在正文出现：{term}")

        # 空话
        for phrase in FORBIDDEN:
            if phrase in text:
                fails.append(f"出现空话/过程性表述：{phrase}")

        # 数字可回溯
        if transcript:
            transcript_text = transcript.read_text(encoding="utf-8")
            numbers = set(re.findall(r"\d+(?:\.\d+)?%", text))
            numbers |= set(re.findall(r"\d+(?:\.\d+)?(?:分|分钟|小时|个|种|篇|倍|年|天)", text))
            missing = sorted(n for n in numbers if n not in transcript_text)
            for item in missing[:10]:
                warns.append(f"数字在转写中找不到原值：{item}")

        # 篇幅
        cjk = len(re.findall(r"[一-鿿]", text))
        if duration:
            per_10min = cjk / (duration / 600)
            infos.append(f"正文汉字 {cjk}，每 10 分钟约 {per_10min:.0f} 字")
            if per_10min < 250:
                warns.append("篇幅偏短：可能提炼过度或漏内容")
            elif per_10min > 1100:
                warns.append("篇幅偏长：可能没有提炼")

        if not images:
            warns.append("没有任何图片引用")

        status = "FAIL" if fails else "PASS"
        result = {
            "status": status,
            "notes": str(notes),
            "duration_s": duration,
            "chapters": len(chapters),
            "images": len(images),
            "cjk": cjk if duration else None,
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
