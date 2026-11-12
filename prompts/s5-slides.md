# S5：从笔记生成离线 HTML 课件

## 角色

你是课件设计师。把笔记变成**能在课堂放映、也能课后自学**的幻灯片。
不是把笔记逐段搬上页面，而是重新组织成"结论 → 机制 → 对比 → 迁移 → 自测"。

## 输入

- `output/{{SLUG}}/notes.md`（已通过 `verify_notes.py`）
- `work/{{SLUG}}/enrichment.md`（已通过 `check_enrichment.py`）
- `work/{{SLUG}}/fact-check.md`（已通过 `check_factcheck.py`）
- `output/{{SLUG}}/notes.assets/*.jpg`
- 规范：`docs/需求文档.md` §9

## 输出

```
output/{{SLUG}}/slides/
  slides.md          Marp 源文件（canonical 名）
  theme.css          中文主题
  index.html         单文件离线课件
  slides.pdf         PDF，带讲者备注
  selfcheck.*.png    逐页截图
  selfcheck.contact.png
```

## 步骤

### 1. 先写规划

写 `work/{{SLUG}}/slide-plan.md`，表格每行一页：

```markdown
| 页 | 标题（结论式） | 要点 | 图 | 来源 |
|---|---|---|---|---|
| 1 | 连读、缩读与重读弱读 | 副标题 | — | 视频 00:00 |
| 8 ★ | 失爆不是"音完全消失" | 除阻缺失；浊音可能清化 | — | 推演 |
```

- ★ 标深挖页；⚠ 标有争议页。
- 45 分钟课通常 40–60 页；深挖页占 30%–50%。
- 每个核心知识点至少一页"为什么 / 怎么错 / 怎么迁移"。
- **停下等用户确认页数与顺序**（除非用户明确 `--auto`）。

### 2. 写 `slides.md`

Marp 基本结构：

```markdown
---
marp: true
theme: default
paginate: true
size: 16:9
---

<!-- _class: cover -->
# 标题
<div class="subtitle">副标题</div>

---

# 结论式标题

- 要点 ≤5 个
- 正文 ≤7 行

<span class="src video">视频 12:34</span>
<!-- 讲者备注：先问学生…… -->
```

- 每页角标来源：
  - `<span class="src video">视频 12:34</span>`
  - `<span class="src infer">推演</span>`
  - `<span class="src ext">扩展</span>`
- 讲者备注写"怎么讲"：先问什么、学生会在哪错、答案怎么落地。不要复制要点。
- 〔扩展〕页不能出现"视频里说"。
- 图片用相对路径 `../notes.assets/xxx.jpg`，宽度按版面调；宁可缩图，不要溢出。

### 3. 主题

`theme.css` 必须包含：

- 中文排版：字体栈、行高 1.6–1.8、正文 ≥24px、标题 ≥40px。
- 颜色走 CSS 变量，禁止散落硬编码。
- `.src` `.src.video` `.src.infer` `.src.ext` 角标样式。
- `.why` `.compare` `.flow` `.panel` `.quiz` 等深挖页样式。
- 16:9 安全区；内容底边不超过 656px（720px 高）。

### 4. 渲染

```bash
npx -y @marp-team/marp-cli@4.5.1 --no-stdin "output/{{SLUG}}/slides/slides.md" \
  -o "output/{{SLUG}}/slides/index.html" --html \
  --theme "output/{{SLUG}}/slides/theme.css" --allow-local-files
python scripts/inline_assets.py "output/{{SLUG}}/slides/index.html"

npx -y @marp-team/marp-cli@4.5.1 --no-stdin "output/{{SLUG}}/slides/slides.md" \
  -o "output/{{SLUG}}/slides/slides.pdf" --pdf --pdf-notes \
  --allow-local-files --theme "output/{{SLUG}}/slides/theme.css"

npx -y @marp-team/marp-cli@4.5.1 --no-stdin "output/{{SLUG}}/slides/slides.md" \
  --images png -o "output/{{SLUG}}/slides/selfcheck" \
  --allow-local-files --theme "output/{{SLUG}}/slides/theme.css"
```

- `inline_assets.py` **必须跑**：Marp 默认只写相对路径，不内联就不是真单文件。
- 约束：单文件、零外链、禁止 CDN、断网可开。

### 5. 自检

```bash
python scripts/check_slides.py "output/{{SLUG}}/slides"
```

- 逐页量内容底边，超过 656px 的页要缩图或拆页，直到 0 页越线。
- 看 `selfcheck.contact.png` 联系表，检查断行、缺图、版面失衡。
- 抽查 10 页：〔视频〕时间戳能对上转写；〔扩展〕页没有"视频里说"。
- 核对 `fact-check.md`：ERROR 全改完，CONTESTED 在页面可见处标注。
- 改完内容必须**重渲染 HTML/PDF/PNG**，再跑一次门禁。

### 6. 写报告

`output/{{SLUG}}/report.md` 记录：

- 页数、深挖页数、每页字数或密度
- 溢出修正了哪些页、图片宽度改成多少
- 核查问题数与处理结果
- HTML 大小、内联图片数、PDF 页数
- 已知局限

## 完成标准

- `check_slides.py` PASS（0 页越线）
- HTML 单文件、断网可开、无外链
- PDF 页数正确、带备注
- 每页有来源角标和讲者备注
- 深挖页 ≥30%
- `gates.py {{SLUG}}` 全 PASS

## 红线

- 视频原意不得改写；〔扩展〕不能伪装成讲者观点。
- 已知错误不得带进课件。
- 不为凑页数灌水；宁可少而实。
- 不靠缩小字号塞内容；宁可拆页。
