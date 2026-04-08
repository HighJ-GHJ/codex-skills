# Handoff Bundle

## 1. 问题定义与 handoff 目标
- mode: `strategy_research`
- topic: `为 sample_project 准备网页版 GPT 研究交接包`
- 任务目标: 把当前策略问题与最小必要材料整理给网页版 GPT 继续研究
- 关键关注点: 保持 minimal_sufficient_context；明确 handoff_id 回显与最终收口格式；把任务维持在策略讨论而不是代码实现

## 2. 关键 contract 与输出约束
### schemas/manifest.schema.json
- 文件路径: `schemas/manifest.schema.json`
- context_layer: `stable_contract`
- artifact_type: `contract`
- 选入原因: User explicitly requested this artifact. Contract artifact that defines output shape, prompt framing, or handoff policy.
- 摘录锚点: $schema, title, required, properties.status, properties.paths.required, properties.artifacts
- 原始 token 数: 245
- 选入 token 数: 234
- excerpt_strategy: `key_block_extract`
- compaction_strategy: `none`
- 截断说明: key_block_extract

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema"
}

{
  "title": "sample_project handoff manifest"
}

{
  "required": [
    "handoff_id",
    "status",
    "paths",
    "artifacts"
  ]
}

{
  "properties": {
    "status": {
      "type": "string",
      "enum": [
        "preview",
        "confirmed"
      ]
    }
  }
}

{
  "properties": {
    "paths": {
      "required": [
        "handoff_dir",
        "attachments_dir"
      ]
    }
  }
}

{
  "properties": {
    "artifacts": {
      "type": "object",
      "required": [
        "brief_md",
        "bundle_md",
        "reply_template_md"
      ],
      "properties": {
        "brief_md": {
          "type": "string"
        },
        "bundle_md": {
          "type": "string"
        },
        "reply_template_md": {
          "type": "string"
        }
      }
    }
  }
}
```

### templates/reply_template.md
- 文件路径: `templates/reply_template.md`
- context_layer: `stable_contract`
- artifact_type: `contract`
- 选入原因: User explicitly requested this artifact. Contract artifact that defines output shape, prompt framing, or handoff policy.
- 摘录锚点: Sample Project Reply Template, Output Contract, Required Sections
- 原始 token 数: 85
- 选入 token 数: 84
- excerpt_strategy: `section_extract`
- compaction_strategy: `none`
- 截断说明: section_extract

```markdown
# Sample Project Reply Template

## Output Contract

- Return a Markdown document that starts with YAML front matter.
- Repeat the `handoff_id` exactly.
- Set `status` to either `draft` or `final`.

## Required Sections

1. Problem Definition
2. Final Recommendation
3. Alternative Options
4. Key Evidence
5. Risks And Open Questions
6. Suggested Next Steps
```

## 3. 工作流与状态变迁
### src/workflow.py
- 文件路径: `src/workflow.py`
- context_layer: `evidence`
- artifact_type: `workflow`
- 选入原因: User explicitly requested this artifact. Workflow artifact that controls handoff creation, preview, or confirmation state.
- 摘录锚点: <imports>, HandoffState, build_preview_state, confirm_state
- 原始 token 数: 119
- 选入 token 数: 112
- excerpt_strategy: `symbol_extract`
- compaction_strategy: `none`
- 截断说明: symbol_extract

```python
from __future__ import annotations

from dataclasses import dataclass

class HandoffState:
    status: str
    recommended_send_order: tuple[str, ...]

def build_preview_state() -> HandoffState:
    return HandoffState(
        status="preview",
        recommended_send_order=("brief.md", "bundle.md", "reply_template.md"),
    )

def confirm_state(state: HandoffState) -> HandoffState:
    return HandoffState(
        status="confirmed",
        recommended_send_order=state.recommended_send_order,
    )
```

## 4. 关键代码片段
### src/selector.py
- 文件路径: `src/selector.py`
- context_layer: `evidence`
- artifact_type: `selection_logic`
- 选入原因: User explicitly requested this artifact. Selection logic artifact that determines ranking, extraction, or budget behavior.
- 摘录锚点: <imports>, Candidate, rank_candidates
- 原始 token 数: 186
- 选入 token 数: 182
- excerpt_strategy: `symbol_extract`
- compaction_strategy: `none`
- 截断说明: symbol_extract

```python
from __future__ import annotations

from dataclasses import dataclass

class Candidate:
    path: str
    priority: int
    reason: str

def rank_candidates(paths: list[str]) -> list[Candidate]:
    ranked: list[Candidate] = []
    for path in paths:
        if path.endswith(".md"):
            ranked.append(Candidate(path=path, priority=1, reason="Documentation explains project context."))
        elif path.endswith(".py"):
            ranked.append(Candidate(path=path, priority=2, reason="Code shows the current implementation shape."))
        elif path.endswith(".log"):
            ranked.append(Candidate(path=path, priority=3, reason="Log summary captures recent signals."))
        else:
            ranked.append(Candidate(path=path, priority=4, reason="Fallback context."))
    return sorted(ranked, key=lambda item: (item.priority, item.path))
```

## 5. 支撑材料与补充上下文
### docs/overview.md
- 文件路径: `docs/overview.md`
- context_layer: `evidence`
- artifact_type: `supporting_context`
- 选入原因: User explicitly requested this artifact. Supporting context artifact that helps frame the task without defining the contract.
- 摘录锚点: Sample Project Overview
- 原始 token 数: 131
- 选入 token 数: 131
- excerpt_strategy: `section_extract`
- compaction_strategy: `none`
- 截断说明: section_extract

```markdown
# Sample Project Overview

The sample project explores how to package a local strategy discussion so that a web GPT session can continue the reasoning without direct access to the Codex thread.

Current constraints:

- The handoff package must stay lightweight and portable.
- The manifest must remain machine-readable and use only repo-relative paths.
- The workflow must separate preview from final confirmation.
- The result should help continue research and option comparison, not trigger direct code implementation.

The current team concern is that too much context makes the handoff noisy, while too little context makes the external model miss important assumptions. The sample exists to show how the skill balances that trade-off.
```

### docs/research_questions.md
- 文件路径: `docs/research_questions.md`
- context_layer: `evidence`
- artifact_type: `supporting_context`
- 选入原因: User explicitly requested this artifact. Supporting context artifact that helps frame the task without defining the contract.
- 摘录锚点: Research Questions
- 原始 token 数: 142
- 选入 token 数: 141
- excerpt_strategy: `section_extract`
- compaction_strategy: `none`
- 截断说明: section_extract

```markdown
# Research Questions

The web GPT follow-up should help answer these questions:

1. How should we define the minimal sufficient context for a strategy handoff?
2. Which files belong in the main reading layer, and which ones should remain attachment-only?
3. What should the final reply template require so the output can be saved as `final_reply.md` and later validated by `handoff_id`?
4. How can we make the preview phase clear enough that a user can confidently confirm or regenerate the package?

Known non-goals:

- Do not automate browser sending.
- Do not rely on hidden local state or login profiles.
- Do not rewrite the task as “just implement the feature”.
```

### README.md
- 文件路径: `README.md`
- context_layer: `evidence`
- artifact_type: `supporting_context`
- 选入原因: User explicitly requested this artifact. Supporting context artifact that helps frame the task without defining the contract.
- 摘录锚点: Sample Project, 演示目标, 示例内容
- 原始 token 数: 775
- 选入 token 数: 392
- excerpt_strategy: `section_extract`
- compaction_strategy: `none`
- 截断说明: section_extract

```markdown
# Sample Project

这个示例项目用于演示 `prepare_web_gpt_handoff` skill 的真实输入形态。它假设团队正在做一个“把本地策略讨论转交给网页版 GPT 继续研究”的小工具原型，目前需要决定文件选择策略、预览确认流程以及最终回灌约束。

## 演示目标

- 展示 skill 如何从一个小型项目中挑选最小必要文件
- 展示 `brief.md` 与 `bundle.md` 的内容层次
- 展示 `manifest.json` 如何记录稳定的 `handoff_id` 和文件明细
- 展示确认交付后推荐发送顺序的正式报告
- 展示 contract-first 分层打包、结构化代码片段摘录与 typed digest compaction

## 示例内容

- `docs/overview.md`: 项目背景与当前问题
- `docs/research_questions.md`: 希望网页版 GPT 重点帮助回答的问题
- `schemas/manifest.schema.json`: 示例 handoff manifest 的最小 contract
- `templates/reply_template.md`: 示例 reply contract
- `src/workflow.py`: preview / confirm 状态流原型
- `src/selector.py`: 文件筛选与优先级逻辑原型
- `src/handoff_builder.py`: 打包阶段的原型代码
- `logs/strategy.log`: 讨论过程中沉淀出的关键信号
```

### logs/strategy.log
- 文件路径: `logs/strategy.log`
- context_layer: `evidence`
- artifact_type: `supporting_context`
- 选入原因: User explicitly requested this artifact. Supporting context artifact that helps frame the task without defining the contract.
- 摘录锚点: 无
- 原始 token 数: 114
- 选入 token 数: 113
- excerpt_strategy: `full_text`
- compaction_strategy: `none`
- 截断说明: full_text

```text
2026-04-06T18:10:00+08:00 INFO Need a clearer preview before asking for confirmation
2026-04-06T18:11:30+08:00 INFO Main reading layer should prefer docs, then core code, then concise logs
2026-04-06T18:12:05+08:00 WARN Previous attempts packed too much low-signal context
2026-04-06T18:12:44+08:00 INFO final_reply.md must echo handoff_id for future validation
```

## 6. 风险、缺口与待验证点
- 当前没有额外的风险或待验证点记录。
