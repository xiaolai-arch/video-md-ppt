---
description: 从笔记生成离线 HTML 课件（S5，Marp 渲染）
argument-hint: <slug | notes.md 路径> [--theme light|dark] [--auto]
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

> `--auto` 只是斜杠命令的宿主约定（等价于用户说“跳过确认”），不是 `scripts/*.py` 的参数。

执行 S5。参数 `$ARGUMENTS`。

前置：`output/<slug>/notes.md` 已通过 S4 自检（`verify_notes.py` 为 PASS）；
`work/<slug>/enrichment.md` 已通过 `check_enrichment.py`；
`work/<slug>/fact-check.md` 的 **A 轮预检**已通过（`check_factcheck.py --allow-no-slides`）。
课件草稿写完后，还要跑 S4.6-B 逐页核查，再定稿渲染。

1. **课时规划**：写 `work/<slug>/slide-plan.md`，每页包含：
   标题（结论式）/ 3–5 个要点 / 配图（来自 `notes.assets/`）/ 讲者备注 / 来源时间戳。
   遵循需求文档 §9.2 页面类型与 §9.3 密度规则（每页 ≤5 要点、≤7 行、宁可拆页）。
   - 深挖页单独列出：原理页（为什么）、对比页（正误）、迁移页（换题怎么用）、自测页。
   - 每个核心知识点至少一页深挖；45 分钟课 40–60 页属正常，不为凑页数灌水。
   - 除非 `--auto`，**停下等用户确认**页数与顺序。
2. **写源文件**：
   - `output/<slug>/slides/slides.md`：Marp Markdown，备注用 `<!-- 讲者备注：... -->`。
   - 每页角标来源：`<span class="src video">视频 12:34</span>` / `.src.infer` / `.src.ext`。
   - `output/<slug>/slides/theme.css`：中文排版主题（字体栈、行高 1.6–1.8、字号、标点），
     含 `.src` `.why` `.compare` `.flow` `.panel` 等深挖页样式。
3. **渲染**：
   ```bash
   npx -y @marp-team/marp-cli@4.5.1 --no-stdin output/<slug>/slides/slides.md \
     -o output/<slug>/slides/index.html --html \
     --theme output/<slug>/slides/theme.css --allow-local-files
   python scripts/inline_assets.py output/<slug>/slides/index.html
   npx -y @marp-team/marp-cli@4.5.1 --no-stdin output/<slug>/slides/slides.md \
     -o output/<slug>/slides/slides.pdf --pdf --pdf-notes \
     --allow-local-files --theme output/<slug>/slides/theme.css
   npx -y @marp-team/marp-cli@4.5.1 --no-stdin output/<slug>/slides/slides.md \
     --images png -o output/<slug>/slides/selfcheck \
     --allow-local-files --theme output/<slug>/slides/theme.css
   ```
   约束：单文件、零外链、禁止 CDN。`inline_assets.py` 必须执行（Marp 默认不内联图片）。
4. **自检**：
   - 双击 `index.html` 确认断网可开；`P` 键确认 presenter 备注。
   - 逐页 PNG 检查溢出、断行、缺图；必要时用 Playwright 量 `scrollWidth > clientWidth`。
   - 抽查 10 页：〔视频〕角标的时间戳能对上转写；〔扩展〕页没有“视频里说”。
   - 核对 `fact-check.md`：ERROR 已全部改完，CONTESTED 已在页面上可见标注。
   - 结果写入 `output/<slug>/report.md`（页数、每页字数、深挖页数、疑似过密页、截图路径）。
5. 汇报：总页数、深挖页数、核查问题数与处理结果、页均字数、自检结论、打开方式。

红线：视频原意不得改写；〔扩展〕内容必须角标可见，不能伪装成讲者观点；已知错误不得带进课件。
