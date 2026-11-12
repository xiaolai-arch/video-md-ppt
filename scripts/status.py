#!/usr/bin/env python3
"""查看每个视频的工作区与各阶段状态。

用法:
    python scripts/status.py [--json] [--slug xxx]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    STAGES,
    STAGE_LABELS,
    Meta,
    ToolError,
    ensure_utf8_stdout,
    fmt_duration,
    load_config,
    path_cfg,
)


def stage_status(meta: Meta, stage: str, slug: str, work_root: Path, output_root: Path) -> str:
    """s3–s5 由人工产出，没有 meta 记录时按产物是否存在判断。"""
    status = meta.status(stage)
    if status != "pending":
        return status
    artifacts = {
        "s3": work_root / slug / "outline.md",
        "s4": output_root / slug / "notes.md",
        "s5": output_root / slug / "slides" / "index.html",
    }
    artifact = artifacts.get(stage)
    return "done" if artifact and artifact.exists() else status


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="查看视频处理进度")
    parser.add_argument("--config", default=None)
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--slug", default=None, help="只看某个工作区")
    args = parser.parse_args(argv)

    try:
        conf = load_config(args.config)
        work_root = path_cfg(conf, "paths.work", "work")
        output_root = path_cfg(conf, "paths.output", "output")
        if not work_root.exists():
            print(f"工作区为空：{work_root}")
            return 0

        pattern = f"{args.slug}/meta.json" if args.slug else "*/meta.json"
        metas = []
        for meta_path in work_root.glob(pattern):
            try:
                metas.append((meta_path.parent.name, Meta(meta_path)))
            except ToolError as exc:
                print(f"跳过：{exc}", file=sys.stderr)
        metas.sort(key=lambda item: item[1].data.get("updated_at", ""), reverse=True)

        if not metas:
            print(f"工作区为空：{work_root}")
            return 0

        if args.json:
            payload = {
                slug: {
                    "source": meta.data.get("source", {}).get("path"),
                    "duration_s": (meta.data.get("probe") or {}).get("duration_s"),
                    "stages": {
                        s: {
                            "status": stage_status(meta, s, slug, work_root, output_root),
                            "error": meta.error(s),
                        }
                        for s in STAGES
                    },
                    "updated_at": meta.data.get("updated_at"),
                }
                for slug, meta in metas
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        for slug, meta in metas:
            source = meta.data.get("source") or {}
            probe = meta.data.get("probe") or {}
            print(f"{slug}")
            print(f"  源文件：{source.get('name', '?')}   时长：{fmt_duration(probe.get('duration_s'))}")
            marks = []
            for stage in STAGES:
                status = stage_status(meta, stage, slug, work_root, output_root)
                symbol = {"done": "OK", "running": "..", "failed": "XX", "pending": "--"}.get(status, "??")
                marks.append(f"{stage}{STAGE_LABELS[stage]}={symbol}")
            print("  阶段：" + "  ".join(marks))
            for stage in STAGES:
                if meta.status(stage) == "failed":
                    print(f"  失败({stage})：{meta.error(stage)}")
            print(f"  更新：{meta.data.get('updated_at', '?')}")
            print()
        return 0

    except ToolError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
