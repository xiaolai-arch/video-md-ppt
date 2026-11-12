#!/usr/bin/env python3
"""扫描 output/ 生成课时总索引。

用法:
    python scripts/build_index.py

产物:
    output/index.html   离线总索引，链接到每集的笔记 / HTML / PDF / 报告
    output/README.md    同样的信息，Markdown 表格，便于 agent 与文本检索
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"


def human_duration(seconds: float | None) -> str:
    if not seconds:
        return "—"
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def notes_title(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else path.parent.name


def duration_of(slug: str, notes: Path) -> float | None:
    meta = ROOT / "work" / slug / "meta.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            return data["stages"]["s0"]["params"]["duration_s"]
        except (KeyError, ValueError):
            pass
    if notes.exists():
        m = re.search(r"^duration:\s*(\d+):(\d+)(?::(\d+))?", notes.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            parts = [int(x) for x in m.groups() if x]
            return parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


def slide_pages(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8").strip()
    parts = [p for p in text.split("\n---\n") if p.strip()]
    if parts and parts[0].lstrip().startswith("---"):
        parts = parts[1:]
    return len(parts)


def deep_pages(report: Path) -> int | None:
    if not report.exists():
        return None
    text = report.read_text(encoding="utf-8")
    m = re.search(r"深挖页[^0-9\n]{0,24}(\d+)\s*页", text)
    if not m:
        m = re.search(r"深挖页[：:]\s*(\d+)\s*/", text)
    return int(m.group(1)) if m else None


def fmt_date(path: Path) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def collect() -> list[dict]:
    rows = []
    for d in sorted(p for p in OUT.iterdir() if p.is_dir()):
        m = re.match(r"(\d+)_(.+)_([0-9a-f]{8})$", d.name)
        if not m:
            continue
        num, slug_title, _ = m.groups()
        notes = d / "notes.md"
        report = d / "report.md"
        slides_md = d / "slides" / "slides.md"
        title = notes_title(notes) if notes.exists() else slug_title.replace("_", " ")
        rows.append(
            {
                "num": num,
                "dir": d.name,
                "title": title,
                "duration": duration_of(d.name, notes),
                "pages": slide_pages(slides_md),
                "deep": deep_pages(report),
                "date": fmt_date(report if report.exists() else d),
                "notes": notes.exists(),
                "html": (d / "slides" / "index.html").exists(),
                "pdf": (d / "slides" / "slides.pdf").exists(),
                "report": report.exists(),
            }
        )
    return rows


def build_html(rows: list[dict]) -> str:
    cards = []
    for r in rows:
        deep = f"{r['deep']} 页深挖 / {r['pages']} 页" if r["deep"] and r["pages"] else f"{r['pages']} 页"
        links = []
        if r["notes"]:
            links.append(f'<a href="{r["dir"]}/notes.md">笔记</a>')
        if r["html"]:
            links.append(f'<a href="{r["dir"]}/slides/index.html">课件 HTML</a>')
        if r["pdf"]:
            links.append(f'<a href="{r["dir"]}/slides/slides.pdf">课件 PDF</a>')
        if r["report"]:
            links.append(f'<a href="{r["dir"]}/report.md">交付报告</a>')
        cards.append(
            f"""    <li class="card">
      <div class="num">{html.escape(r["num"])}</div>
      <div class="body">
        <h2>{html.escape(r["title"])}</h2>
        <p class="meta">{html.escape(r["duration"] and human_duration(r["duration"]) or "—")} · {html.escape(deep)} · {r["date"]}</p>
        <p class="links">{"".join(links)}</p>
      </div>
    </li>"""
        )
    total_min = sum((r["duration"] or 0) for r in rows) / 60
    total_pages = sum(r["pages"] for r in rows)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>四级课程课件索引</title>
<style>
  :root {{
    --bg: #f6f4ee; --surface: #fffdf8; --ink: #1d2a26; --muted: #5d6b64;
    --line: #ddd8cb; --accent: #1f6f5c; --accent-soft: #e3eee9;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #141a18; --surface: #1c2522; --ink: #e9efe9; --muted: #9fb0a8;
      --line: #2e3b36; --accent: #74c3a8; --accent-soft: #22352e;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 16px 64px; background: var(--bg); color: var(--ink);
    font-family: "Noto Sans SC", "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
    line-height: 1.6;
  }}
  .wrap {{ max-width: 980px; margin: 0 auto; }}
  header h1 {{ margin: 0 0 6px; font-size: 30px; letter-spacing: .02em; }}
  header p {{ margin: 0; color: var(--muted); }}
  .summary {{ margin: 20px 0 28px; padding: 14px 18px; background: var(--accent-soft);
    border-radius: 10px; color: var(--ink); font-size: 15px; }}
  ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }}
  .card {{
    display: grid; grid-template-columns: 56px 1fr; gap: 16px; align-items: start;
    background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
    padding: 16px 18px;
  }}
  .num {{ font-size: 22px; font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; }}
  .card h2 {{ margin: 0 0 6px; font-size: 18px; line-height: 1.4; }}
  .meta {{ margin: 0 0 10px; color: var(--muted); font-size: 13.5px; font-variant-numeric: tabular-nums; }}
  .links {{ margin: 0; display: flex; flex-wrap: wrap; gap: 8px 14px; font-size: 14px; }}
  .links a {{ color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; }}
  .links a:hover {{ border-color: var(--accent); }}
  footer {{ margin-top: 28px; color: var(--muted); font-size: 13px; }}
  @media (max-width: 560px) {{
    header h1 {{ font-size: 24px; }}
    .card {{ grid-template-columns: 40px 1fr; padding: 14px; }}
    .num {{ font-size: 18px; }}
    .card h2 {{ font-size: 16px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>四级课程课件索引</h1>
    <p>视频 → 带时间戳的 Markdown 笔记 → 离线 HTML / PDF 课件</p>
  </header>
  <p class="summary">{len(rows)} 集 · 视频共 {total_min:.0f} 分钟 · 课件共 {total_pages} 页。门禁结果见各集 <code>report.md</code>；点击链接直接打开本地文件。</p>
  <ul>
{chr(10).join(cards)}
  </ul>
  <footer>由 <code>scripts/build_index.py</code> 生成。索引不内嵌课件，链接指向同目录下的文件。
    交付范围与已知局限见 <a href="课程说明.md">课程交付说明</a>。</footer>
</div>
</body>
</html>
"""


def build_markdown(rows: list[dict]) -> str:
    lines = [
        "# 课时总索引",
        "",
        "由 `scripts/build_index.py` 生成。",
        "",
        "| # | 课时 | 时长 | 页数 | 深挖页 | 笔记 | 课件 | 报告 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        links = []
        links.append(f"[notes]({r['dir']}/notes.md)" if r["notes"] else "—")
        links.append(f"[HTML]({r['dir']}/slides/index.html)" if r["html"] else "—")
        links.append(f"[PDF]({r['dir']}/slides/slides.pdf)" if r["pdf"] else "—")
        links.append(f"[report]({r['dir']}/report.md)" if r["report"] else "—")
        lines.append(
            f"| {r['num']} | {r['title']} | {human_duration(r['duration'])} | {r['pages'] or '—'} | "
            f"{r['deep'] or '—'} | {links[0]} | {links[1]} / {links[2]} | {links[3]} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    rows = collect()
    if not rows:
        print("output/ 下没有找到课时目录")
        return 1
    (OUT / "index.html").write_text(build_html(rows), encoding="utf-8")
    (OUT / "README.md").write_text(build_markdown(rows), encoding="utf-8")
    print(f"生成 {OUT / 'index.html'}（{len(rows)} 集）")
    for r in rows:
        print(f"  {r['num']}  {r['pages']:>3} 页  {r['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
