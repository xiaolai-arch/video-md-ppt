---
name: video-notes
description: 把本地视频转成带时间戳的 Markdown 笔记和离线 HTML 课件。当用户要求"处理某个视频/给视频做笔记/把讲座转成笔记/用笔记做课件"时使用。该技能规定了流水线阶段、产物位置、阶段提示词与质量门槛。
---

# 视频 → 笔记 → 课件（Claude Code 适配层）

**规范以仓库根目录 [`AGENTS.md`](../../../AGENTS.md) 与 [`prompts/`](../../../prompts/) 为准。**
本文件只保留 Claude Code 的入口与专属说明，避免两份规则漂移。

## 先读

1. `AGENTS.md`：流水线、产物位置、硬约束、多 agent 适配。
2. `prompts/<stage>.md`：当前阶段的完整任务说明。
3. `docs/需求文档.md`：业务规范（§8 笔记、§9 课件）。

## 阶段路由

| 阶段 | 提示词 | 产物 |
|---|---|---|
| S0–S2 | `prompts/s0-s2-ingest.md` | `audio/`、`transcript/`、`frames/` |
| S3 | `prompts/s3-outline.md` | `work/<slug>/outline.md` |
| S4 | `prompts/s4-notes.md` | `output/<slug>/notes.md` |
| S4.5 | `prompts/s4.5-enrichment.md` | `work/<slug>/enrichment.md` |
| S4.6 | `prompts/s4.6-factcheck.md` | `work/<slug>/fact-check.md` |
| S5 | `prompts/s5-slides.md` | `output/<slug>/slides/*` |

## Claude Code 专属

- **S4.6 写查分离**：用 Agent 工具起一个不继承写作上下文的新 agent，只给
  `transcript.txt`、`notes.md`、`enrichment.md`、`slides.md`，提示词用
  `prompts/s4.6-factcheck.md`。不要自己查自己。
- **S3 盘问**：可调用 `outline-grill` 技能做设计树追问，决策写入 `outline-decisions.md`。
- **门禁**：优先一条命令 `python scripts/gates.py <slug>`；单项脚本见 `AGENTS.md` §5。
- **Windows**：IPA 输出报 GBK 编码错误时加 `PYTHONIOENCODING=utf-8`。

## 硬性约束（摘要）

- 你无法直接观看视频；结论必须能指向转写时间戳或帧图。
- 视频原意不得改写；〔扩展〕不得伪装成"老师说的"。
- 视频讲错或简化的地方要标出，不能照抄成结论。
- 课件必须单文件、零外链、断网可开。
- 门禁失败修内容，不改门禁迁就内容。
