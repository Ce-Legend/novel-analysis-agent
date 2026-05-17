# 长任务里踩过的坑

长篇小说拆解很容易从一个脚本变成一个长跑任务。真正麻烦的地方经常发生在第 40 章、第 60 章，或者重启以后。

## 断点续跑

章节分析会增量写入 `chapter_analysis.jsonl`。如果中途断掉，重新运行同一个 `run_id` 时，会跳过已经成功的章节，继续补剩下的章节。

失败章节会写到：

```text
03_chapter_analysis/chapter_failures.jsonl
```

这样我可以区分两类情况：

- 模型临时失败，重跑可能恢复。
- 某一章内容或格式一直触发失败，需要单独处理。

## 幂等写入

我之前遇到过一个很隐蔽的问题：同一个 `run_id` 被启动了两次，两个进程都在写 `chapter_analysis.jsonl`。

结果看起来像章节数变多了，后面全书聚合也被污染。

后来处理方式是：

- 按 `chapter_id` 写入，恢复时自动去重。
- 同一个 `run_id` 加运行锁。
- stale lock 可以回收，正常退出会释放锁。

## 成本和耗时统计

长任务如果没有统计，很难知道钱花在哪里。

这个项目会写：

```text
06_eval/stage_stats.json
06_eval/stage_stats_history.jsonl
06_eval/run_summary.json
```

我一般看：

- 总调用次数。
- 每个阶段调用次数。
- 输入输出 token。
- 总耗时。
- 是否走了降级路径。
- 是否用了长上下文 file id。

## 切章质量

切章会影响所有后续结果。

如果原文标题格式很乱，代码会降级成分块章节。这个选择能保证流程跑完，但质量检查里会把风险写出来。

排查入口：

```text
02_split/chapters.jsonl
06_eval/chapter_split_diagnostics.json
06_eval/quality_review.json
```

看到降级切块以后，我通常会先处理切章，再看提示词。

## 导出重建

分析结果已经跑完时，最好不要因为导出层改了一点就重跑整本书。

所以我加了：

```bash
analyze-book finalize-delivery --run-dir runs/sample_novel/demo
```

它只会基于现有结构化结果重建 Markdown、Docx、PDF 和质量检查文件。

