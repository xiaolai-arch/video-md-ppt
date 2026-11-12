#!/usr/bin/env python3
"""按当前疑点规则重算 asr_suspects.txt，不重跑 ASR。

用法:
    python scripts/resuspect.py <slug>

用于规则收紧后回填旧产物（例如 no_speech_prob 在带 BGM 的片子里整体虚高）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    Meta,
    ensure_utf8_stdout,
    fmt_duration,
    load_config,
    resolve_workspace,
    sha256_file,
)
from transcribe import suspect_reason  # noqa: E402


def main() -> int:
    ensure_utf8_stdout()
    if len(sys.argv) != 2:
        print("用法: python scripts/resuspect.py <slug>", file=sys.stderr)
        return 2

    conf = load_config()
    slug, work_dir, meta, _ = resolve_workspace(sys.argv[1], conf)
    json_path = work_dir / "transcript" / "transcript.json"
    if not json_path.exists():
        print(f"缺少 {json_path}", file=sys.stderr)
        return 2

    data = json.loads(json_path.read_text(encoding="utf-8"))
    segments = data["segments"] if isinstance(data, dict) else data

    lines: list[str] = []
    for seg in segments:
        reason = suspect_reason(seg)
        if reason:
            lines.append(
                f"[{fmt_duration(seg['start'])}] {reason} "
                f"无语音概率={seg.get('no_speech_prob', 0):.2f}  {seg['text']}"
            )

    out = work_dir / "transcript" / "asr_suspects.txt"
    out.write_text(("\n".join(lines) + "\n") if lines else "（无疑点）\n", encoding="utf-8")

    if isinstance(meta, Meta):
        st = meta.stage("s1")
        st.setdefault("params", {})["suspects"] = len(lines)
        for rec in st.get("outputs", []):
            if rec.get("path", "").endswith("asr_suspects.txt"):
                rec["bytes"] = out.stat().st_size
                rec["sha256"] = sha256_file(out)
        meta.save()

    print(f"{slug}: 疑点 {len(lines)} 条 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())