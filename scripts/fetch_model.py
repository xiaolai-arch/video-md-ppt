#!/usr/bin/env python3
"""下载 faster-whisper 模型（镜像 + 断点续传）。

用法:
    python scripts/fetch_model.py large-v3
    python scripts/fetch_model.py small --endpoint https://hf-mirror.com

说明：hf-mirror 会 308 跳转到真实文件地址，Python urllib 默认不跟随 308，
因此这里统一调用 curl（Windows 10+ 自带），与手工下载行为一致。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ToolError, ensure_utf8_stdout  # noqa: E402

FILES = (
    "model.bin",
    "config.json",
    "preprocessor_config.json",  # large-v3 需要 128 mel，缺了会按 80 mel 报形状错误
    "tokenizer.json",
    "vocabulary.json",
    "vocabulary.txt",
)
CURL = "curl"


def _remote_size(url: str, timeout: int = 60) -> int | None:
    """用 0-0 字节的 Range 请求拿总大小，避免依赖 HEAD。"""
    proc = subprocess.run(
        [CURL, "-sL", "-r", "0-0", "-D", "-", "-o", os.devnull, url],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    match = re.search(r"(?i)content-range:\s*bytes\s+0-0/(\d+)", proc.stdout)
    if match:
        return int(match.group(1))
    statuses = re.findall(r"(?m)^HTTP/\S+\s+(\d{3})", proc.stdout)
    if statuses and int(statuses[-1]) >= 400:
        raise ToolError(f"HTTP {statuses[-1]}：{url}")
    # 服务器不支持 Range 时会直接返回 200 全文，此时 content-length 就是总大小
    lengths = re.findall(r"(?i)content-length:\s*(\d+)", proc.stdout)
    return int(lengths[-1]) if lengths else None


def _curl_download(url: str, dest: Path, resume: bool) -> None:
    cmd = [
        CURL, "-L", "--fail",
        "--retry", "8", "--retry-delay", "3", "--retry-connrefused",
        "--progress-bar", "-o", str(dest),
    ]
    if resume:
        cmd += ["-C", "-"]
    cmd.append(url)
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise ToolError(f"curl 退出码 {proc.returncode}：{dest.name}")


def _download(url: str, dest: Path, retries: int = 8) -> None:
    try:
        total = _remote_size(url)
    except (subprocess.SubprocessError, OSError) as exc:
        raise ToolError(f"无法访问 {url}：{exc}") from exc

    existing = dest.stat().st_size if dest.exists() else 0
    if total is not None and existing >= total:
        print(f"  跳过（已完整）：{dest.name} {existing / 1e6:.1f} MB")
        return
    if existing:
        print(f"  续传：已有 {existing / 1e6:.1f} MB / {total / 1e6 if total else '?'} MB")

    for attempt in range(1, retries + 1):
        resume = total is not None and (dest.stat().st_size if dest.exists() else 0) > 0
        try:
            _curl_download(url, dest, resume)
        except ToolError as exc:
            if "退出码 22" in str(exc):  # HTTP 4xx/5xx，重试无意义
                raise
            print(f"  中断（第 {attempt}/{retries} 次）：{exc}")
            time.sleep(min(30, 3 * attempt))
            continue
        size = dest.stat().st_size if dest.exists() else 0
        if total is None or size >= total:
            print(f"  完成：{dest.name}（{size / 1e6:.1f} MB）")
            return
        print(f"  未完成：{size / 1e6:.1f}/{total / 1e6:.1f} MB，继续")
    raise ToolError(f"下载失败：{dest.name}（已尝试 {retries} 次，可重跑续传）")


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="下载 faster-whisper 模型")
    parser.add_argument("model", help="如 large-v3 / small，或完整 repo（Systran/faster-whisper-large-v3）")
    parser.add_argument("--endpoint", default=os.environ.get("HF_ENDPOINT", "https://hf-mirror.com"))
    parser.add_argument("--out", default=None, help="输出目录，默认 models/<repo 名>")
    args = parser.parse_args(argv)

    repo = args.model if "/" in args.model else f"Systran/faster-whisper-{args.model}"
    name = repo.rsplit("/", 1)[-1]
    out = Path(args.out) if args.out else Path(__file__).resolve().parent.parent / "models" / name
    out.mkdir(parents=True, exist_ok=True)
    print(f"仓库：{repo}\n目录：{out}\n镜像：{args.endpoint}")

    try:
        vocab_done = False
        for filename in FILES:
            if filename.startswith("vocabulary"):
                if vocab_done:
                    continue
            url = f"{args.endpoint.rstrip('/')}/{repo}/resolve/main/{filename}"
            print(f"下载 {filename} …")
            try:
                _download(url, out / filename)
                if filename.startswith("vocabulary"):
                    vocab_done = True
            except ToolError:
                if filename.startswith("vocabulary"):
                    print(f"  跳过（不存在）：{filename}")
                    continue
                raise
        print("模型就绪。用法：python scripts/transcribe.py <视频> --model", out)
        return 0
    except ToolError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
