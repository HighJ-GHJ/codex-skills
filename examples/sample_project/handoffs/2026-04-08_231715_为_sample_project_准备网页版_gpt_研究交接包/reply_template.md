# Web GPT Final Reply Template

请在多轮讨论结束后，仅输出一个可直接保存为 `final_reply.md` 的 Markdown 文档。不要附加聊天式寒暄，不要省略 YAML front matter，并且必须回显本次 handoff 的 `handoff_id`。

填写要求：

- `contains_external_sources` 必须如实反映是否使用了外部资料
- `generated_at` 使用 ISO-8601 时间戳
- `status` 默认写 `final`
- 正文必须严格包含下面九个二级标题，顺序不要改动

```md
---
schema_version: "1.0"
handoff_id: "2026-04-08_231715_为_sample_project_准备网页版_gpt_研究交接包"
topic: "为 sample_project 准备网页版 GPT 研究交接包"
mode: "strategy_research"
source_provider: "OpenAI"
source_channel: "web_gpt"
generated_at: "<ISO-8601>"
generated_from: "prepare_web_gpt_handoff"
reply_template_version: "0.2.0"
language: "zh-CN"
contains_external_sources: false
status: "final"
---

## 1. 问题定义

## 2. 最终结论

## 3. 推荐路线

## 4. 备选路线

## 5. 关键依据

## 6. 风险与反例

## 7. 候选论文/资料

## 8. 建议下一步

## 9. 仍未解决的问题
```
