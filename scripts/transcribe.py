#!/usr/bin/env python3
"""S1 转写：faster-whisper → transcript.json / .srt / .txt + 疑点表。

用法:
    python scripts/transcribe.py <视频路径|slug> [--force] [--model large-v3]
                                 [--language zh] [--device cuda|cpu]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    ROOT,
    Meta,
    ToolError,
    cfg,
    ensure_utf8_stdout,
    fmt_duration,
    load_config,
    path_cfg,
    prepare_cuda_dlls,
    resolve_workspace,
)


# Whisper 在静音 / BGM 上常见的固定幻觉，出现即整段丢弃并留审计记录
HALLUCINATION_MARKERS = (
    "请不吝点赞",
    "订阅转发打赏",
    "明镜与点点",
    "字幕由",
    "谢谢观看",
)


def suspect_reason(item: dict) -> str | None:
    """段级疑点判定：以词概率为主。

    Whisper 的 no_speech_prob 在带 BGM、VAD 切得很碎的片子会整体虚高
    （实测中位数 0.88），单独用 >0.6 会把整条视频标成疑点，因此只作参考。
    """
    probs = [w["p"] for w in item.get("words", []) if w.get("p") is not None]
    avg = sum(probs) / len(probs) if probs else None
    low = min(probs) if probs else None
    if avg is not None and avg < 0.5:
        return f"平均概率={avg:.2f}"
    if low is not None and low < 0.2:
        return f"最低词概率={low:.2f}"
    if item.get("avg_logprob", 0.0) < -1.0:
        return f"对数概率={item['avg_logprob']:.2f}"
    return None


def _srt_time(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _load_glossary(conf: dict, override: str | None = None) -> list[str]:
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            path = ROOT / path
    else:
        rel = cfg(conf, "asr.glossary")
        if not rel:
            return []
        path = path_cfg(conf, "asr.glossary", str(rel))
    if not path.exists():
        return []
    terms: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        term = line.split("\t")[0].strip()
        if term and term not in terms:
            terms.append(term)
    return terms


def _build_hotwords(terms: list[str], limit: int = 400, max_chars: int = 2000) -> str | None:
    if not terms:
        return None
    kept: list[str] = []
    size = 0
    for term in terms[:limit]:
        if size + len(term) + 1 > max_chars:
            break
        kept.append(term)
        size += len(term) + 1
    return " ".join(kept) if kept else None


def _resolve_device(conf: dict, force_device: str | None = None,
                    force_compute: str | None = None) -> tuple[str, str]:
    requested = (force_device or str(cfg(conf, "asr.device", "auto"))).lower()
    compute = force_compute or str(cfg(conf, "asr.compute_type", "int8_float16"))

    if requested == "auto":
        ok, detail = prepare_cuda_dlls()
        if ok:
            requested = "cuda"
        else:
            print(f"  提示：{detail}；自动降级到 CPU。")
            print("  如需 GPU：安装 CUDA 12 + cuDNN 9，或参考 docs/技术选型.md。")
            requested = "cpu"
    elif requested == "cuda":
        ok, detail = prepare_cuda_dlls()
        if not ok:
            raise ToolError(
                f"无法使用 CUDA：{detail}\n"
                "安装 CUDA 12 + cuDNN 9，或改用 --device cpu --compute-type int8。"
            )

    if requested == "cpu" and compute not in {"int8", "float32", "int16"}:
        compute = "int8"
    return requested, compute


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="S1 转写：faster-whisper")
    parser.add_argument("target", help="视频路径或 slug")
    parser.add_argument("--config", default=None)
    parser.add_argument("--force", action="store_true", help="S1 已完成时强制重跑")
    parser.add_argument("--model", default=None, help="覆盖 config.toml 的 asr.model")
    parser.add_argument("--language", default=None, help="覆盖 asr.language，auto 表示自动检测")
    parser.add_argument("--device", default=None, help="覆盖 asr.device")
    parser.add_argument("--compute-type", default=None, help="覆盖 asr.compute_type")
    parser.add_argument("--glossary", default=None, help="术语表路径，覆盖 config.toml")
    args = parser.parse_args(argv)

    meta: Meta | None = None
    try:
        conf = load_config(args.config)
        slug, work_dir, meta, src = resolve_workspace(args.target, conf)
        if meta is None or not meta.is_done("s0"):
            from probe import main as probe_main

            code = probe_main([str(src)])
            if code != 0:
                raise ToolError("S0 预处理失败，无法转写")
            meta = Meta(work_dir / "meta.json")

        if meta.is_done("s1") and not args.force:
            print(f"S1 已完成，跳过：{slug}")
            print(f"转写：{work_dir / 'transcript' / 'transcript.json'}")
            return 0

        audio = work_dir / "audio" / "audio.wav"
        if not audio.exists():
            raise ToolError(f"找不到音频：{audio}（请重跑 S0）")

        from faster_whisper import WhisperModel

        model_name = args.model or str(cfg(conf, "asr.model", "large-v3"))
        model_path = Path(model_name)
        if model_path.is_dir():
            missing = [f for f in ("model.bin", "config.json", "tokenizer.json") if not (model_path / f).exists()]
            # large-v3 是 128 mel，缺 preprocessor_config.json 会报 (1,128,3000) vs (1,80,3000)
            if "large-v3" in model_path.name and not (model_path / "preprocessor_config.json").exists():
                missing.append("preprocessor_config.json")
            if missing:
                raise ToolError(
                    f"本地模型缺少文件：{', '.join(missing)}\n"
                    f"重新下载：python scripts/fetch_model.py {model_path.name}"
                )
        language = args.language if args.language is not None else str(cfg(conf, "asr.language", "zh"))
        device, compute = _resolve_device(conf, args.device, args.compute_type)
        language = None if str(language).lower() == "auto" else language

        terms = _load_glossary(conf, args.glossary)
        use_hotwords = bool(cfg(conf, "asr.hotwords", True))
        hotwords = _build_hotwords(terms) if use_hotwords else None

        meta.mark_running("s1")
        started = time.time()
        print(f"加载模型：{model_name}（{device}/{compute}）")
        print("  首次使用会从 HuggingFace 下载模型；large-v3 约 3GB。")
        model = WhisperModel(model_name, device=device, compute_type=compute)

        duration_hint = (meta.data.get("probe") or {}).get("duration_s") or 0
        print("转写中…", flush=True)
        segments_iter, info = model.transcribe(
            str(audio),
            language=language,
            beam_size=int(cfg(conf, "asr.beam_size", 5)),
            vad_filter=bool(cfg(conf, "asr.vad_filter", True)),
            word_timestamps=bool(cfg(conf, "asr.word_timestamps", True)),
            hotwords=hotwords,
            condition_on_previous_text=bool(cfg(conf, "asr.condition_on_previous_text", False)),
        )
        total = float(info.duration or duration_hint or 0.0)

        segments: list[dict] = []
        suspects: list[str] = []
        dropped: list[str] = []
        last_pct = -10
        for index, seg in enumerate(segments_iter):
            text = seg.text.strip()
            if any(marker in text for marker in HALLUCINATION_MARKERS):
                dropped.append(f"[{fmt_duration(seg.start)}] {text}")
                continue
            words = [
                {
                    "w": w.word,
                    "s": round(float(w.start), 3),
                    "e": round(float(w.end), 3),
                    "p": round(float(w.probability), 3) if w.probability is not None else None,
                }
                for w in (seg.words or [])
            ]
            item = {
                "id": len(segments),
                "start": round(float(seg.start), 3),
                "end": round(float(seg.end), 3),
                "text": text,
                "avg_logprob": round(float(seg.avg_logprob), 4),
                "no_speech_prob": round(float(seg.no_speech_prob), 4),
                "words": words,
            }
            segments.append(item)

            reason = suspect_reason(item)
            if reason:
                suspects.append(
                    f"[{fmt_duration(seg.start)}] {reason} 无语音概率={seg.no_speech_prob:.2f}  {seg.text.strip()}"
                )

            if total > 0:
                pct = int(min(100.0, seg.end / total * 100))
                if pct >= last_pct + 10:
                    print(f"  {pct:3d}%  {fmt_duration(seg.end)} / {fmt_duration(total)}", flush=True)
                    last_pct = pct

        if bool(cfg(conf, "asr.simplify", True)) and str(info.language or language or "").startswith("zh"):
            try:
                import zhconv

                for seg in segments:
                    seg["text"] = zhconv.convert(seg["text"], "zh-cn")
                    for word in seg["words"]:
                        word["w"] = zhconv.convert(word["w"], "zh-cn")
                suspects = [zhconv.convert(line, "zh-cn") for line in suspects]
            except ImportError:
                print("  提示：未安装 zhconv，跳过简繁转换（pip install zhconv）")

        out_dir = work_dir / "transcript"
        out_dir.mkdir(parents=True, exist_ok=True)
        detected = info.language or (language or "unknown")
        payload = {
            "meta": {
                "engine": "faster-whisper",
                "model": model_name,
                "device": device,
                "compute_type": compute,
                "language": detected,
                "language_probability": round(float(info.language_probability or 0), 4),
                "duration": round(total, 3),
                "hotwords": len(terms) if hotwords else 0,
                "parameters": {
                    "beam_size": int(cfg(conf, "asr.beam_size", 5)),
                    "vad_filter": bool(cfg(conf, "asr.vad_filter", True)),
                    "word_timestamps": bool(cfg(conf, "asr.word_timestamps", True)),
                },
            },
            "segments": segments,
        }
        json_path = out_dir / "transcript.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        srt_lines: list[str] = []
        for i, seg in enumerate(segments, 1):
            srt_lines += [str(i), f"{_srt_time(seg['start'])} --> {_srt_time(seg['end'])}", seg["text"], ""]
        srt_path = out_dir / "transcript.srt"
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")

        txt_lines = [
            f"# 转写：{src.name}",
            f"# 语言：{detected}（{float(info.language_probability or 0):.2f}）  时长：{fmt_duration(total)}  模型：{model_name}",
            "",
        ]
        for seg in segments:
            txt_lines.append(f"[{fmt_duration(seg['start'])}] {seg['text']}")
        txt_path = out_dir / "transcript.txt"
        txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")

        suspects_path = out_dir / "asr_suspects.txt"
        suspects_path.write_text(
            ("\n".join(suspects) + "\n") if suspects else "（无疑点）\n", encoding="utf-8"
        )

        outputs = [json_path, srt_path, txt_path, suspects_path]
        if dropped:
            dropped_path = out_dir / "dropped.txt"
            dropped_path.write_text("\n".join(dropped) + "\n", encoding="utf-8")
            outputs.append(dropped_path)
            print(f"  已丢弃 {len(dropped)} 段幻觉文本 → {dropped_path}", flush=True)

        elapsed = time.time() - started
        meta.mark_done(
            "s1",
            outputs=outputs,
            params={
                "model": model_name,
                "device": device,
                "compute_type": compute,
                "language": detected,
                "language_probability": round(float(info.language_probability or 0), 4),
                "segments": len(segments),
                "suspects": len(suspects),
                "dropped_hallucinations": len(dropped),
                "hotwords": len(terms) if hotwords else 0,
                "elapsed_s": round(elapsed, 1),
                "speed_x": round(total / elapsed, 2) if elapsed > 0 and total else None,
            },
            base_dir=work_dir,
        )
        (work_dir / "logs").mkdir(parents=True, exist_ok=True)
        (work_dir / "logs" / "s1-transcribe.log").write_text(
            json.dumps(
                {
                    "model": model_name,
                    "device": device,
                    "compute_type": compute,
                    "elapsed_s": round(elapsed, 1),
                    "duration_s": total,
                    "segments": len(segments),
                    "suspects": len(suspects),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"完成：{slug}")
        print(f"  语言：{detected}（置信 {float(info.language_probability or 0):.2f}）  段数：{len(segments)}")
        print(f"  耗时：{elapsed / 60:.1f} 分钟（{total / elapsed:.1f}× 实时）")
        print(f"  疑点：{len(suspects)} 条 → {suspects_path}")
        print(f"  文本：{txt_path}")
        print("下一步：S2 抽帧（python scripts/keyframes.py <slug>）")
        return 0

    except ToolError as exc:
        if meta is not None and meta.status("s1") == "running":
            meta.mark_failed("s1", str(exc))
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # 模型/依赖错误给出可行动信息
        if meta is not None and meta.status("s1") == "running":
            meta.mark_failed("s1", f"{type(exc).__name__}: {exc}")
        print(f"错误：{type(exc).__name__}: {exc}", file=sys.stderr)
        print("提示：检查 CUDA/cuDNN 是否可用，或改用 --device cpu --compute-type int8。", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
