---
description: 只做转写与抽帧（S0–S2），产出带时间戳文本和关键帧
argument-hint: <视频路径 | slug> [--force]
allowed-tools: Bash, Read, Write, Glob, Grep
---

执行 S0–S2。参数 `$ARGUMENTS`。

1. 若参数是文件路径：`python scripts/probe.py <路径>`；
   若已是 slug：`python scripts/status.py --slug <slug>` 确认工作区存在。
2. 运行 `python scripts/transcribe.py <视频>`（S1）与 `python scripts/keyframes.py <视频>`（S2）。
   脚本缺失时如实说明尚未实现（M1），不要生成假转写。
3. 完成后汇报：
   - 转写语言、时长、段落数、前 200 字
   - 关键帧数量、覆盖时段、`frames/index.json` 路径
   - 人工抽检提示：随机给 3 个时间戳，让用户回听核对
4. 把失败日志（`work/<slug>/logs/`）的尾部关键行贴给用户，不整段转储。
