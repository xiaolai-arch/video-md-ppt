# Claude Code 入口

@AGENTS.md

## Claude 专属适配

- **独立核查**：S4.6 用 Agent 工具起一个不继承上下文的新 agent，提示词用
  `prompts/s4.6-factcheck.md`；不要用同一个会话自查。
- **斜杠命令**：`/video-notes`、`/video-transcribe`、`/video-notes-write`、`/video-slides`、
  `/video-factcheck`。命令只是薄壳，规则以 `AGENTS.md` + `prompts/` 为准。
- **技能**：`.claude/skills/video-notes/SKILL.md` 与 `.claude/skills/outline-grill/SKILL.md`
  是 Claude Code 的适配层。
- **Windows 控制台**：脚本输出 IPA 报 `UnicodeEncodeError` 时，命令前加
  `PYTHONIOENCODING=utf-8`（PowerShell：`$env:PYTHONIOENCODING='utf-8'`）。

## 最常用的三条命令

```bash
python scripts/status.py
python scripts/gates.py <slug>
python scripts/build_index.py
```
