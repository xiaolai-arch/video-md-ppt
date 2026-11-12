#!/usr/bin/env python3
"""环境自检：确认 M0 能跑，并列出 M1 还缺什么。

用法:
    python scripts/doctor.py
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    ToolError,
    cfg,
    ensure_utf8_stdout,
    load_config,
    path_cfg,
    prepare_cuda_dlls,
    resolve_tool,
    run,
)


def main() -> int:
    ensure_utf8_stdout()
    fails = 0

    def line(level: str, text: str) -> None:
        nonlocal fails
        if level == "fail":
            fails += 1
        print(f"[{level:4}] {text}")

    # Python
    version = sys.version_info
    line("ok" if version >= (3, 10) else "fail", f"Python {version.major}.{version.minor}.{version.micro}")

    # 配置
    conf: dict | None = None
    try:
        conf = load_config()
        line("ok", f"config.toml 可解析（{len(conf)} 个配置节）")
    except ToolError as exc:
        line("fail", str(exc))

    # ffmpeg / ffprobe
    for key, name in (("paths.ffmpeg", "ffmpeg"), ("paths.ffprobe", "ffprobe")):
        value = str(cfg(conf, key, name)) if conf else name
        try:
            binary = resolve_tool(value, "请安装 ffmpeg 并加入 PATH")
            first = (run([binary, "-version"]).stdout or "").splitlines()
            line("ok", first[0] if first else f"{name} 可用")
        except ToolError as exc:
            line("fail", str(exc))

    # 目录可写
    if conf:
        for key, default in (("paths.videos", "videos"), ("paths.work", "work"), ("paths.output", "output")):
            directory = path_cfg(conf, key, default)
            try:
                directory.mkdir(parents=True, exist_ok=True)
                probe_file = directory / ".write_test"
                probe_file.write_text("ok", encoding="utf-8")
                probe_file.unlink()
                line("ok", f"目录可写：{directory}")
            except OSError as exc:
                line("fail", f"目录不可写：{directory}（{exc}）")

    # M1 依赖（faster-whisper 基于 ctranslate2，不需要 torch）
    whisper_ok = importlib.util.find_spec("faster_whisper") is not None
    if whisper_ok:
        line("ok", "faster-whisper（S1 转写）已安装")
    else:
        line("info", "faster-whisper 未安装：python -m pip install -r requirements.txt")

    # GPU
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            for row in proc.stdout.strip().splitlines():
                line("ok", f"GPU：{row}")
            cuda_ok, cuda_detail = prepare_cuda_dlls()
            if cuda_ok:
                line("ok", f"CUDA 运行库：{cuda_detail}")
            else:
                line("warn", f"CUDA 运行库不可用（{cuda_detail}），转写将回退 CPU")
        else:
            line("info", "未检测到 NVIDIA GPU（将回退 CPU 转写）")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        line("info", "未检测到 nvidia-smi（将回退 CPU 转写）")

    print()
    if fails:
        print(f"有 {fails} 项需要处理。")
        return 1
    print("依赖就绪。RUN：python scripts/transcribe.py videos/<你的视频>（首次会自动下载模型）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
