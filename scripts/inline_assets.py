#!/usr/bin/env python3
"""把 Marp 输出 HTML 中的本地图片内联为 data URI，得到真正可离线分发的单文件。

用法:
    python scripts/inline_assets.py output/<slug>/slides/index.html
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ToolError, ensure_utf8_stdout  # noqa: E402

SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=)(["\'])([^"\']+)\2', re.IGNORECASE)


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="内联 HTML 中的本地图片")
    parser.add_argument("html", help="待处理的 HTML")
    args = parser.parse_args(argv)

    path = Path(args.html)
    if not path.is_absolute():
        from common import ROOT

        path = (ROOT / path).resolve()
    if not path.exists():
        print(f"错误：找不到 {path}", file=sys.stderr)
        return 2

    try:
        html = path.read_text(encoding="utf-8")
        inlined = 0
        missing: list[str] = []

        def repl(match: re.Match[str]) -> str:
            nonlocal inlined
            src = match.group(3)
            if src.startswith(("data:", "http://", "https://", "#")):
                return match.group(0)
            file_path = (path.parent / src).resolve()
            if not file_path.is_file():
                missing.append(src)
                return match.group(0)
            mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            payload = base64.b64encode(file_path.read_bytes()).decode("ascii")
            inlined += 1
            return f"{match.group(1)}{match.group(2)}data:{mime};base64,{payload}{match.group(2)}"

        result = SRC_RE.sub(repl, html)
        if missing:
            raise ToolError("以下图片不存在：" + ", ".join(sorted(set(missing))))

        path.write_text(result, encoding="utf-8")
        size_kb = path.stat().st_size / 1024
        print(f"已内联 {inlined} 张图片，输出 {path}（{size_kb:.0f} KB）")

        # 自检：不应再有本地资源引用
        leftovers = [
            src
            for _, _, src in SRC_RE.findall(result)
            if not src.startswith(("data:", "http://", "https://", "#"))
        ]
        if leftovers:
            print(f"警告：仍有本地图片引用：{', '.join(leftovers)}", file=sys.stderr)
            return 1
        return 0
    except ToolError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
