# AGENTS.md — 视频 → 笔记 → 课件

本文件是本仓库的**唯一入口**。任何能读写文件、执行 shell 的编码 agent 都按它工作：
Claude Code、Codex、Gemini CLI、Cursor、Windsurf、Aider，以及 Orca 里编排的 worker。

不依赖某个厂商的专有工具名。宿主差异见 [§8 多 agent 适配](#8-多-agent-适配)。

---

## 1. 这个项目做什么

把**本地**课程视频变成两样交付物：

1. `output/<slug>/notes.md`：带 `[mm:ss]` 时间戳的 Markdown 笔记。
2. `output/<slug>/slides/index.html`：完全离线的 HTML 课件（另有 PDF 与逐页 PNG）。

中间还有一层**知识深挖**（`work/<slug>/enrichment.md`）和一层**独立内容核查**
（`work/<slug>/fact-check.md`）。课件不是视频的复述，而是"是什么 → 为什么 → 怎么错 → 怎么迁移"。

完整业务规范在 [`docs/需求文档.md`](docs/需求文档.md)，本文件只讲**怎么执行**。

## 2. 你无法直接观看视频

这是最重要的事实：

- 视频已经由 S0–S2 拆成 `work/<slug>/transcript/transcript.txt`（带 `[mm:ss]`）和
  `work/<slug>/frames/*.jpg`（关键帧，文件名含时间）。
- 你只能读文本和图片。**不要假装看过视频、听过音频。**
- 每条结论必须能指向一个时间戳或一张帧图。
- 训练数据里的"常识"不能替代视频证据；视频外的补充必须标〔扩展〕。

## 3. 目录与定位

```
videos/                 原始视频（git 忽略）
work/<slug>/            中间产物（可重建）
  transcript/           S1：transcript.{txt,json,srt}
  frames/               S2：关键帧 + index.json
  outline.md            S3
  outline-decisions.md  S3 设计树追问的决策记录
  enrichment.md         S4.5
  fact-check.md         S4.6
  slide-plan.md         S5 规划
  meta.json             阶段状态与校验和
output/<slug>/          交付物
  notes.md              笔记
  notes.assets/         笔记配图
  slides/slides.md      Marp 源文件（唯一 canonical 名）
  slides/slides.pdf     PDF（带讲者备注）
  slides/index.html     单文件离线课件
  slides/theme.css      中文主题
  slides/selfcheck.*    逐页 PNG + 联系表
  report.md             交付报告
output/index.html       全套课时总索引（scripts/build_index.py 生成）
prompts/                各阶段的可移植提示词
scripts/                确定性脚本
docs/                   需求与选型
```

`slug` = `<视频文件名>_<内容哈希前 8 位>`，由 `scripts/probe.py` 生成。
不确定当前状态时先跑：

```bash
python scripts/status.py
python scripts/status.py --slug <slug>
```

## 4. 流水线

| 阶段 | 谁做 | 命令 / 提示词 | 产物 | 门禁 |
|---|---|---|---|---|
| S0 预处理 | 脚本 | `python scripts/probe.py <video>` | `audio/audio.wav`、`meta.json` | `status.py` 显示 `s0=done` |
| S1 转写 | 脚本 | `python scripts/transcribe.py <video>` | `transcript/*` | 同上 |
| S2 抽帧 | 脚本 | `python scripts/keyframes.py <video>` | `frames/*.jpg` | 同上 |
| S3 大纲 | agent | [`prompts/s3-outline.md`](prompts/s3-outline.md) | `outline.md`、`outline-decisions.md`（可选） | `check_outline.py` |
| S4 笔记 | agent | [`prompts/s4-notes.md`](prompts/s4-notes.md) | `output/<slug>/notes.md` | `verify_notes.py` |
| S4.5 深挖 | agent（推理层） | [`prompts/s4.5-enrichment.md`](prompts/s4.5-enrichment.md) | `enrichment.md` | `check_enrichment.py` |
| S4.6 核查 | **独立 agent** + 作者 | [`prompts/s4.6-factcheck.md`](prompts/s4.6-factcheck.md) | `fact-check.md` | `check_factcheck.py`（两轮，见 §4.3） |
| S5 课件 | agent | [`prompts/s5-slides.md`](prompts/s5-slides.md) | `slides/*` | `check_slides.py` |

设计原则：**脚本只做确定性的事，agent 只做判断的事。**
探测、转写、抽帧、渲染、截图测量都属于脚本；大纲、写作、深挖、核查、排版属于 agent。

### 4.1 先跑确定性阶段

```bash
python scripts/probe.py videos/第3讲.mp4
python scripts/transcribe.py videos/第3讲.mp4
python scripts/keyframes.py videos/第3讲.mp4
```

脚本已完成会自动跳过；重跑加 `--force`。失败时读 `work/<slug>/logs/` 的尾部，
修因不绕过。不要手写假转写、假帧图。

### 4.2 再逐阶段做判断

把对应 `prompts/*.md` 的内容作为任务说明交给 agent，替换 `{{SLUG}}` / `{{VIDEO}}`。
每个提示词都自带输入、步骤、门禁和停止条件，可以单独执行。

### 4.3 S4.6 与 S5 的两轮顺序（避免循环依赖）

核查要覆盖课件页，但课件又要在核查通过后才能定稿——这不是死循环，而是**两轮**：

1. **S4.6-A（课件之前）**：核查 `transcript` / `notes.md` / `enrichment.md`。
   这一轮不要传 `--slides`，只保证笔记与深挖没有硬错误。
2. **S5 草稿**：写 `slide-plan.md` 与 `slides/slides.md`，先不要导出最终 HTML/PDF。
3. **S4.6-B（草稿之后）**：另起一个独立上下文，逐页核查 `slides.md`，
   每个 `src ext` 页都要有一行 `课件 pN`；把结果追加到同一张 `fact-check.md`。
4. **处理 + 定稿**：改完 ERROR、收紧 WEAK、标注 CONTESTED，再渲染 HTML/PDF/PNG。
5. **总门禁**：`python scripts/gates.py <slug>`，此时 `--slides` 必须存在，
   覆盖笔记、深挖、全部扩展页与版式。

**不要**把 S4.6-A 当成完整核查就进入定稿；也不要因为课件还没写就跳过 B 轮。
两轮的核查员都必须与作者隔离。

## 5. 门禁：一条命令

```bash
python scripts/gates.py <slug>          # 全量：五道缺一即 FAIL（01 使用说明按设计豁免深挖/核查）
python scripts/gates.py --all           # 全部课时
python scripts/gates.py <slug> --only notes --strict  # 只跑某项时，缺产物也 FAIL
```

它统一解析课件源文件：**只认 `slides/slides.md`**，兼容旧的 `slides.rich.md` 并提示改名。
`--slides` 路径不存在时直接 FAIL。历史教训：`check_factcheck.py` 曾因路径不存在而静默跳过
扩展页覆盖检查，导致 03–09 误报 PASS；现在的门禁不会再给假通过。

单项门禁（调试时用）：

```bash
python scripts/check_outline.py work/<slug>/outline.md --slug <slug>
python scripts/verify_notes.py output/<slug>/notes.md --slug <slug>
python scripts/check_enrichment.py work/<slug>/enrichment.md
python scripts/check_factcheck.py work/<slug>/fact-check.md \
  --enrichment work/<slug>/enrichment.md \
  --slides output/<slug>/slides/slides.md
python scripts/check_slides.py output/<slug>/slides
```

Windows 控制台遇到 IPA 字符报 `UnicodeEncodeError` 时，命令前加
`PYTHONIOENCODING=utf-8`（PowerShell：`$env:PYTHONIOENCODING='utf-8'`）。

上面的 bash 示例在 Git Bash / WSL / macOS / Linux 可直接跑。在 PowerShell 里：

- `VAR=x cmd` 改为先 `$env:VAR='x'`，再另起一行 `cmd`；
- 行尾 `\` 续行改为单行命令；
- `ls | head` 改为 `Get-ChildItem | Select-Object -First 10`。

`gates.py` 的退出码：0 全部通过；1 单元不存在或内容门禁失败；2 用法错误（未知门禁、缺 slug）。
`check_factcheck.py` 缺 `--slides` 且没有 `--allow-no-slides` 时返回 2。

## 6. 写查分离（S4.6 的硬规则）

**写的人和查的人必须是两个上下文。** 作者不能自己判"没问题"。

核查 agent 按轮次只拿这些文件，不要多拿：

- **A 轮（课件之前）**：`work/<slug>/transcript/transcript.txt`、`output/<slug>/notes.md`、
  `work/<slug>/enrichment.md`
- **B 轮（课件草稿之后）**：再加 `output/<slug>/slides/slides.md`

不继承写作过程、不继承作者的自我解释。它以"假设一定有错"的姿态找：

- 事实错误、过度概括、把"常见"说成"规则"
- 错误归因（把〔扩展〕写成"老师说的"）
- 内部矛盾、英文例句不自然
- 词源、历史、统计数字没有依据

它**只报告，不改文件**。作者逐条处理：`ERROR` 必改，`WEAK` 收紧，`CONTESTED` 在课件
可见位置标注。视频本身讲错的，标"讲者的简化/口误"，不能照抄成结论。

宿主怎么提供"独立上下文"见下一节。宿主没有子 agent 时，开一个新会话、只贴当前轮次需要的文件（A 轮三个，B 轮再加课件）
和提示词，也能达到同样的隔离。

## 7. 产物与命名约定

- 课件源文件唯一名字：`slides/slides.md`；PDF 唯一名字：`slides/slides.pdf`。
- 旧名 `slides.rich.md`、`slides.final.pdf`、`slides.v22.pdf` 只作历史兼容，不再新建。
- 深挖卡 ID：`E01`、`E02`……；核查表位置写 `E01` 或课件页 `p13`。
- 核查表表头固定：
  `| ID | 位置 | 主张 | 类型 | 判定 | 说明 | 处理 |`
- 来源三级标注：〔视频〕〔推演〕〔扩展〕，课件用
  `<span class="src video">视频 12:34</span>`、`.src.infer`、`.src.ext`。
- 报告写 `output/<slug>/report.md`，至少记录：页数、深挖页数、门禁结果、核查问题与处理、已知局限。

## 8. 多 agent 适配

本仓库不绑定 Claude。核心层是 `AGENTS.md` + `prompts/` + `scripts/`；各宿主的适配只是薄壳。

| 宿主 | 入口 | 说明 |
|---|---|---|
| **Claude Code** | `CLAUDE.md` → `AGENTS.md`；`/video-*` 斜杠命令 | `.claude/skills/` 是薄适配层，规则以本文件为准 |
| **Codex CLI** | 自动读取 `AGENTS.md` | 例：`codex exec "读 AGENTS.md 和 prompts/s4.6-factcheck.md，核查 {{SLUG}}"` |
| **Gemini CLI** | `GEMINI.md` → `AGENTS.md` | 例：`gemini -p "读 AGENTS.md，按 prompts/s5-slides.md 做 {{SLUG}}"` |
| **Cursor / Windsurf** | 自动读取根目录 `AGENTS.md` | 在对话里指定阶段提示词 |
| **Orca worker** | 把 `AGENTS.md` + 阶段提示词作为 task | 可派 Claude / Codex worker 并行；核查用另一个 worker 保证隔离 |
| **其他** | 直接读 `AGENTS.md` | 只要能读写文件、跑 shell 即可 |

### 8.1 独立核查的宿主写法

| 宿主 | 做法 |
|---|---|
| Claude Code | 用 Agent 工具起一个**不继承上下文**的子 agent，提示词用 `prompts/s4.6-factcheck.md` |
| Codex | 新开一个 `codex exec` 会话：A 轮给三个文件，B 轮加 `slides.md` |
| Gemini CLI | 新会话 `gemini -p`：A 轮三个文件，B 轮加 `slides.md` |
| Orca | 另起一个 worker（最好跨厂商）：A、B 两轮各自独立，B 轮再加课件 |
| 都没有 | 人工开新会话粘贴对应轮次的文件 |

**不要**把作者的推理过程、辩解、"我已经检查过了"带给核查 agent。

### 8.2 在 Orca 里编排

用户已授权用 Orca 编排 worker 开发。建议分工：

- 写作类阶段（S3–S4.5，以及 S5 的写作部分）可以由一个 worker 顺序做，保持大纲与文风一致。
- S4.6 必须换一个 worker / 会话，最好换一个厂商（Claude 写、Codex 查，或反之）。
- 机械任务（重命名、跑门禁、生成索引）交给脚本，不派 agent。

## 9. 硬约束

- 视频原意不得改写；讲者原话、原例必须带 `[mm:ss]`。
- 视频外的知识必须标〔扩展〕，不能伪装成"老师说的"。
- 不虚构时间戳、原话、词源、统计数字、英文例句。
- 视频讲错或简化的地方要标出，不能直接抄成结论。
- 图片必须本地存在；课件禁止外链、CDN；断网必须能打开。
- 不修改上游产物（`audio/`、`transcript/*.json` 等）；要改就重跑对应阶段。
- 门禁失败时修内容，不改门禁来迁就内容。
- 每集定稿顺序：`check_slides.py` → `gates.py <slug>` → 写 `report.md` → 再跑一次 `gates.py`，以最后一次为准。
- 产物变化后跑 `python scripts/build_index.py` 更新总索引。

## 10. 交互与停止点

- **S3 结束必须停下等用户确认**（除非用户在任务里明确写"跳过确认"/AUTO）。
- S5 开始前先写 `slide-plan.md`，等确认页数与顺序（除非用户在任务里明确写"跳过确认"/AUTO）。
- 其余阶段失败可重试；不要静默跳过。
- 汇报时给：章节数、字数、时间覆盖率、深挖卡数、核查行数与处理结果、课件页数与深挖页数、门禁结论。

## 11. 一次完整执行的顺序

```text
status.py → probe/transcribe/keyframes → s3-outline → check_outline
→ 等确认 → s4-notes → verify_notes
→ s4.5-enrichment → check_enrichment
→ s4.6-A 核查笔记与深挖（独立上下文）→ check_factcheck --allow-no-slides
→ s5-slides 草稿（先 slide-plan，等确认）
→ s4.6-B 逐页核查课件（另一个独立上下文）→ check_factcheck --slides
→ 修内容、定稿渲染 → check_slides
→ gates.py <slug> → report.md → gates.py <slug>（以最后一次为准）
→ build_index.py → package.py
```

任何一步失败，先修因，再重跑该步及其下游。