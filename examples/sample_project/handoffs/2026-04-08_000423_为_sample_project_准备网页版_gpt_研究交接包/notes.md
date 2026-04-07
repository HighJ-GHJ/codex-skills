# Handoff Notes

- handoff_id: `2026-04-08_000423_为_sample_project_准备网页版_gpt_研究交接包`
- mode: `strategy_research`
- topic: `为 sample_project 准备网页版 GPT 研究交接包`

## Main Reading Layer
- README.md: evidence / supporting_context / User explicitly requested this artifact. Supporting context artifact that helps frame the task without defining the contract.
- docs/overview.md: evidence / supporting_context / User explicitly requested this artifact. Supporting context artifact that helps frame the task without defining the contract.
- docs/research_questions.md: evidence / supporting_context / User explicitly requested this artifact. Supporting context artifact that helps frame the task without defining the contract.
- schemas/manifest.schema.json: stable_contract / contract / User explicitly requested this artifact. Contract artifact that defines output shape, prompt framing, or handoff policy.
- templates/reply_template.md: stable_contract / contract / User explicitly requested this artifact. Contract artifact that defines output shape, prompt framing, or handoff policy.
- src/workflow.py: evidence / workflow / User explicitly requested this artifact. Workflow artifact that controls handoff creation, preview, or confirmation state.
- src/selector.py: evidence / selection_logic / User explicitly requested this artifact. Selection logic artifact that determines ranking, extraction, or budget behavior.
- logs/strategy.log: evidence / supporting_context / User explicitly requested this artifact. Supporting context artifact that helps frame the task without defining the contract.

## Attachment Decisions
- 本次没有 artifact 被压到 attachments/。

## Compaction And Fallback
- 当前主阅读层条目均未触发 compaction 或 fallback。

## Excluded Areas
- 默认排除了 data/、outputs/、依赖锁文件、大型二进制和全量日志原文。

## Confirmation Checklist
- 确认 brief.md 仍然只承载动态任务 framing，而不是实现需求。
- 确认 bundle.md 的 contract / workflow / code snippet 分层是否符合当前主题。
- 确认 typed digest 或 fallback 条目仍然保留了继续讨论所需的决策、约束与锚点。
- 确认 handoff_id 会在未来 final_reply.md 中被回显。
