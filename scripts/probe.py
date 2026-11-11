#!/usr/bin/env python3
"""S0 预处理：探查视频元信息，抽取 16kHz 单声道音频。

用法:
    python scripts/probe.py videos/第3讲.mp4 [--force] [--slug 自定义名]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    Meta,
    ToolError,
    cfg,
    ensure_utf8_stdout,
    ffprobe,
    fmt_duration,
    load_config,
    make_slug,
    path_cfg,
    resolve_tool,
    run,
    summarize_probe,
)


def _peak_db(ffmpeg: str, audio: Path, log_path: Path) -> float | None:
    """检测音轨峰值，用于发现"有音轨但几乎无声"的情况。"""
    try:
        proc = run(
            [ffmpeg, "-hide_banner", "-nostdin", "-i", str(audio), "-af", "volumedetect", "-f", "null", "-"],
            log_path=log_path,
        )
    except ToolError:
        return None
    text = (proc.stderr or "") + (proc.stdout or "")
    match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", text)
    return float(match.group(1)) if match else None


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="S0 预处理：探测视频并抽取转写用音频")
    parser.add_argument("video", help="本地视频文件（mp4/mkv/mov/avi/flv/webm）")
    parser.add_argument("--config", default=None, help="配置文件路径，默认 ./config.toml")
    parser.add_argument("--force", action="store_true", help="S0 已完成时强制重跑")
    parser.add_argument("--slug", default=None, help="手动指定工作目录名")
    args = parser.parse_args(argv)

    meta: Meta | None = None
    try:
        conf = load_config(args.config)
        ffmpeg = resolve_tool(str(cfg(conf, "paths.ffmpeg", "ffmpeg")), "请安装 ffmpeg 或修改 config.toml")
        ffprobe_bin = resolve_tool(
            str(cfg(conf, "paths.ffprobe", "ffprobe")), "请安装 ffmpeg（含 ffprobe）"
        )

        src = Path(args.video).expanduser().resolve()
        if not src.exists():
            raise ToolError(f"视频不存在：{src}")
        if not src.is_file():
            raise ToolError(f"不是文件：{src}")

        slug = args.slug or make_slug(src)
        work_dir = path_cfg(conf, "paths.work", "work") / slug
        work_dir.mkdir(parents=True, exist_ok=True)
        audio_path = work_dir / "audio" / "audio.wav"

        meta = Meta(work_dir / "meta.json")
        if meta.is_done("s0") and not args.force:
            print(f"S0 已完成，跳过：{slug}")
            print(f"音频：{audio_path}")
            return 0

        meta.mark_running("s0")

        print(f"探测：{src.name}")
        info = summarize_probe(ffprobe(ffprobe_bin, src))
        meta.data["slug"] = slug
        meta.data["source"] = {"path": str(src), "name": src.name, "bytes": src.stat().st_size}
        meta.data["probe"] = info
        meta.save()

        if not info["has_audio"]:
            meta.mark_failed("s0", "视频没有音轨")
            raise ToolError(
                "视频没有音轨，无法转写。当前流水线依赖语音；纯演示/无声视频暂不支持（见需求文档 §13）。"
            )

        duration = info["duration_s"]
        print(f"  时长：{fmt_duration(duration)}   容器：{info['format']}")
        vinfo = info.get("video") or {}
        if vinfo:
            print(f"  画面：{vinfo.get('width')}x{vinfo.get('height')} @ {vinfo.get('fps')}fps  {vinfo.get('codec')}")
        ainfo = info.get("audio") or {}
        print(f"  音轨：{ainfo.get('codec')}  {ainfo.get('channels')}ch  {ainfo.get('sample_rate')}Hz")
        if duration and duration > 7200:
            print("  提醒：视频超过 2 小时，转写与大纲将分块处理，耗时较长。")

        print("抽取音频（16kHz / 单声道 / 16bit）…")
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                ffmpeg,
                "-y",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(src),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-sample_fmt",
                "s16",
                "-c:a",
                "pcm_s16le",
                str(audio_path),
            ],
            log_path=work_dir / "logs" / "s0-extract.log",
        )
        if not audio_path.exists() or audio_path.stat().st_size < 1024:
            raise ToolError("音频抽取失败：输出文件为空")

        peak = _peak_db(ffmpeg, audio_path, work_dir / "logs" / "s0-volume.log")
        if peak is not None and peak <= -50.0:
            print(f"  警告：音轨峰值仅 {peak:.1f} dB，可能几乎无声，请先人工确认音轨。")
        elif peak is not None:
            print(f"  音频峰值：{peak:.1f} dB")

        meta.mark_done(
            "s0",
            outputs=[audio_path],
            params={"audio": "wav/16k/mono/s16", "duration_s": duration, "peak_db": peak},
            base_dir=work_dir,
        )

        print(f"完成：{slug}")
        print(f"  工作区：{work_dir}")
        print(f"  音频：{audio_path}（{audio_path.stat().st_size / 1e6:.1f} MB）")
        print("下一步：S1 转写（M1 实现）")
        return 0

    except ToolError as exc:
        if meta is not None and meta.status("s0") == "running":
            meta.mark_failed("s0", str(exc))
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
