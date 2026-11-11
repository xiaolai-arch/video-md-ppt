#!/usr/bin/env python3
"""S2 抽帧：scene + 间隔采样 → dHash 聚类 → 像素复核 → 停留过滤 → 预算裁剪。

用法:
    python scripts/keyframes.py <视频路径|slug> [--force] [--max-frames 80]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    Meta,
    ToolError,
    cfg,
    ensure_utf8_stdout,
    fmt_duration,
    load_config,
    path_cfg,
    resolve_tool,
    resolve_workspace,
    run,
)

CAND_WIDTH = 320


def _dhash(img) -> int:
    px = img.convert("L").resize((9, 8)).tobytes()
    bits = 0
    for row in range(8):
        base = row * 9
        for col in range(8):
            bits = (bits << 1) | (1 if px[base + col] > px[base + col + 1] else 0)
    return bits


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _signature(img) -> bytes:
    """32×32 RGB 原始字节，用于颜色 + 结构差异。纯色画面也能区分。"""
    return img.convert("RGB").resize((32, 32)).tobytes()


def _pixel_diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / (255.0 * max(1, len(a)))


def _sharpness(img) -> float:
    from PIL import ImageFilter, ImageStat

    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    return float(ImageStat.Stat(edges).var[0])


def _thin(items: list, max_count: int) -> list:
    if max_count <= 0 or len(items) <= max_count:
        return items
    if max_count == 1:
        return [items[len(items) // 2]]
    indexes = [round(i * (len(items) - 1) / (max_count - 1)) for i in range(max_count)]
    return [items[i] for i in indexes]


def _extract_candidates(ffmpeg: str, src: Path, cand_dir: Path, interval: float,
                        scene_threshold: float, log_path: Path) -> list[tuple[float, Path, str]]:
    if cand_dir.exists():
        shutil.rmtree(cand_dir)
    cand_dir.mkdir(parents=True, exist_ok=True)

    print(f"  采样 1/1：每 {interval:g}s 一帧…")
    proc_int = run(
        [ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "info",
         "-i", str(src),
         "-vf", f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,{interval:g})',showinfo,scale={CAND_WIDTH}:-2",
         "-fps_mode", "vfr", "-q:v", "4", str(cand_dir / "int_%05d.png")],
        log_path=log_path,
    )
    interval_files = sorted(cand_dir.glob("int_*.png"))
    interval_times = [
        float(x) for x in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", proc_int.stderr or "")
    ]
    candidates: list[tuple[float, Path, str]] = []
    for i, path in enumerate(interval_files):
        # fps 滤镜的输出 PTS 才是真实时间；解析失败才退回 i*interval
        t = interval_times[i] if i < len(interval_times) else i * interval
        candidates.append((t, path, "interval"))

    print(f"  采样 2/2：场景变化（阈值 {scene_threshold:g}）…")
    proc = run(
        [ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "info",
         "-i", str(src),
         "-vf", f"scale={CAND_WIDTH}:-2,select='gt(scene,{scene_threshold:g})',showinfo",
         "-fps_mode", "vfr", "-q:v", "4", str(cand_dir / "sc_%05d.png")],
        log_path=log_path,
    )
    times = [float(x) for x in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", proc.stderr or "")]
    scene_files = sorted(cand_dir.glob("sc_*.png"))
    for t, path in zip(times, scene_files):
        candidates.append((t, path, "scene"))
    return sorted(candidates, key=lambda item: item[0])


def _cluster(candidates: list[tuple[float, Path, str]], conf: dict) -> list[dict]:
    from PIL import Image

    hamming_thr = int(cfg(conf, "frames.phash_hamming", 6))
    diff_thr = float(cfg(conf, "frames.pixel_diff", 0.08))
    clusters: list[dict] = []
    current: dict | None = None
    rep_dhash = rep_sig = None

    for t, path, reason in candidates:
        try:
            with Image.open(path) as img:
                img = img.convert("RGB")
                dh = _dhash(img)
                sig = _signature(img)
                sharp = _sharpness(img)
        except Exception:
            continue

        same = (
            current is not None
            and rep_dhash is not None
            and rep_sig is not None
            and _hamming(dh, rep_dhash) <= hamming_thr
            and _pixel_diff(sig, rep_sig) <= diff_thr
        )
        if same:
            current["t_end"] = t
            current["count"] += 1
            if sharp > current["sharpness"]:
                current.update(sharpness=sharp, t=t, path=path, reason=reason,
                               dhash=f"{dh:016x}")
                rep_dhash, rep_sig = dh, sig
        else:
            current = {
                "t_start": t,
                "t_end": t,
                "t": t,
                "path": path,
                "reason": reason,
                "sharpness": sharp,
                "dhash": f"{dh:016x}",
                "count": 1,
            }
            clusters.append(current)
            rep_dhash, rep_sig = dh, sig
    return clusters


def _drop_transitions(clusters: list[dict], min_dwell: float) -> list[dict]:
    kept: list[dict] = []
    for i, cluster in enumerate(clusters):
        span = cluster["t_end"] - cluster["t_start"]
        near_prev = i > 0 and cluster["t_start"] - clusters[i - 1]["t_end"] < min_dwell
        near_next = i + 1 < len(clusters) and clusters[i + 1]["t_start"] - cluster["t_end"] < min_dwell
        if span < min_dwell and near_prev and near_next:
            continue
        kept.append(cluster)
    return kept


def _enforce_min_gap(clusters: list[dict], min_gap: float) -> list[dict]:
    """同一张幻灯片上的讲师走动会造成重复帧；用最小间隔压掉，场景切换帧豁免。"""
    kept: list[dict] = []
    for cluster in clusters:
        if not kept:
            kept.append(cluster)
            continue
        gap = cluster["t"] - kept[-1]["t"]
        if cluster.get("reason") == "scene" or gap >= min_gap:
            kept.append(cluster)
    return kept


def _budget(clusters: list[dict], per_10min: int, max_frames: int) -> list[dict]:
    buckets: dict[int, list[dict]] = {}
    for cluster in clusters:
        buckets.setdefault(int(cluster["t"] // 600), []).append(cluster)
    selected: list[dict] = []
    for key in sorted(buckets):
        selected.extend(_thin(buckets[key], per_10min))
    return _thin(selected, max_frames)


def _extract_final(ffmpeg: str, src: Path, frames_dir: Path, t: float,
                   width: int, quality: int, log_path: Path) -> Path:
    name = f"{int(round(t * 1000)):09d}.jpg"
    out = frames_dir / name
    run(
        [ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
         "-vf", f"scale={width}:-2", "-q:v", str(quality), str(out)],
        log_path=log_path,
    )
    if not out.exists() or out.stat().st_size < 1024:
        raise ToolError(f"帧提取失败：t={t:.1f}s")
    return out


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="S2 抽帧")
    parser.add_argument("target", help="视频路径或 slug")
    parser.add_argument("--config", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--interval", type=float, default=None)
    args = parser.parse_args(argv)

    meta: Meta | None = None
    try:
        try:
            from PIL import Image  # noqa: F401
        except ImportError as exc:
            raise ToolError("缺少 Pillow：python -m pip install Pillow") from exc

        conf = load_config(args.config)
        slug, work_dir, meta, src = resolve_workspace(args.target, conf)
        if meta is None or not meta.is_done("s0"):
            from probe import main as probe_main

            if probe_main([str(src)]) != 0:
                raise ToolError("S0 预处理失败，无法抽帧")
            meta = Meta(work_dir / "meta.json")

        if meta.is_done("s2") and not args.force:
            print(f"S2 已完成，跳过：{slug}")
            print(f"索引：{work_dir / 'frames' / 'index.json'}")
            return 0

        ffmpeg = resolve_tool(str(cfg(conf, "paths.ffmpeg", "ffmpeg")), "请安装 ffmpeg")
        interval = args.interval or float(cfg(conf, "frames.interval_seconds", 12))
        scene_thr = float(cfg(conf, "frames.scene_threshold", 0.3))
        max_frames = args.max_frames or int(cfg(conf, "frames.max_frames", 80))
        per_10min = int(cfg(conf, "frames.max_per_10min", 12))
        min_dwell = float(cfg(conf, "frames.min_dwell_seconds", 2))
        width = int(cfg(conf, "frames.width", 1280))
        quality = int(cfg(conf, "frames.quality", 3))
        duration = (meta.data.get("probe") or {}).get("duration_s")

        meta.mark_running("s2")
        started = time.time()
        log_path = work_dir / "logs" / "s2-keyframes.log"
        cand_dir = work_dir / "frames" / ".cand"
        frames_dir = work_dir / "frames"

        print(f"抽帧：{src.name}（{fmt_duration(duration)}）")
        candidates = _extract_candidates(ffmpeg, src, cand_dir, interval, scene_thr, log_path)
        print(f"  候选帧：{len(candidates)}")

        clusters = _cluster(candidates, conf)
        print(f"  聚类后：{len(clusters)}")

        clusters = _drop_transitions(clusters, min_dwell)
        print(f"  过滤转场帧：{len(clusters)}")

        selected = _budget(clusters, per_10min, max_frames)
        min_gap = float(cfg(conf, "frames.min_gap_seconds", 20))
        selected = _enforce_min_gap(selected, min_gap)
        print(f"  预算与最小间隔后：{len(selected)}")

        frames_dir.mkdir(parents=True, exist_ok=True)
        for old in frames_dir.glob("*.jpg"):
            old.unlink()

        records: list[dict] = []
        for index, cluster in enumerate(selected):
            final = _extract_final(
                ffmpeg, src, frames_dir, cluster["t"], width, quality, log_path
            )
            records.append(
                {
                    "file": final.name,
                    "path": f"frames/{final.name}",
                    "t_s": round(cluster["t"], 2),
                    "t_ms": int(round(cluster["t"] * 1000)),
                    "reason": cluster["reason"],
                    "cluster": index,
                    "frames_in_cluster": cluster["count"],
                    "sharpness": round(cluster["sharpness"], 1),
                }
            )
            if (index + 1) % 20 == 0 or index + 1 == len(selected):
                print(f"  导出 {index + 1}/{len(selected)}")

        index_path = frames_dir / "index.json"
        index_path.write_text(
            json.dumps(
                {
                    "meta": {
                        "source": src.name,
                        "duration_s": duration,
                        "scene_threshold": scene_thr,
                        "interval_seconds": interval,
                        "candidates": len(candidates),
                        "clusters": len(clusters),
                        "kept": len(records),
                    },
                    "frames": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        shutil.rmtree(cand_dir, ignore_errors=True)

        elapsed = time.time() - started
        meta.mark_done(
            "s2",
            outputs=[index_path],
            params={
                "candidates": len(candidates),
                "clusters": len(clusters),
                "kept": len(records),
                "scene_threshold": scene_thr,
                "interval_seconds": interval,
                "max_frames": max_frames,
                "elapsed_s": round(elapsed, 1),
            },
            base_dir=work_dir,
        )

        print(f"完成：{slug}")
        print(f"  保留 {len(records)} 帧，{fmt_duration(duration)} 覆盖")
        print(f"  索引：{index_path}")
        print("下一步：S3 大纲（Claude 读 transcript.txt + 邻近帧）")
        return 0

    except ToolError as exc:
        if meta is not None and meta.status("s2") == "running":
            meta.mark_failed("s2", str(exc))
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        if meta is not None and meta.status("s2") == "running":
            meta.mark_failed("s2", f"{type(exc).__name__}: {exc}")
        print(f"错误：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
