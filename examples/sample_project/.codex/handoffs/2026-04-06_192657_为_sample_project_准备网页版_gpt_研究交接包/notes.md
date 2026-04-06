# Handoff Notes

- handoff_id: `2026-04-06_192657_为_sample_project_准备网页版_gpt_研究交接包`
- mode: `strategy_research`
- topic: `为 sample_project 准备网页版 GPT 研究交接包`

## Scope Decisions
- 主阅读层选入 6 个文件，优先保留显式指定、讨论提及和高价值上下文材料。
- attachments/ 中保留了选中文件的完整副本，便于后续人工补查。

## Truncation Notes
- src/selector.py: head_tail_chars:585+219

## Excluded Areas
- 默认排除了 data/、outputs/、依赖锁文件、大型二进制和全量日志原文。

## Confirmation Checklist
- 确认 brief.md 是否准确表达了策略讨论目标，而不是实现任务。
- 确认 bundle.md 中的主阅读材料是否足够且不过量。
- 确认 handoff_id 会在未来 final_reply.md 中被回显。
