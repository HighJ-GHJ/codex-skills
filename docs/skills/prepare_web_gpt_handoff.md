<!--
中文说明：当前生产级 handoff skill 的独立说明页。

根 README 只负责仓库级导航，这里承载 prepare_web_gpt_handoff 的运行边界、
命令入口、输出契约和 sample 说明，避免单 skill 细节重新膨胀回仓库首页。
-->

# prepare_web_gpt_handoff

## 作用与边界

`prepare_web_gpt_handoff` 用于把当前 Codex 中的策略讨论、方案比较或研究线程整理成可发送给 web GPT 的 handoff 包。它只负责上下文打包，不负责自动打开网页、自动发送消息，也不承担回复回灌。

当前 skill 的稳定边界：

- 采用 `contract-first` selector
- 默认启用 graph-assisted selector 作为内部增强
- graph 只服务候选扩展、最小必要子图解释和跨文件召回
- 仍坚持 `preview -> confirm` 两阶段交付
- 所有正式输出位于仓库根的 `handoffs/`

## 运行入口

推荐入口始终是根级包：

```bash
python -m prepare_web_gpt_handoff.prepare --help
python -m prepare_web_gpt_handoff.preview --help
python -m prepare_web_gpt_handoff.confirm --help
```

兼容 wrapper 仍保留在：

- `.agents/skills/prepare_web_gpt_handoff/scripts/prepare_handoff.py`
- `.agents/skills/prepare_web_gpt_handoff/scripts/render_preview.py`
- `.agents/skills/prepare_web_gpt_handoff/scripts/confirm_handoff.py`

但 wrapper 只作为兼容层存在，真实实现以根级包 `prepare_web_gpt_handoff/` 为准。

## 输出结构

每次 handoff 都会生成这些产物：

- `brief.md`
- `bundle.md`
- `manifest.json`
- `reply_template.md`
- `notes.md`
- `preview.json`
- `attachments/`

推荐发送顺序：

1. `brief.md`
2. `bundle.md`
3. `reply_template.md`

## strict-exact

当运行环境要求精确 token 稳定可用时，开启 strict-exact：

```bash
python -m prepare_web_gpt_handoff.prepare --require-exact-tokens ...
```

或：

```bash
PREPARE_WEB_GPT_HANDOFF_REQUIRE_EXACT_TOKENS=1 python -m prepare_web_gpt_handoff.prepare ...
```

在专属环境中建议先预热 `cl100k_base`，再运行 strict-exact 验证。

## Canonical Sample

已提交样例位于：

- `examples/sample_project/`
- `examples/sample_project/handoffs/LATEST.md`

它是当前 public-facing contract 的 golden fixture。只有在 schema、关键输出字段、目录结构或 preview / confirm 行为发生变化时才允许更新。

## 当前设计状态

当前版本已经具备：

- 稳定包入口与 wrapper 一致性
- exact token 运行契约
- contract-first selector
- graph-assisted selector v1
- explainable manifest / preview 契约

下一步若继续演进，应优先在当前 skill 内部增强 selector 质量或复用共享层，而不是先做 installer、plugin 或 marketplace 化。
