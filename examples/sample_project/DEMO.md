# Demo Walkthrough

这个文件指向一个已经真实生成并确认过的 handoff 快照，方便在 GitHub 中直接查看完整产物。当前示例位于 `examples/sample_project/handoffs/`，稳定入口是 `examples/sample_project/handoffs/LATEST.md`。这份快照被当作 canonical sample / golden fixture 管理，而不是普通调试输出。

这份样例现在专门用来展示 contract-first context layering，因此主阅读层应同时包含：

- contract artifact
- workflow artifact
- selection / code snippet artifact
- supporting context

## 示例 handoff

- 稳定入口: `examples/sample_project/handoffs/LATEST.md`
- 当前已提交快照: `examples/sample_project/handoffs/2026-04-08_231715_为_sample_project_准备网页版_gpt_研究交接包/`
- 状态: `confirmed`

只有当 schema、目录结构、关键输出字段或 preview / confirm 行为发生变化时，才应该重生成并替换这份快照。

## 关键文件

- `handoffs/<handoff_id>/brief.md`
- `handoffs/<handoff_id>/bundle.md`
- `handoffs/<handoff_id>/manifest.json`
- `handoffs/<handoff_id>/reply_template.md`
- `handoffs/<handoff_id>/notes.md`
- `handoffs/<handoff_id>/preview.json`

## 生成命令

```bash
python -m prepare_web_gpt_handoff.prepare \
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
  --must-include schemas/manifest.schema.json \
  --must-include templates/reply_template.md \
  --must-include src/workflow.py \
  --must-include src/selector.py \
  --must-include logs/strategy.log \
  --question "哪些材料应该进入主阅读层？" \
  --question "reply_template 应如何约束最终收口？" \
  --avoid-direction "不要自动化浏览器发送" \
  --avoid-direction "不要依赖本机登录态或隐式记忆" \
  --output-requirement "请给出推荐路线、备选路线、关键依据、风险与下一步建议" \
  --max-files 8 \
  --require-exact-tokens \
  --max-bundle-tokens 4096
```

确认命令：

```bash
python -m prepare_web_gpt_handoff.confirm \
  --project-root examples/sample_project \
  --handoff handoffs/2026-04-08_231715_为_sample_project_准备网页版_gpt_研究交接包
```
