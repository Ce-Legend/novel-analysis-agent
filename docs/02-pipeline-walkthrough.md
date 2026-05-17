# 流水线怎么跑

一次完整运行会在 `runs/<book_id>/<run_id>/` 下生成固定目录。

```text
01_ingest/
02_split/
03_chapter_analysis/
04_aggregate/
05_export/
06_eval/
```

## 01_ingest

这一层把输入文件读进来，统一成规范化文本。

支持：

- `txt`
- `docx`
- `pdf`

产物：

```text
manifest.json
normalized.txt
```

`manifest.json` 记录输入类型、字数、文件路径和本次 run 的基础信息。后面排查问题时，这个文件很方便。

## 02_split

这一层负责切章节。

理想情况是识别出清晰章标题。遇到章标题稀疏、格式混乱、整本书只有几个超大段落时，代码会降级切块，并把诊断写出来。

产物：

```text
chapters.jsonl
chapter_split_diagnostics.json
```

我没有把降级切块藏起来。因为切章质量会直接影响后面的章节细纲和情感线，必须让它可见。

## 03_chapter_analysis

这一层逐章分析。

每章会生成：

- 剧情摘要。
- 事件列表。
- 危机、伏笔、悬念、高潮、爽点。
- 情节点与节奏。
- 名场面与金句。
- 情感状态。
- 关系推进。
- 文风信号。
- 证据片段。

产物：

```text
chapter_analysis.jsonl
chapter_failures.jsonl
chapter_status.json
stage_stats_history.jsonl
```

`chapter_analysis.jsonl` 按 `chapter_id` 幂等写入。同一个 `run_id` 恢复时，不会把同一章重复写成两份。

## 04_aggregate

这一层把章节结果汇总成全书分析。

如果配置了 `bailian-long`，这里会走文件上传和 file id 引用，适合更长的全书上下文。

产物：

```text
book_analysis.json
qwen_long_book_input.json
qwen_long_upload.json
```

`book_analysis.json` 是报告的结构化真值。后面的 Markdown、Docx、PDF 都从这里来。

## 05_export

这一层导出最终报告。

产物：

```text
book_analysis.md
book_analysis.docx
book_analysis.pdf
book_analysis.debug.md
```

`debug.md` 会保留更多调试痕迹，正式交付看前三个文件。

## 06_eval

这一层做质量检查。

产物：

```text
eval_report.json
quality_review.json
reference_alignment_review.json
delivery_integrity_review.json
run_summary.json
stage_stats.json
```

我最常看的两个文件：

- `run_summary.json`：任务跑到哪里了，有没有失败章节，成本和调用次数大概是多少。
- `quality_review.json`：最终报告有哪些覆盖项，哪里还有风险。

