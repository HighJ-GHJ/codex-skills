# Demo Walkthrough

这个文件指向一个已经真实生成并确认过的 handoff 快照，方便在 GitHub 中直接查看完整产物。

## 示例 handoff

- handoff_id: `2026-04-06_192657_为_sample_project_准备网页版_gpt_研究交接包`
- 状态: `confirmed`
- 目录: [examples/sample_project/.codex/handoffs/2026-04-06_192657_为_sample_project_准备网页版_gpt_研究交接包](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/.codex/handoffs/2026-04-06_192657_为_sample_project_准备网页版_gpt_研究交接包)

## 关键文件

- [brief.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/.codex/handoffs/2026-04-06_192657_为_sample_project_准备网页版_gpt_研究交接包/brief.md)
- [bundle.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/.codex/handoffs/2026-04-06_192657_为_sample_project_准备网页版_gpt_研究交接包/bundle.md)
- [manifest.json](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/.codex/handoffs/2026-04-06_192657_为_sample_project_准备网页版_gpt_研究交接包/manifest.json)
- [reply_template.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/.codex/handoffs/2026-04-06_192657_为_sample_project_准备网页版_gpt_研究交接包/reply_template.md)
- [notes.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/.codex/handoffs/2026-04-06_192657_为_sample_project_准备网页版_gpt_研究交接包/notes.md)
- [preview.json](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/.codex/handoffs/2026-04-06_192657_为_sample_project_准备网页版_gpt_研究交接包/preview.json)

## 生成命令

```bash
python .codex/skills/prepare_web_gpt_handoff/scripts/prepare_handoff.py \
  --project-root examples/sample_project \
  --mode strategy_research \
  --topic "为 sample_project 准备网页版 GPT 研究交接包" \
  --goal "把当前策略问题与最小必要材料整理给网页版 GPT 继续研究" \
  --focus-point "保持 minimal_sufficient_context" \
  --focus-point "明确 handoff_id 回显与最终收口格式" \
  --focus-point "把任务维持在策略讨论而不是代码实现" \
  --must-include README.md \
  --must-include docs/overview.md \
  --must-include docs/research_questions.md \
  --must-include src/selector.py \
  --must-include logs/strategy.log \
  --question "哪些材料应该进入主阅读层？" \
  --question "reply_template 应如何约束最终收口？" \
  --avoid-direction "不要自动化浏览器发送" \
  --avoid-direction "不要依赖本机登录态或隐式记忆" \
  --output-requirement "请给出推荐路线、备选路线、关键依据、风险与下一步建议" \
  --max-files 6 \
  --max-bundle-chars 7000
```

确认命令：

```bash
python .codex/skills/prepare_web_gpt_handoff/scripts/confirm_handoff.py \
  --project-root examples/sample_project \
  --handoff 2026-04-06_192657_为_sample_project_准备网页版_gpt_研究交接包
```
