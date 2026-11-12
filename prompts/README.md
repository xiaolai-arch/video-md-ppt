# 阶段提示词

这些文件是**可移植的任务说明**，不绑定任何厂商的 agent。把文件内容作为任务交给 agent，
替换占位符即可。

| 文件 | 阶段 | 产物 |
|---|---|---|
| [`s0-s2-ingest.md`](s0-s2-ingest.md) | S0–S2 预处理、转写、抽帧 | `work/<slug>/audio`、`transcript`、`frames` |
| [`s3-outline.md`](s3-outline.md) | S3 大纲 | `work/<slug>/outline.md` |
| [`s4-notes.md`](s4-notes.md) | S4 笔记 | `output/<slug>/notes.md` |
| [`s4.5-enrichment.md`](s4.5-enrichment.md) | S4.5 知识深挖 | `work/<slug>/enrichment.md` |
| [`s4.6-factcheck.md`](s4.6-factcheck.md) | S4.6 独立核查 | `work/<slug>/fact-check.md` |
| [`s5-slides.md`](s5-slides.md) | S5 课件 | `output/<slug>/slides/*` |

占位符：

- `{{VIDEO}}`：视频路径，例如 `videos/第3讲.mp4`
- `{{SLUG}}`：工作区名，例如 `03_动词2_..._c8ee0760`；不确定时跑 `python scripts/status.py`

通用约束见 [`../AGENTS.md`](../AGENTS.md)。每个阶段结束都跑
`python scripts/gates.py {{SLUG}}`，不要只看脚本退出码就宣布完成。

## 组合方式

- **单阶段**：只把对应文件交给 agent，适合修某一层。
- **全流程**：按 `s0-s2 → s3 → s4 → s4.5 → s4.6 → s5` 顺序执行；S3 与 S5 前停下等确认。
- **独立核查**：S4.6 必须换一个上下文；见 `AGENTS.md` §8.1。
- **Orca**：写作 worker 与核查 worker 分开，最好不同厂商。

## 一条命令跑门禁

```bash
python scripts/gates.py "{{SLUG}}"
python scripts/gates.py --all
```
