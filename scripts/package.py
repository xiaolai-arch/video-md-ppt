#!/usr/bin/env python3
"""把交付物打成一个可分发的 zip。

用法:
    python scripts/package.py                 # 默认：全部课时
    python scripts/package.py --lessons 03 12 # 只打指定集
    python scripts/package.py --include-png   # 连同逐页自检图一起打包

默认只收交付所需文件：notes.md、notes.assets、slides/{slides.md,index.html,slides.pdf,theme.css}、
report.md，以及顶层总索引。自检 PNG 与 _legacy 旧版本不入包。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
DIST = ROOT / "dist"

LESSON_FILES = [
    "notes.md",
    "report.md",
    "slides/slides.md",
    "slides/index.html",
    "slides/slides.pdf",
    "slides/theme.css",
]


def lesson_dirs(lessons: list[str] | None) -> list[Path]:
    dirs = sorted(p for p in OUT.iterdir() if p.is_dir() and re.match(r"\d{2}_", p.name))
    if lessons:
        wanted = set(lessons)
        dirs = [p for p in dirs if p.name[:2] in wanted]
    return dirs


def checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="打包课程交付物")
    ap.add_argument("--lessons", nargs="*", help="只打指定集号，如 03 12")
    ap.add_argument("--include-png", action="store_true", help="连逐页自检图一起打包")
    ap.add_argument("--name", default=None, help="zip 文件名（不含路径）")
    args = ap.parse_args()

    dirs = lesson_dirs(args.lessons)
    if not dirs:
        print("没有找到课时目录")
        return 1

    # 指定集号时重新收集，避免把未指定课时混进来
    files: list[Path] = []
    for name in ("index.html", "README.md"):
        p = OUT / name
        if p.exists():
            files.append(p)
    for d in dirs:
        for rel in LESSON_FILES:
            p = d / rel
            if p.exists():
                files.append(p)
        assets = d / "notes.assets"
        if assets.exists():
            files.extend(sorted(p for p in assets.rglob("*") if p.is_file()))
        if args.include_png:
            files.extend(sorted((d / "slides").glob("selfcheck*")))

    DIST.mkdir(exist_ok=True)
    stamp = dt.date.today().isoformat()
    name = args.name or f"四级课件_{stamp}.zip"
    zip_path = DIST / name

    sums = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in files:
            arc = p.relative_to(OUT).as_posix()
            zf.write(p, arc)
            sums.append(f"{checksum(p)}  {arc}")
        zf.writestr("SHA256SUMS.txt", "\n".join(sums) + "\n")

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"已生成 {zip_path}")
    print(f"  {len(files)} 个文件，{size_mb:.1f} MB，{len(dirs)} 集")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
