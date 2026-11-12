# video-md-ppt

把本地视频变成**带时间戳的 Markdown 笔记**，再把笔记变成**可离线放映的 HTML 课件**。
一条分阶段执行、每步可人工干预的流水线，**不绑定单一 agent**：
Claude Code、Codex、Gemini CLI、Cursor、Orca worker 都能跑。

> 入口：[`AGENTS.md`](AGENTS.md)（agent 无关的执行手册）
> 阶段提示词：[`prompts/`](prompts/)
> 需求与设计：[`docs/需求文档.md`](docs/需求文档.md)
> 选型依据与许可证：[`docs/技术选型.md`](docs/技术选型.md)

## 状态

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 骨架、配置、状态机、S0 预处理 | ✅ 已完成 |
| M1 | S1 转写、S2 抽帧 | ✅ 脚本完成并冒烟通过（CPU/tiny） |
| M2 | S3 大纲、S4 笔记 | ✅ 真实样例通过（覆盖率 100%，笔记门禁 PASS） |
| M3 | S4.5 知识深挖、S4.6 内容核查、S5 HTML 课件 | ✅ 22 张深挖卡 + 独立核查表；58 页单文件 HTML + PDF + 逐页 PNG，自检通过 |
| M4 | 批量、多 agent 适配、全套交付 | ✅ 12 集全部完成；`AGENTS.md` + `prompts/`；`gates.py` 一键门禁；`output/index.html` 总索引 |

## 技术选型（摘要）

| 层 | 选型 |
|---|---|
| 转写 | faster-whisper + large-v3（显式 `zh`、VAD、词级时间戳、热词） |
| 抽帧 | scene + 间隔采样 → dHash 聚类 → 像素复核 → 最短停留过滤 |
| 大纲 | 自建 `outline-grill`：设计树追问 + 时间戳证据 |
| 笔记 | 证据表 + `verify_notes.py` / `check_outline.py` 门禁 |
| 深挖 | `work/<slug>/enrichment.md`：视频 / 推演 / 扩展三级来源，`check_enrichment.py` 门禁 |
| 核查 | 独立 agent 查错 → `fact-check.md`（ERROR/WEAK/CONTESTED），`check_factcheck.py` 门禁 |
| 课件 | Marp CLI 单文件 HTML（备选 reveal.js），深挖页带来源角标 |
| 编排 | `AGENTS.md` + `prompts/`，宿主适配层只做薄壳 |

理由、license 与未验证项见 [`docs/技术选型.md`](docs/技术选型.md)。

## 快速开始

```bash
python scripts/doctor.py                      # 环境自检
python scripts/fetch_model.py large-v3        # 预下载模型（镜像 + 断点续传）
python scripts/probe.py videos/第3讲.mp4       # S0：探测 + 抽音频
python scripts/transcribe.py videos/第3讲.mp4  # S1：转写（默认 large-v3）
python scripts/keyframes.py videos/第3讲.mp4   # S2：抽帧
python scripts/status.py                      # 查看进度

# 一条命令跑完一集的所有门禁
python scripts/gates.py <slug>
python scripts/gates.py --all

# 生成全套课时索引
python scripts/build_index.py

# 打包交付物（HTML + PDF + 笔记 + 报告）
python scripts/package.py
```

单项门禁（调试时用，失败时退出码 1）：

```bash
python scripts/check_outline.py work/<slug>/outline.md --slug <slug>
python scripts/verify_notes.py output/<slug>/notes.md --slug <slug>
python scripts/check_enrichment.py work/<slug>/enrichment.md
python scripts/check_factcheck.py work/<slug>/fact-check.md --enrichment work/<slug>/enrichment.md --slides output/<slug>/slides/slides.md
python scripts/check_slides.py output/<slug>/slides
```

> **GPU 说明**：faster-whisper 在 Windows 上需要 CUDA 12 的 `cublas64_12.dll` 与 cuDNN 9 的
> `cudnn_ops64_9.dll`。缺失时脚本会自动降级到 CPU（`int8`）并给出提示，不会跑到一半失败。
> 首次运行会自动下载模型：large-v3 约 3 GB。建议先跑
> `python scripts/fetch_model.py large-v3`：默认走 `hf-mirror.com`，支持断点续传，
> 不会像 `huggingface_hub` 那样卡在 0 字节；也可用 `--endpoint` 指定其他镜像。

S0 产物：

```
work/<slug>/
├─ meta.json              # 各阶段状态、参数、产物校验和
├─ audio/audio.wav        # 16kHz 单声道 16bit，供转写
└─ logs/                  # ffmpeg 原始日志
```

`slug` = `视频文件名_内容哈希前8位`，同名视频不会互相覆盖；S0 已完成会自动跳过，重跑加 `--force`。

## 多 agent 使用

核心规则只有一份：[`AGENTS.md`](AGENTS.md)。各宿主用薄适配层指向它。

| 宿主 | 入口 | 示例 |
|---|---|---|
| Claude Code | `CLAUDE.md`；`/video-*` 命令 | `/video-notes videos/第3讲.mp4` |
| Codex CLI | 自动读 `AGENTS.md` | `codex exec "读 AGENTS.md 和 prompts/s4.6-factcheck.md，核查 <slug>"` |
| Gemini CLI | `GEMINI.md` | `gemini -p "读 AGENTS.md，按 prompts/s5-slides.md 做 <slug>"` |
| Cursor / Windsurf | 自动读根目录 `AGENTS.md` | 对话里指定阶段提示词 |
| Orca | 把 `AGENTS.md` + 阶段提示词作为 worker task | 写作 worker 与核查 worker 分开 |

Claude Code 的斜杠命令：

```
/video-notes videos/第3讲.mp4        # 全流程（S3/S5 前会停下等确认）
/video-transcribe videos/第3讲.mp4   # 只做 S0–S2
/video-notes-write <slug>            # 从大纲/转写写笔记 + 深挖
/video-factcheck <slug>              # 独立内容核查（S4.6）
/video-slides <slug>                 # 从笔记生成课件
```

**写查分离**：S4.6 必须换一个上下文。Claude Code 用 Agent 工具起新 agent；Codex / Gemini
开新会话；Orca 另起 worker。不同厂商交叉核查更好（Claude 写、Codex 查，或反之）。

## 目录

```
videos/          原始视频（git 忽略）
work/<slug>/     中间产物（可重建）
output/<slug>/   交付物：notes.md、slides/index.html、slides.pdf、report.md
output/index.html 全套课时总索引
dist/            打包后的 zip（git 忽略）
scripts/         确定性脚本（ffmpeg / ASR / 抽帧 / 门禁 / 索引）
prompts/         可移植的阶段提示词
AGENTS.md        agent 无关的执行手册（唯一规范入口）
CLAUDE.md        Claude Code 入口
GEMINI.md        Gemini CLI 入口
.claude/         Claude Code 的 skills 与 slash commands（薄适配层）
docs/            需求文档与技术选型
```

## 设计原则

- 脚本只做确定性的事（探测、转写、抽帧、截图校验），agent 只做判断的事（大纲、写作、排版）。
- 规则只有一份：`AGENTS.md` + `prompts/`；`.claude/` 等目录只做宿主适配，不复制规则。
- 每阶段幂等、产物落盘、可单步重跑；改大纲不必重跑转写。
- 全流程本地：视频、音频、抽帧不出本机；只有转写文本与关键帧进入 agent 上下文。
- 课件完全离线，不依赖 CDN。

## 边界

- 只处理**本地**视频；不做在线平台下载。
- 只面向**以讲解为主**的视频；无音轨的纯演示视频会在 S0 明确报错。
- 版权归视频作者/使用者，请只处理自有或已授权素材。

## 许可

本仓库自写代码与文档；依赖与参考项目的许可证见 [`docs/技术选型.md`](docs/技术选型.md)。
