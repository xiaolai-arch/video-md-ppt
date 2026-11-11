---
name: video-notes
description: 把本地视频转成带时间戳的 Markdown 笔记和离线 HTML 课件。当用户要求"处理某个视频/给视频做笔记/把讲座转成笔记/用笔记做课件"时使用。该技能规定了六阶段流水线、产物位置、笔记与课件规范和质量门槛。
---

# 视频 → 笔记 → 课件

完整需求见 `docs/需求文档.md`。本文件是执行时的操作手册。

## 核心事实

- **你无法直接观看视频。** 音频已经由 S0/S1 转成文本，画面已经由 S2 抽成 JPG。
  你能读的只有：`work/<slug>/transcript/transcript.txt`、`work/<slug>/frames/*.jpg`、
  以及自己产出的 `outline.md`、`notes.md`。
- 不要假装看过视频。所有结论都必须能指向转写里的时间戳或某张帧图。
- 确定性工作（抽音频、转写、抽帧、截图）交给 `scripts/*.py`；你只做提炼、写作、排版。

## 阶段与产物

| 阶段 | 执行者 | 产物 | 完成标志 |
|---|---|---|---|
| S0 预处理 | `scripts/probe.py` | `work/<slug>/audio/audio.wav`、`meta.json` | `s0=done` |
| S1 转写 | `scripts/transcribe.py` | `transcript/transcript.{json,srt,txt}` | `s1=done` |
| S2 抽帧 | `scripts/keyframes.py` | `frames/*.jpg`、`frames/index.json` | `s2=done` |
| S3 大纲 | 你 | `work/<slug>/outline.md` | 用户确认 |
| S4 笔记 | 你 | `output/<slug>/notes.md` | 通过 §8.4 清单 |
| S4.5 深挖 | 你（推理层） | `work/<slug>/enrichment.md` | 通过 `check_enrichment.py` |
| S4.6 核查 | 独立子代理 + 你 | `work/<slug>/fact-check.md` | 通过 `check_factcheck.py` |
| S5 课件 | 你 | `output/<slug>/slides/index.html` | 通过 §9.5 清单 |

**当前实现状态**：M0–M3 已完成。S0–S2 脚本、S3/S4 门禁、S5 Marp 渲染均已用真实视频跑通。
若脚本不存在，明确告诉用户该阶段尚未实现，**不要编造产物**。

## 工作区定位

```bash
python scripts/status.py              # 列出所有 slug 及阶段状态
python scripts/status.py --slug <slug>
```

`slug` = `<视频文件名>_<内容哈希前8位>`。后续所有命令都以 slug 或视频路径定位工作区。

## 各阶段操作

### S0
```bash
python scripts/probe.py videos/xxx.mp4
```
- 已完成会跳过；需要重跑加 `--force`。
- 报"没有音轨"时停止，告知用户该视频不适配当前流水线。

### S3 大纲
1. 读 `transcript.txt`（超过 30 分钟按时间分块读，不要一次读全文）。
2. 需要确认画面内容时，只读与当前时间段相邻的 `frames/` 图片。
3. 写 `outline.md`：章节标题、`[起–止]` 时间范围、二级要点、`[图]`/`[公式]`/`[代码]` 标记。
4. 标出 `低置信度` 段落（转写含糊、语义跳跃）。
5. 跑 `python scripts/check_outline.py`（M2 起）；再调用 `outline-grill` 做设计树追问，
   决策写入 `outline-decisions.md`。
6. **停在这里等用户确认**，除非用户明确说跳过/自动。

### S4 笔记
按需求文档 §8 的 frontmatter、结构与内容规则写 `output/<slug>/notes.md`；
图片从 `frames/` 精选后复制到 `output/<slug>/notes.assets/`。
写完后跑 `python scripts/verify_notes.py`（M2 起）逐条核对 §8.4，结果写进 `output/<slug>/report.md`。
可选：让一个无上下文的子代理只读 notes.md 做 reader test（哪里看不懂、哪个结论没时间戳）。

### S4.5 知识深挖（推理层）
这一阶段是“让课件有味道”的关键：不只复述视频，而是把每个知识点拆成**是什么 → 为什么 → 怎么错 → 怎么迁移**。

1. 读 `outline.md`、`notes.md` 与抽帧，列出全片的核心知识点（通常 15–25 个）。
2. 每个知识点写一张卡片到 `work/<slug>/enrichment.md`，字段固定：
   ```markdown
   ### E01 卡片标题
   - **对应视频**：[mm:ss]（视频外写“无”）
   - **一句话**：结论，≤ 40 字
   - **原理**：为什么会这样，讲清机制或来源
   - **例**：至少两个对比例句/实例
   - **易错**：学生最可能怎么错
   - **迁移**：换一道题/换一个场景怎么用
   - **来源**：〔视频〕/〔推演〕/〔扩展〕，可组合
   ```
3. 来源必须分级，不能混：
   - `〔视频〕` 讲者原话或原例，必须带 `[mm:ss]`；
   - `〔推演〕` 从视频规则推导出的解释，可以没有新时间戳，但要能追到原规则；
   - `〔扩展〕` 视频外补充的标准知识，不得写成“老师说的”。
4. 学科知识要可核对：语法/术语用标准体系，历史词源、统计数字等没有把握就不写；宁可少一条，不编一条。
5. 若发现讲者表述是教学简化（例：“动词只能作谓语”），不要删，另起一张“校正卡”说明准确说法，课件上用“讲者的简化”标注。
6. 跑 `python scripts/check_enrichment.py work/<slug>/enrichment.md`，PASS 才能进 S5。

### S4.6 内容核查（防止把视频里的错误整理成课件）
**原则：写的人和查的人必须分开。** 不能自己写完自己判“没问题”。

1. 起一个独立子代理（不继承你的推理过程），只给它 `transcript.txt`、`notes.md`、`enrichment.md`、`slides.md`，
   让它以“假设一定有错”的姿态找：事实错误、过度概括、争议规则、错误归因、内部矛盾、英文例句不自然。
2. 把它的结论整理成 `work/<slug>/fact-check.md`，表头固定：
   `| ID | 位置 | 主张 | 类型 | 判定 | 说明 | 处理 |`
   - 判定：`OK` / `WEAK` / `ERROR` / `CONTESTED`
   - 类型：视频原意 / 语法规则 / 词源 / 例句 / 术语
   - 位置写卡片号（E01）或课件页（p13）
3. 逐条处理：
   - `ERROR` 必须改；不能留“待处理”。
   - `WEAK` 收紧措辞或加限定。
   - `CONTESTED` 必须在课件可见位置标“考试约定 / 有争议”，不能只写在备注里。
   - 视频本身讲错的，课件要标“讲者的简化/口误”，不能照抄成结论。
4. 常见高风险点，逐项过：
   - 绝对化：所有 / 一定 / 永远 / 唯一 / 从不
   - 把“常见”说成“规则”（o 结尾、the+形容词、乐器加 the）
   - 词源、历史、统计数据
   - 英文例句的语法与自然度
   - 视频原意 vs 推演 vs 扩展的归因
5. 跑 `python scripts/check_factcheck.py work/<slug>/fact-check.md --enrichment ... --slides ...`。
   它要求：≥20 行、每张 E 卡被查、每个带扩展角标的页面被查、ERROR 全部有处理、CONTESTED 有标注。
6. 修完内容后重渲染课件，再跑 `check_slides.py`。

### S5 课件
1. 先写 `work/<slug>/slide-plan.md`（每页标题/要点/配图/讲者备注/来源时间戳），请用户确认。
   深挖页要单独列出：原理页、对比页、迁移页、自测页。
2. 生成 `output/<slug>/slides.md` 与 `theme.css`，再用 **Marp CLI** 渲染：
   ```bash
   npx -y @marp-team/marp-cli@4.5.1 --no-stdin output/<slug>/slides/slides.md \
     -o output/<slug>/slides/index.html --html \
     --theme output/<slug>/slides/theme.css --allow-local-files
   python scripts/inline_assets.py output/<slug>/slides/index.html
   ```
   主选 Marp（单文件、离线、备注内嵌）；仅当需要逐页定制版式时才改用 reveal.js。
   `inline_assets.py` 必须跑：Marp 默认只写相对路径，图片不内联就不是真单文件。
3. 遵守需求文档 §9.3 的密度规则：每页 ≤5 要点、≤7 行、宁可拆页。
   **深度规则**：每个核心知识点至少有一页“为什么/怎么错/怎么迁移”，不能整场只有原视频的结论。
   每页用角标标来源：`<span class="src video">视频 12:34</span>`、`.src.infer`、`.src.ext`。
4. 讲者备注要写“怎么讲”：先问什么、学生会在哪里错、答案怎么落地，再附来源；不要复制页面要点。
5. 导出 PDF 与逐页 PNG（`--pdf --pdf-notes`、`--images png`），做溢出与缺图自检，结果写进 `report.md`。

## 硬性约束

- 视频原意不得改写；讲者的原话、原例必须带 `[mm:ss]`。
- 补充知识允许写，但必须分级标注：〔推演〕〔扩展〕，并在课件角标可见。
- 不得把视频外知识伪装成“老师说的”；不得虚构时间戳、原话、词源或统计数字。
- 图片必须本地存在且路径正确，禁止外链。
- 课件必须完全离线可用。
- 脚本失败时读 `work/<slug>/logs/*.log` 定位，修因不绕过。
- 不修改 `work/*/audio`、`transcript/*.json` 等上游产物；要改就重跑对应阶段。

## 质量自检（交付前必做）

- 时间戳单调、不超时长、覆盖率 ≥95%
- 术语表与正文一致
- 笔记与课件结论一致（同一份大纲驱动）
- `enrichment.md` 通过 `check_enrichment.py`，且每个核心知识点有原理、对比、迁移
- `fact-check.md` 通过 `check_factcheck.py`：ERROR 已改、CONTESTED 已标注、没有未核查的扩展页
- 视频里的错误或简化已标出，没有直接抄成结论
- 课件每页来源角标与实际来源一致；〔扩展〕页不出现“视频里说”
- 课件无溢出、有讲者备注、页码正确、断网可开
