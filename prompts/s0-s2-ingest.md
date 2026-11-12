# S0–S2：预处理、转写、抽帧

## 角色

你是这条流水线的执行者。S0–S2 是**确定性工作**，全部交给脚本；你负责运行、核对产物、
在失败时定位原因。不要手写转写、不要自己挑帧图。

## 输入

- 视频：`{{VIDEO}}`（本地文件）
- 配置：`config.toml`

## 步骤

1. 环境与状态：

   ```bash
   python scripts/doctor.py
   python scripts/status.py
   ```

2. S0 探测与抽音频：

   ```bash
   python scripts/probe.py "{{VIDEO}}"
   ```

   产物：`work/<slug>/audio/audio.wav`、`meta.json`。
   报"没有音轨"就停止，告诉用户这个视频不适配当前流水线。

3. S1 转写：

   ```bash
   python scripts/transcribe.py "{{VIDEO}}"
   ```

   默认 faster-whisper large-v3、显式 `zh`、VAD、词级时间戳。
   首次运行需要模型；建议先 `python scripts/fetch_model.py large-v3`（走镜像、可续传）。

4. S2 抽帧：

   ```bash
   python scripts/keyframes.py "{{VIDEO}}"
   ```

5. 核对产物：

   ```bash
   python scripts/status.py --slug "{{SLUG}}"
   ls work/{{SLUG}}/transcript/
   ls work/{{SLUG}}/frames/ | head
   ```

6. 汇报给用户：
   - 转写语言、时长、段数、前 200 字
   - 关键帧数量、覆盖时段、`frames/index.json` 路径
   - 抽 3 个随机时间戳，请用户回听核对
   - 失败日志只贴尾部关键行，不整段转储

## 完成标准

- `status.py` 显示 `s0=done`、`s1=done`、`s2=done`
- `transcript/transcript.txt` 非空，`frames/` 有图

## 失败处理

读 `work/<slug>/logs/*.log` 的最后几十行，定位是 ffmpeg、模型、显存还是磁盘问题。
修因后重跑；需要覆盖已有产物时加 `--force`。不要绕过失败去写下游文件。

## 红线

- 不生成假转写、假帧图。
- 不修改 `transcript/*.json` 冒充脚本输出；要纠错走 `scripts/apply_corrections.py`。
- 不把视频、音频上传到外部服务。
