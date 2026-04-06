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

你可以从这里直接查看示例入口：

- [DEMO.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/DEMO.md)
