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

## 已提交的真实 handoff 快照

生成后的示例快照会保存在本项目根目录下的 `handoffs/`。这个快照不是随手提交的临时产物，而是为了给 GitHub 读者展示输出 contract 而维护的 canonical sample / golden fixture，也与当前默认输出目录保持一致。

推荐使用仓库根包入口生成它，而不是直接依赖旧的 `scripts/*.py` 路径：

```bash
python -m prepare_web_gpt_handoff.prepare --project-root examples/sample_project ...
```

当前 canonical sample 会显式覆盖三类材料：

- contract artifact
- workflow artifact
- supporting context / code snippet

维护规则：

- `handoffs/` 中只保留一份 canonical sample handoff
- `LATEST.md` 必须稳定指向这份 canonical sample
- 只有当 schema、关键输出字段、目录结构或 preview / confirm 行为发生变化时才重生成
- 更新 sample 时要连同 diff 一起审阅，而不是直接覆盖

你可以从这里直接查看示例入口：

- [DEMO.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/DEMO.md)
- [LATEST.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/handoffs/LATEST.md)
