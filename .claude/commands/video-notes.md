---
description: 视频 → Markdown 笔记 → HTML 课件 全流程
argument-hint: <视频路径> [--from sN] [--to sN] [--auto]
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

按 `.claude/skills/video-notes/SKILL.md` 执行完整流水线。参数 `$ARGUMENTS`。

1. **解析参数**：视频路径、`--from`/`--to`（s0–s5，默认 s0→s5）、`--auto`（跳过确认点）。
   未给路径时，列出 `videos/` 里的文件让用户选。
2. **S0**：`python scripts/probe.py <视频>`。失败则读 `work/<slug>/logs/` 定位，向用户说明。
3. **S1/S2**：`python scripts/transcribe.py <视频>`、`python scripts/keyframes.py <视频>`。
   脚本不存在时明确告知"该阶段尚未实现"，不要伪造产物。
4. **S3**：读转写，写 `work/<slug>/outline.md`，**停下等用户确认**（除非 `--auto`）。
5. **S4**：按 SKILL.md 与需求文档 §8 写 `output/<slug>/notes.md`，跑完 §8.4 自检。
6. **S5**：先写 `work/<slug>/slide-plan.md` 等确认，再生成 `output/<slug>/slides/`，
   做截图自检，写 `output/<slug>/report.md`。
7. 每步结束用 `python scripts/status.py --slug <slug>` 汇报当前阶段状态。

约束：不虚构视频内容；所有论点带 `[mm:ss]`；课件必须离线可用。
