# Novel Analysis Agent

长篇小说拆解流水线：把 `txt / docx / pdf` 小说拆成章节分析、人物关系、剧情大纲、情感线、文笔拆解，再导出 Markdown、Docx、PDF 报告。

[快速开始](#-快速开始) · [报告样例](examples/sample_report.md) · [质量检查](examples/quality_review.sample.json) · [设计记录](docs/01-story-and-decisions.md)

![报告预览](assets/report-preview-1.png)

## 30 秒看懂

| 输入 | 处理 | 输出 |
|---|---|---|
| 小说文本、Word、PDF | 切章、逐章抽取、全书聚合、报告修复、质量检查 | Markdown / Docx / PDF 拆书报告 |

适合参考的地方：

- 长文本怎么拆成可恢复的 LLM pipeline。
- 章节级分析和全书级聚合怎么分工。
- 最终报告怎么同时导出 Markdown、Docx、PDF。
- 长任务怎么留下进度、成本、失败章节和质量检查。

## 🚀 快速开始

默认用 `mock` provider，不需要 API Key，先看完整流程。

```bash
python3 -m pip install -e ".[dev]"
analyze-book --input tests/fixtures/sample_novel.txt --provider mock --export markdown,docx,pdf --run-id demo --force
```

跑完以后看这些文件：

```text
runs/sample_novel/demo/05_export/book_analysis.md
runs/sample_novel/demo/05_export/book_analysis.docx
runs/sample_novel/demo/05_export/book_analysis.pdf
runs/sample_novel/demo/06_eval/quality_review.json
runs/sample_novel/demo/06_eval/run_summary.json
```

## 🖼️ 报告效果

Markdown、Docx、PDF 从同一份报告结构生成，减少不同格式之间的内容漂移。

![报告预览 2](assets/report-preview-2.png)

可以直接看脱敏样例：

- [examples/sample_report.md](examples/sample_report.md)
- [examples/quality_review.sample.json](examples/quality_review.sample.json)
- [examples/run_summary.sample.json](examples/run_summary.sample.json)

## 🧩 Pipeline

```mermaid
flowchart LR
  A["输入小说 txt / docx / pdf"] --> B["规范化文本"]
  B --> C["章节切分"]
  C --> D["逐章结构化抽取"]
  D --> E["全书聚合"]
  E --> F["报告 AST"]
  F --> G["Markdown / Docx / PDF"]
  G --> H["质量检查"]
  H --> I["可交付报告"]
```

每一步都会落盘，长任务中断后可以继续跑。

```text
01_ingest/             输入清洗和 manifest
02_split/              章节切分结果
03_chapter_analysis/   逐章 JSONL、失败章节、进度
04_aggregate/          全书结构化分析
05_export/             Markdown、Docx、PDF
06_eval/               质量检查、运行摘要、成本统计
```

## 🔌 接真实模型

复制配置模板：

```bash
cp .env.example .env.local
```

填好自己的 Key 后运行：

```bash
analyze-book \
  --input path/to/your-novel.txt \
  --provider openai \
  --profile mvp \
  --export markdown,docx,pdf \
  --run-id first-full-run
```

我实践下来更喜欢分层使用模型：

| 阶段 | 推荐配置 | 原因 |
|---|---|---|
| 章节分析 | `qwen-plus` | 适合多次结构化抽取 |
| 全书聚合 | `qwen-long` | 适合更长上下文合并 |
| 质量检查 | `qwen-flash` | 成本低，适合扫明显问题 |

## 我为什么这样做

最开始我以为难点在 prompt。跑过长篇以后，真正麻烦的地方变成了稳定性和可复查性。

一本小说太长，直接丢给模型很容易前细后粗。拆书报告又有很多固定栏目：剧情大纲、章节细纲、情感线、CP 感分析、人物小传、文笔拆解。任何一个模块空掉，整份报告都会显得不可信。

所以我把任务拆成多层：

- 章节先抽取，保留细节。
- 全书再聚合，负责组织。
- 导出层只管渲染，Markdown、Docx、PDF 共用同一份结构。
- 质量检查单独跑，把残句、弱占位、内部字段、模块缺失抓出来。

更完整的过程写在 [docs/01-story-and-decisions.md](docs/01-story-and-decisions.md)。

## 质量检查会看什么

`quality_review.json` 会检查：

- Docx 和 PDF 是否生成。
- 顶层模块顺序是否稳定。
- 报告里有没有内部字段。
- 人物小传是否达到人物卡结构。
- CP 感分析是否有足够专题。
- 情感线是否有阶段锚点。
- 章节细纲数量是否匹配。
- 文笔模块有没有拆解维度。
- 是否存在弱占位、残句、截断尾巴。

## 长任务调试入口

跑整本书时，我一般先看这些文件：

```text
03_chapter_analysis/chapter_status.json
03_chapter_analysis/chapter_analysis.jsonl
03_chapter_analysis/chapter_failures.jsonl
06_eval/run_summary.json
06_eval/stage_stats.json
06_eval/quality_review.json
```

`run_summary.json` 看进度和成本，`quality_review.json` 看报告能不能发出去。

## 重新生成最终交付

章节分析和全书聚合已经跑完时，可以只重建导出和质量检查：

```bash
analyze-book finalize-delivery \
  --run-dir runs/sample_novel/demo \
  --export markdown,docx,pdf
```

会重建：

```text
05_export/book_analysis.md
05_export/book_analysis.docx
05_export/book_analysis.pdf
06_eval/quality_review.json
06_eval/reference_alignment_review.json
06_eval/delivery_integrity_review.json
```

## 文档

- [docs/01-story-and-decisions.md](docs/01-story-and-decisions.md)：这个工具怎么从一次交付需求长出来。
- [docs/02-pipeline-walkthrough.md](docs/02-pipeline-walkthrough.md)：每个阶段做什么。
- [docs/03-report-contract.md](docs/03-report-contract.md)：最终报告覆盖哪些模块。
- [docs/04-long-run-notes.md](docs/04-long-run-notes.md)：长任务、断点续跑、重复写入、运行锁。

## 验证

```bash
python3 -m pytest -q
```

当前保留的回归：

- `mock` provider 跑完整链路。
- 同一个 `run_id` 断点续跑。
- 章节失败后记录失败项。
- 导出 Markdown、Docx、PDF。
- 报告里不暴露内部技术字段。
- 质量检查能识别模块缺失、弱占位、导出版式风险。

## License

MIT
