# video-md-ppt

把本地视频变成**带时间戳的 Markdown 笔记**，再把笔记变成**可离线放映的 HTML 课件**。
一条在 Claude Code 里分步执行、每步可人工干预的流水线。

> 需求与设计：[`docs/需求文档.md`](docs/需求文档.md)
> 选型依据与许可证：[`docs/技术选型.md`](docs/技术选型.md)

## 状态

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 骨架、配置、状态机、S0 预处理 | ✅ 已完成 |
| M1 | S1 转写、S2 抽帧 | ✅ 脚本完成并冒烟通过（CPU/tiny） |
| M2 | S3 大纲、S4 笔记 | ✅ 真实样例通过（覆盖率 100%，笔记门禁 PASS） |
| M3 | S4.5 知识深挖、S4.6 内容核查、S5 HTML 课件 | ✅ 22 张深挖卡 + 独立核查表；58 页单文件 HTML + PDF + 逐页 PNG，自检通过 |
| M4 | 批量、自动自检、字体子集 | ⏳ 待开始（单文件打包已提前完成） |

## 技术选型（摘要）

| 层 | 选型 |
|---|---|
| 转写 | faster-whisper + large-v3（显式 `zh`、VAD、词级时间戳、热词） |
| 抽帧 | scene + 间隔采样 → dHash 聚类 → 像素复核 → 最短停留过滤 |
| 大纲 | 自建 `outline-grill`：设计树追问 + 时间戳证据 |
| 笔记 | 证据表 + `verify_notes.py` / `check_outline.py` 门禁 |
| 深挖 | `work/<slug>/enrichment.md`：视频 / 推演 / 扩展三级来源，`check_enrichment.py` 门禁 |
| 核查 | 独立子代理查错 → `fact-check.md`（ERROR/WEAK/CONTESTED），`check_factcheck.py` 门禁 |
| 课件 | Marp CLI 单文件 HTML（备选 reveal.js），深挖页带来源角标 |

理由、license 与未验证项见 [`docs/技术选型.md`](docs/技术选型.md)。

## 快速开始

```bash
python scripts/doctor.py                      # 环境自检
python scripts/fetch_model.py large-v3        # 预下载模型（镜像 + 断点续传）
python scripts/probe.py videos/第3讲.mp4       # S0：探测 + 抽音频
python scripts/transcribe.py videos/第3讲.mp4  # S1：转写（默认 large-v3）
python scripts/keyframes.py videos/第3讲.mp4   # S2：抽帧
python scripts/status.py                      # 查看进度

# 门禁（失败时退出码 1）
python scripts/check_outline.py work/<slug>/outline.md
python scripts/verify_notes.py output/<slug>/notes.md --slug <slug>
python scripts/check_enrichment.py work/<slug>/enrichment.md
python scripts/check_factcheck.py work/<slug>/fact-check.md --enrichment work/<slug>/enrichment.md --slides output/<slug>/slides/slides.md

# 转写纠错（可选，TSV：错误<TAB>正确<TAB>备注）
python scripts/apply_corrections.py <slug> --rules work/<slug>/corrections.tsv
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

## 在 Claude Code 中使用

```
/video-notes videos/第3讲.mp4        # 全流程（S3/S5 前会停下等确认）
/video-transcribe videos/第3讲.mp4   # 只做 S0–S2
/video-notes-write <slug>            # 从大纲/转写写笔记
/video-slides <slug>                 # 从笔记生成课件
```

技能文件在 `.claude/skills/video-notes/SKILL.md`，规定了产物位置、写作规范与质量门槛。

## 目录

```
videos/          原始视频（git 忽略）
work/<slug>/     中间产物（可重建）
output/<slug>/   交付物：notes.md、slides/index.html
scripts/         确定性脚本（ffmpeg / ASR / 抽帧 / 校验）
.claude/         skills 与 slash commands
docs/            需求文档与技术选型
```

## 设计原则

- 脚本只做确定性的事（探测、转写、抽帧、截图校验），Claude 只做判断的事（大纲、写作、排版）。
- 每阶段幂等、产物落盘、可单步重跑；改大纲不必重跑转写。
- 全流程本地：视频、音频、抽帧不出本机；只有转写文本与关键帧进入 Claude 上下文。
- 课件完全离线，不依赖 CDN。

## 边界

- 只处理**本地**视频；不做在线平台下载。
- 只面向**以讲解为主**的视频；无音轨的纯演示视频会在 S0 明确报错。
- 版权归视频作者/使用者，请只处理自有或已授权素材。
