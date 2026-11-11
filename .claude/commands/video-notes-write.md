---
description: 从转写生成大纲与 Markdown 笔记（S3–S4）
argument-hint: <slug | 视频路径> [--auto] [--revise]
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

执行 S3–S4。参数 `$ARGUMENTS`。

前置：`work/<slug>/transcript/transcript.txt` 存在；必要时用 `python scripts/status.py --slug <slug>` 确认。

1. **S3 大纲**
   - 按时间分块读转写（每块 ≤ 30 分钟，块间重叠 1–2 分钟），不要一次读全文。
   - 需要核对画面时，只读与当前时段相邻的 `work/<slug>/frames/*.jpg`。
   - 写 `work/<slug>/outline.md`：章节标题、`[起–止]`、二级要点、`[图]/[公式]/[代码]` 标记。
   - 标出"低置信度"段落。
   - 跑 `python scripts/check_outline.py`（M2 起），再调用 `outline-grill` 做设计树追问，
     决策写入 `work/<slug>/outline-decisions.md`。
   - 除非 `--auto`，**停下等用户确认**；用户提出修改时改 outline 而不是改笔记。
2. **S4 笔记**
   - 严格按 `.claude/skills/video-notes/SKILL.md` 与 `docs/需求文档.md` §8 写 `output/<slug>/notes.md`。
   - 图片从 `frames/` 精选，复制到 `output/<slug>/notes.assets/`，相对路径引用。
   - 逐条跑 §8.4 自检，结果写入 `output/<slug>/report.md`。
   - `--revise`：只改用户指出的部分，不动其他章节。
3. **S4.5 知识深挖**
   - 按 SKILL.md 的 S4.5 写 `work/<slug>/enrichment.md`：每个核心知识点一张卡，固定七字段。
   - 来源分级：〔视频〕带时间戳，〔推演〕能追到原规则，〔扩展〕是视频外标准知识。
   - 跑 `python scripts/check_enrichment.py work/<slug>/enrichment.md`，PASS 再进 S5。
4. **S4.6 内容核查**
   - 起独立子代理（不继承写作上下文）读 transcript/notes/enrichment/slides，按“假设有错”逐条挑错。
   - 整理成 `work/<slug>/fact-check.md`，判定 OK/WEAK/ERROR/CONTESTED；ERROR 必改，CONTESTED 必须在课件可见处标注。
   - 跑 `python scripts/check_factcheck.py ...`，PASS 才算完成。
5. 最后汇报：章节数、字数、时间覆盖率、深挖卡数、核查问题数与处理结果。

红线：视频原意不得改写；视频讲错或简化的地方要标出，不能照抄成结论；〔扩展〕内容不得冒充讲者观点。
