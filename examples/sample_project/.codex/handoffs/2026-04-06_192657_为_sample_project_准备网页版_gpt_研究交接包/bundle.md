# Handoff Bundle

## 1. 项目背景
本次 handoff 聚焦于“为 sample_project 准备网页版 GPT 研究交接包”，模式为 `strategy_research`。主阅读层坚持 minimal_sufficient_context 原则，优先保留能帮助网页版 GPT 快速进入问题空间的材料。

## 2. 当前问题定义
保持 minimal_sufficient_context；明确 handoff_id 回显与最终收口格式；把任务维持在策略讨论而不是代码实现

## 3. 关键文档摘录
### README.md
- 文件路径: `README.md`
- 选入原因: User explicitly requested this file.
- 原始字符数: 607
- 选入字符数: 606
- 截断说明: full_text

```markdown
# Sample Project

这个示例项目用于演示 `prepare_web_gpt_handoff` skill 的真实输入形态。它假设团队正在做一个“把本地策略讨论转交给网页版 GPT 继续研究”的小工具原型，目前需要决定文件选择策略、预览确认流程以及最终回灌约束。

## 演示目标

- 展示 skill 如何从一个小型项目中挑选最小必要文件
- 展示 `brief.md` 与 `bundle.md` 的内容层次
- 展示 `manifest.json` 如何记录稳定的 `handoff_id` 和文件明细
- 展示确认交付后推荐发送顺序的正式报告

## 示例内容

- `docs/overview.md`: 项目背景与当前问题
- `docs/research_questions.md`: 希望网页版 GPT 重点帮助回答的问题
- `src/selector.py`: 文件筛选与优先级逻辑原型
- `src/handoff_builder.py`: 打包阶段的原型代码
- `logs/strategy.log`: 讨论过程中沉淀出的关键信号

## 已提交的真实 handoff 快照

生成后的示例快照会保存在本项目根目录下的 `.codex/handoffs/`。这个快照是为了给 GitHub 读者展示产物形态而提交的静态样本，不改变 skill 运行时默认输出目录的约束。
```

### docs/overview.md
- 文件路径: `docs/overview.md`
- 选入原因: User explicitly requested this file.
- 原始字符数: 740
- 选入字符数: 739
- 截断说明: full_text

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
- 选入原因: User explicitly requested this file.
- 原始字符数: 668
- 选入字符数: 667
- 截断说明: full_text

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

## 4. 关键代码摘录
### src/selector.py
- 文件路径: `src/selector.py`
- 选入原因: User explicitly requested this file.
- 原始字符数: 873
- 选入字符数: 844
- 截断说明: head_tail_chars:585+219

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
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
        elif path.endswith("

...[truncated for bundle preview]...

eason="Log summary captures recent signals."))
        else:
            ranked.append(Candidate(path=path, priority=4, reason="Fallback context."))
    return sorted(ranked, key=lambda item: (item.priority, item.path))
```

### src/handoff_builder.py
- 文件路径: `src/handoff_builder.py`
- 选入原因: Core implementation file relevant to the topic.
- 原始字符数: 331
- 选入字符数: 330
- 截断说明: full_text

```python
from __future__ import annotations

from pathlib import Path


def relative_paths(paths: list[Path], project_root: Path) -> list[str]:
    return [path.resolve().relative_to(project_root.resolve()).as_posix() for path in paths]


def recommended_send_order() -> list[str]:
    return ["brief.md", "bundle.md", "reply_template.md"]
```

## 5. 配置/日志摘要
### logs/strategy.log
- 文件路径: `logs/strategy.log`
- 选入原因: User explicitly requested this file.
- 原始字符数: 362
- 选入字符数: 361
- 截断说明: full_text

```text
2026-04-06T18:10:00+08:00 INFO Need a clearer preview before asking for confirmation
2026-04-06T18:11:30+08:00 INFO Main reading layer should prefer docs, then core code, then concise logs
2026-04-06T18:12:05+08:00 WARN Previous attempts packed too much low-signal context
2026-04-06T18:12:44+08:00 INFO final_reply.md must echo handoff_id for future validation
```

## 6. 已有想法与疑问
- 保持 minimal_sufficient_context
- 明确 handoff_id 回显与最终收口格式
- 把任务维持在策略讨论而不是代码实现
