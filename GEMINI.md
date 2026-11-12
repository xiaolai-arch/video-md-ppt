# Gemini CLI 入口

@AGENTS.md

本仓库的完整规则在 `AGENTS.md` 与 `prompts/`。Gemini CLI 会把本文件作为上下文；
若 `@AGENTS.md` 导入未生效，请直接读取仓库根目录的 `AGENTS.md`。

独立核查（S4.6）请开一个新会话，只提供以下文件与 `prompts/s4.6-factcheck.md`：

- `work/<slug>/transcript/transcript.txt`
- `output/<slug>/notes.md`
- `work/<slug>/enrichment.md`
- `output/<slug>/slides/slides.md`

示例：

```bash
gemini -p "读 AGENTS.md 与 prompts/s5-slides.md，为 <slug> 生成课件"
```
