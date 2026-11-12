---
description: 独立核查视频笔记与课件的知识准确性（S4.6）
argument-hint: <slug>
allowed-tools: Agent, Read, Write, Edit, Glob, Grep, Bash
---

执行 S4.6 内容核查。参数 `$ARGUMENTS`（slug）。

前置：`work/<slug>/enrichment.md` 已通过 `check_enrichment.py`；
`output/<slug>/notes.md` 与 `output/<slug>/slides/slides.md` 已生成。
课件源文件唯一 canonical 名为 `slides/slides.md`；旧名 `slides.rich.md` 已统一。

1. **起独立子代理**：用 Agent 起一个不继承当前推理上下文的核查员，只给它四个文件：
   `transcript.txt`、`notes.md`、`enrichment.md`、`slides.md`。
   提示词要求：
   - 假设一定有错，按 ERROR / WEAK / OK 判定；
   - 查事实错误、过度概括、争议规则、错误归因、内部矛盾、英文例句自然度；
   - 不因“讲者这么说”就判 OK；
   - 区分考试约定与标准语法；
   - 只报告，不改文件。
2. **整理成表** `work/<slug>/fact-check.md`：
   `| ID | 位置 | 主张 | 类型 | 判定 | 说明 | 处理 |`
   - 位置写 E01 或 p13；
   - ERROR 必须有具体处理；
   - CONTESTED 必须写明在课件哪里标注；
   - 覆盖所有 E 卡与所有带 `.src.ext` 的页面。
3. **处理问题**：
   - ERROR：改 enrichment / notes / slides；
   - WEAK：收紧措辞，补“通常/多数/考试按……”；
   - CONTESTED：在课件可见位置加注，不能只写讲者备注；
   - 视频本身的错误或简化：标“讲者的简化/口误”，不照抄。
4. **门禁**：
   ```bash
   python scripts/check_factcheck.py work/<slug>/fact-check.md \
     --enrichment work/<slug>/enrichment.md \
     --slides output/<slug>/slides/slides.md
   ```
5. 改完重渲染课件，再跑 `check_slides.py`；把核查结果写进 `report.md`。

红线：核查员与写作者必须分离；不得用“已人工确认”代替具体依据；ERROR 不得留在课件里。