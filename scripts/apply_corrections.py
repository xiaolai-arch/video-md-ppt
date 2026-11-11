#!/usr/bin/env python3
"""对 S1 转写做高置信术语纠错（保留审计记录）。

规则文件为 TSV：`错误<TAB>正确[<TAB>备注]`，从长到短匹配，空行与 # 注释忽略。

用法:
    python scripts/apply_corrections.py <slug|transcript.json> --rules work/<slug>/corrections.tsv
    python scripts/apply_corrections.py <slug> --rules ... --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, ToolError, ensure_utf8_stdout, fmt_duration, load_config, path_cfg, sha256_file  # noqa: E402


def srt_time(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def load_rules(path: Path) -> list[tuple[str, str, str]]:
    rules: list[tuple[str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = line.split("\t")
        if len(cells) < 2 or not cells[0]:
            raise ToolError(f"规则格式错误（需要 错误<TAB>正确）：{line}")
        rules.append((cells[0], cells[1], cells[2] if len(cells) > 2 else ""))
    return sorted(rules, key=lambda r: len(r[0]), reverse=True)


def resolve(slug_or_json: str, conf: dict) -> tuple[Path, Path, Path]:
    target = Path(slug_or_json)
    if target.suffix.lower() == ".json":
        json_path = target if target.is_absolute() else (ROOT / target)
    else:
        json_path = path_cfg(conf, "paths.work", "work") / slug_or_json / "transcript" / "transcript.json"
    json_path = json_path.resolve()
    if not json_path.exists():
        raise ToolError(f"找不到 transcript.json：{json_path}")
    work_dir = json_path.parent.parent
    return json_path, work_dir, work_dir / "meta.json"


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="转写术语纠错（带审计）")
    parser.add_argument("target", help="slug 或 transcript.json")
    parser.add_argument("--rules", required=True, help="TSV 规则文件")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        conf = load_config()
        json_path, work_dir, meta_path = resolve(args.target, conf)
        rules_path = Path(args.rules)
        if not rules_path.is_absolute():
            rules_path = ROOT / rules_path
        rules = load_rules(rules_path)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        segments = data.get("segments") or []
        if not segments:
            raise ToolError("transcript.json 没有 segments")

        audit: list[str] = []
        applied = 0
        for old, new, note in rules:
            count = 0
            times: list[str] = []
            for seg in segments:
                n = seg["text"].count(old)
                if n:
                    count += n
                    seg["text"] = seg["text"].replace(old, new)
                    for word in seg.get("words") or []:
                        word["w"] = word["w"].replace(old, new)
                    times.append(fmt_duration(seg["start"]))
            if count:
                applied += count
                audit.append(f"{old}\t{new}\t{count}\t{','.join(times)}\t{note}")

        if not applied:
            print("没有命中任何规则。")
            return 0

        print(f"命中 {applied} 处，涉及 {len(audit)} 条规则。")
        for line in audit:
            print("  " + line.replace("\t", "  "))
        if args.dry_run:
            print("（dry-run，未写文件）")
            return 0

        out = json_path.parent
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        srt: list[str] = []
        for i, seg in enumerate(segments, 1):
            srt += [str(i), f"{srt_time(seg['start'])} --> {srt_time(seg['end'])}", seg["text"], ""]
        (out / "transcript.srt").write_text("\n".join(srt), encoding="utf-8")

        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        src_name = ((meta.get("source") or {}).get("name")) or work_dir.name
        duration = ((meta.get("probe") or {}).get("duration_s")) or data["meta"].get("duration")
        model = data["meta"].get("model", "")
        txt = [
            f"# 转写：{src_name}",
            f"# 语言：{data['meta'].get('language', 'zh')}（{data['meta'].get('language_probability', 0)}）"
            f"  时长：{fmt_duration(float(duration or 0))}  模型：{model}",
            "",
        ]
        txt += [f"[{fmt_duration(seg['start'])}] {seg['text']}" for seg in segments]
        (out / "transcript.txt").write_text("\n".join(txt) + "\n", encoding="utf-8")

        suspects: list[str] = []
        for seg in segments:
            probs = [w["p"] for w in (seg.get("words") or []) if w.get("p") is not None]
            avg = sum(probs) / len(probs) if probs else None
            if (avg is not None and avg < 0.5) or seg.get("no_speech_prob", 0) > 0.6:
                reason = f"平均概率={avg:.2f}" if avg is not None else "低置信"
                suspects.append(
                    f"[{fmt_duration(seg['start'])}] {reason} "
                    f"无语音概率={seg.get('no_speech_prob', 0):.2f}  {seg['text']}"
                )
        (out / "asr_suspects.txt").write_text(
            ("\n".join(suspects) + "\n") if suspects else "（无疑点）\n", encoding="utf-8"
        )
        audit_path = out / "corrections_applied.tsv"
        header = "时间\t错误\t正确\t次数\t位置\t备注"
        existing = []
        if audit_path.exists():
            existing = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if existing and existing[0].startswith("时间\t"):
                existing = existing[1:]
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = [f"{stamp}\t{line}" for line in audit]
        audit_path.write_text("\n".join([header] + existing + rows) + "\n", encoding="utf-8")

        data["meta"]["corrections"] = applied
        data["meta"]["corrections_rules"] = str(rules_path)
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        if meta_path.exists():
            st = (meta.get("stages") or meta).get("s1")
            if st is not None:
                st.setdefault("params", {})["corrections"] = applied
                files = [json_path, out / "transcript.srt", out / "transcript.txt",
                         out / "asr_suspects.txt", out / "corrections_applied.tsv"]
                if (out / "dropped.txt").exists():
                    files.append(out / "dropped.txt")
                st["outputs"] = [
                    {
                        "path": p.relative_to(work_dir).as_posix(),
                        "bytes": p.stat().st_size,
                        "sha256": sha256_file(p),
                    }
                    for p in files if p.exists()
                ]
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"已写入：{out / 'corrections_applied.tsv'}")
        return 0
    except ToolError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
