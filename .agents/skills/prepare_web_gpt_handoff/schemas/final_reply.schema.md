# final_reply.md Schema Notes

`reply_template.md` 要求网页版 GPT 在最终收口时输出一个可直接保存为 `final_reply.md` 的 Markdown 文档。为了便于未来回灌校验，必须满足以下规则：

## YAML Front Matter

必须包含以下字段：

- `schema_version`
- `handoff_id`
- `topic`
- `mode`
- `source_provider`
- `source_channel`
- `generated_at`
- `generated_from`
- `reply_template_version`
- `language`
- `contains_external_sources`
- `status`

其中：

- `handoff_id` 必须与对应 `manifest.json` 中的 `handoff_id` 完全一致
- `generated_from` 推荐固定为 `prepare_web_gpt_handoff`
- `status` 推荐使用 `final`

## 正文标题

正文必须严格包含以下九个二级标题，并保持顺序不变：

1. `## 1. 问题定义`
2. `## 2. 最终结论`
3. `## 3. 推荐路线`
4. `## 4. 备选路线`
5. `## 5. 关键依据`
6. `## 6. 风险与反例`
7. `## 7. 候选论文/资料`
8. `## 8. 建议下一步`
9. `## 9. 仍未解决的问题`

## 回灌关联要求

未来如需回灌到 Codex，必须优先通过 `handoff_id` 做显式关联，不依赖会话记忆或隐式上下文。
