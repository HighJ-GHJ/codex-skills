# prepare_web_gpt_handoff

`prepare_web_gpt_handoff` 是一个 Codex-first 的 repo-scoped skill，用来把当前与 Codex 的策略讨论或资料检索上下文整理成一个可手动发送给网页版 GPT 的 handoff 包。skill 本体位于 `.agents/skills/prepare_web_gpt_handoff/`，真实产物默认直接输出到仓库根的 `handoffs/`，便于在 macOS、Windows 和 WSL 中直接查看。

仓库目标是长期维护、轻依赖、跨平台。当前版本已经包含可运行脚本、模板、schema、测试、GitHub Actions CI、skill metadata 文件，以及一个真实示例项目与示例 handoff 快照。预算控制采用 token-first 设计；安装 `tiktoken` 时会使用精确 token 计数，未安装时会回退到保守估算。当前主线能力已经升级成 contract-first context layering：主阅读层会优先交付稳定 contract、workflow 和关键代码片段，而不是简单按文件做 head/tail 截断。

## 本地环境

仓库现在带有独立的依赖声明文件：

- [environment.yml](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/environment.yml): conda 环境定义
- [requirements.txt](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/requirements.txt): 推荐运行依赖
- [requirements-dev.txt](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/requirements-dev.txt): 本地开发与 CI 依赖

推荐的本地初始化方式：

```bash
conda env create -f environment.yml
conda activate prepare-web-gpt-handoff
```

如果环境已经存在，更新方式：

```bash
conda env update -f environment.yml --prune
conda activate prepare-web-gpt-handoff
```

当前依赖非常轻，核心只依赖 `tiktoken` 来获得精确 token 计数；即使不安装它，skill 仍然可以退回到保守估算模式。推荐在首次使用前预热一次 `cl100k_base`：

```bash
python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); print('cl100k_base cached')"
```

如果你希望在专属 agent 环境中把“精确 token 可用”当成正式运行契约，而不是静默回退条件，请启用 strict-exact 模式：

```bash
python -m prepare_web_gpt_handoff.prepare --require-exact-tokens ...
```

或者设置环境变量：

```bash
export PREPARE_WEB_GPT_HANDOFF_REQUIRE_EXACT_TOKENS=1
```

## 做什么

- 生成结构化的 `brief.md`
- 选择最小必要文件并生成 `bundle.md`
- 生成稳定可读的 `manifest.json`
- 生成 `reply_template.md` 和 `notes.md`
- 生成 `preview.json` 并进入预览态
- 在确认后更新状态并输出正式交付路径报告
- 以 `stable_contract / dynamic_task / evidence / attachments` 的上下文层组织 handoff
- 以 `contract / workflow / selection_logic / code_snippet / supporting_context` 的 artifact 类型组织主阅读层
- 优先使用结构化摘录与 typed digest compaction，而不是盲目截断

## 不做什么

- 不依赖浏览器、Playwright、10x-chat、Node 或本机登录态
- 不把机器绝对路径写入 `manifest.json`
- 不自动发送给网页版 GPT
- 不自动回灌 `final_reply.md`

## 目录结构

```text
.
├─ .agents/
│  └─ skills/
│     └─ prepare_web_gpt_handoff/
│        └─ agents/openai.yaml
├─ handoffs/
├─ AGENTS.md
├─ LICENSE
├─ README.md
├─ pyproject.toml
├─ .github/
└─ examples/
```

## GitHub Ready

- 使用 [`.gitattributes`](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/.gitattributes) 统一文本行尾
- 使用 [`.editorconfig`](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/.editorconfig) 统一编码、缩进与结尾换行
- 使用 [GitHub Actions CI](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/.github/workflows/python-tests.yml) 在 macOS / Windows / Ubuntu 上运行测试
- 使用 [MIT License](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/LICENSE) 便于公开托管和后续协作

## Distribution Boundary

这个仓库当前定位是“公共 skill 源码仓库 + 可直接使用的 repo-scoped skill”，不是 plugin / marketplace / installer 仓库。本轮实现专注于：

- 让 Codex 直接在仓库内发现并调用 skill
- 让 handoff 产物在 `handoffs/` 中可见、可迁移、可追踪
- 让输出 contract、示例快照和测试一起稳定维护

不在本轮范围内的内容：

- plugin 打包
- marketplace 元数据发布
- 自动安装器或插件市场集成

除了 [SKILL.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/.agents/skills/prepare_web_gpt_handoff/SKILL.md) 之外，skill 还包含 UI-facing metadata 文件 [agents/openai.yaml](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/.agents/skills/prepare_web_gpt_handoff/agents/openai.yaml)，用于补齐展示名、短描述和默认 prompt。

## 运行方式

建议从仓库根目录运行。当前仓库按 repo-scoped `.agents/skills/` 方式组织，产物默认写到仓库根 `handoffs/`。

主入口推荐使用包入口：

```bash
python -m prepare_web_gpt_handoff.prepare --mode strategy_research --topic "为 handoff skill 设计可迁移的工程结构" --goal "整理当前讨论并交接给网页版 GPT 继续策略论证" --focus-point "保持跨平台、轻依赖、可长期维护" --must-include README.md --must-include prepare_web_gpt_handoff/workflow.py --max-files 6 --max-bundle-tokens 4096
```

重新查看预览：

```bash
python -m prepare_web_gpt_handoff.preview --handoff handoffs/2026-04-06_180000_prepare_web_gpt_handoff
```

确认交付：

```bash
python -m prepare_web_gpt_handoff.confirm --handoff handoffs/2026-04-06_180000_prepare_web_gpt_handoff
```

旧的 `scripts/*.py` 路径仍然保留，但现在只作为兼容 wrapper；真实实现统一位于仓库根的 `prepare_web_gpt_handoff/` 包中。

## 输出文件说明

每次生成都会创建：

- `handoffs/YYYY-MM-DD_HHMMSS_<slug>/brief.md`
- `handoffs/YYYY-MM-DD_HHMMSS_<slug>/bundle.md`
- `handoffs/YYYY-MM-DD_HHMMSS_<slug>/manifest.json`
- `handoffs/YYYY-MM-DD_HHMMSS_<slug>/reply_template.md`
- `handoffs/YYYY-MM-DD_HHMMSS_<slug>/notes.md`
- `handoffs/YYYY-MM-DD_HHMMSS_<slug>/preview.json`
- `handoffs/YYYY-MM-DD_HHMMSS_<slug>/attachments/`

`manifest.json` 中所有路径都以项目根相对路径记录，便于迁移和后续自动化处理。正式交付报告会同时显示当前机器的绝对路径，方便手动定位文件。文件与 bundle 的预算字段都记录为 token，而不是字符数。

`bundle.md` 当前采用固定的 v2 结构：

- 问题定义与 handoff 目标
- 关键 contract 与输出约束
- 工作流与状态变迁
- 关键代码片段
- 支撑材料与补充上下文
- 风险、缺口与待验证点

每个 bundle 条目还会记录 `context_layer`、`artifact_type`、`excerpt_strategy`、`compaction_strategy` 与摘录锚点，便于后续审计“为什么选它、摘了哪一段、是否用了 fallback”。

`dynamic_task` 这一层固定由 `brief.md` 承载，因此不会伪装成 `bundle` 内的文件计数；`selection_summary.bundle_layer_counts` 只统计主阅读层与 attachments 中真实出现的 artifact。

为了方便快速定位最新 handoff，仓库根还会自动生成：

- `handoffs/LATEST.md`
- `handoffs/<handoff_id>.md`
- `handoffs/<handoff_id>/brief.md`
- `handoffs/<handoff_id>/bundle.md`
- `handoffs/<handoff_id>/manifest.json`
- `handoffs/<handoff_id>/reply_template.md`
- `handoffs/<handoff_id>/notes.md`
- `handoffs/<handoff_id>/preview.json`

其中 `handoffs/<handoff_id>/` 本身就是真实 handoff 包，可以直接打开查看。

## 真实示例

仓库包含一个可直接阅读的演示输入项目：

- [examples/sample_project/README.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/README.md)
- [examples/sample_project/DEMO.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/DEMO.md)
- [examples/sample_project/handoffs/LATEST.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/handoffs/LATEST.md)

该示例会配套一个真实生成的 handoff 快照，展示 `brief.md`、`bundle.md`、`manifest.json`、`reply_template.md`、`notes.md` 与 `preview.json` 的实际形态。具体路径见示例项目内的说明文档。

## 预览 / 确认 / 交付流程

1. 运行 `python -m prepare_web_gpt_handoff.prepare` 生成 handoff 包，`manifest.status` 初始为 `preview`
2. 查看终端预览或再次运行 `python -m prepare_web_gpt_handoff.preview`
3. 用户显式确认后运行 `python -m prepare_web_gpt_handoff.confirm`
4. 确认脚本会把 `manifest.status` 更新为 `confirmed`，并输出推荐发送顺序：
   1. `brief.md`
   2. `bundle.md`
   3. `reply_template.md`

## 测试

```bash
python -m unittest discover .agents/skills/prepare_web_gpt_handoff/tests -v
python -m prepare_web_gpt_handoff.prepare --help
python -m prepare_web_gpt_handoff.preview --help
python -m prepare_web_gpt_handoff.confirm --help
```

如需只通过 pip 补依赖，也可以执行：

```bash
python -m pip install -r requirements-dev.txt
```

未安装或运行时无法加载 exact tokenizer 时，skill 会默认回退到保守估算，并在 `manifest.json` 中同时记录 `selection_summary.token_count_method` 与 `selection_summary.token_runtime`。如果开启 strict-exact，prepare 会直接报错而不是静默回退。

## 示例生成命令

下面的命令会以 `examples/sample_project` 作为项目根生成一个新的 handoff：

```bash
python -m prepare_web_gpt_handoff.prepare \
  --project-root examples/sample_project \
  --mode strategy_research \
  --topic "为 sample_project 准备网页版 GPT 研究交接包" \
  --goal "把当前策略问题与最小必要材料整理给网页版 GPT 继续研究" \
  --focus-point "保持 minimal_sufficient_context" \
  --focus-point "明确 handoff_id 回显与最终收口格式" \
  --must-include README.md \
  --must-include docs/overview.md \
  --must-include docs/research_questions.md \
  --must-include schemas/manifest.schema.json \
  --must-include templates/reply_template.md \
  --must-include src/workflow.py \
  --must-include src/selector.py \
  --must-include logs/strategy.log \
  --require-exact-tokens \
  --max-files 8
```

## Golden Fixture

[examples/sample_project/handoffs/](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/handoffs) 里的已提交快照不是临时生成垃圾，而是仓库受控维护的 canonical sample / golden fixture，用来展示输出 contract。维护规则是：

- 目录内只保留一份 canonical sample handoff
- `LATEST.md` 必须指向这份 canonical sample
- 只有当 schema、目录结构、关键输出字段或 preview / confirm 行为发生变化时才重生成
- 更新 sample 时必须一并审阅 diff，而不是直接覆盖

## Research Notes

仓库还包含一组面向后续质量改造的研究文档，主题是如何把“高价值 contract 与代码片段选择”做成这个 skill 的核心特色：

- [Research Summary](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/docs/research/contract_snippet_selection/research_summary.md)
- [Design Principles](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/docs/research/contract_snippet_selection/design_principles.md)
- [Implementation Plan](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/docs/research/contract_snippet_selection/implementation_plan.md)
