# Contract-Snippet Selection Implementation Plan

本计划是研究结论落地后的实现 spec，目标是把 `prepare_web_gpt_handoff` 的主阅读层从“文件级材料打包器”升级成“contract-first snippet selector”。

## Summary

下一轮实现保持这些外部行为不变：

- 继续使用当前 CLI
- 继续使用 token-first 预算
- 继续使用 `preview -> confirm` 两阶段 workflow
- 继续把真实产物写到可见的 `handoffs/`

真正要改的是：

- 选择单位
- 摘录单位
- bundle 结构
- manifest 审计元数据
- 质量测试

## 1. Selector Pipeline

选择器改成四阶段流水线：

1. candidate discovery
2. artifact typing
3. artifact scoring
4. snippet extraction + budget allocation

### Candidate Discovery

候选仍从当前文件扫描器产生，但进入下一阶段的单位不再只是文件。

新增两层概念：

- `file candidate`
- `artifact candidate`

其中 `artifact candidate` 是后续真正参与 bundle 竞争的单位。

### Artifact Typing

每个 artifact 必须归到以下角色之一：

- `contract`
- `workflow`
- `selection_logic`
- `supporting_context`
- `supporting_signal`

角色规则：

- schema / template / openai metadata / visible entry / status transition 相关材料归 `contract`
- `prepare / render / confirm / resolve_handoff_dir / validate_handoff_payload / write_visible_entry` 一类逻辑归 `workflow`
- scan / exclude / select / budget / excerpt 逻辑归 `selection_logic`
- README / AGENTS / DEMO / sample README 一类归 `supporting_context`
- 日志 / 配置摘要 /示例信号归 `supporting_signal`

### Artifact Scoring

评分采用确定性规则，不引入语义模型。

固定优先级：

1. `must_include`
2. `contract`
3. `workflow`
4. `selection_logic`
5. `supporting_context`
6. `supporting_signal`

附加加权因素：

- topic / focus / question 关键词命中
- 是否与 handoff contract 直接相关
- 是否是 status transition / visible entry / output schema 的一部分
- 是否是被当前讨论显式提及的符号 / section / file

明确降权：

- 纯说明性 supporting 文档
- 示例快照说明文档
- 与当前 topic 没有直接契约作用的样例文件

### Snippet Extraction

不同类型文件使用不同摘录器：

- Python: 标准库 `ast`
- Markdown: heading section
- JSON: key block
- YAML/TOML: top-level block
- 其他文本: 局部摘要，最后兜底 head-tail

## 2. Structured Extractors

### Python Extractor

优先摘录这些单元：

- workflow 入口函数
- handoff path / status / manifest / preview 相关函数
- selector / budget / excerpt 相关函数
- 支撑这些函数理解所需的 import block 与局部 helper

输出必须带：

- symbol name
- source file
- symbol role

首版只支持 Python 结构化摘录；其他代码语言继续使用现有兜底策略。

### Markdown Extractor

按 heading section 提取，优先匹配：

- workflow
- outputs
- contract
- preview
- confirm
- token
- schema
- golden fixture

### JSON / YAML / TOML Extractor

按 key block 提取，优先匹配：

- schema required / properties / enum
- status / handoff_id / paths / artifacts
- template / output / token / exclusion / next actions
- interface / policy / metadata

### Fallback Rule

只有在结构化提取失败时，才允许整文件 `head_tail_tokens:*`。

manifest 必须能记录某条是否是 fallback。

## 3. Bundle and Manifest Contract

### Bundle v2

`bundle.md` 改为固定六段：

1. 问题定义与 handoff 目标
2. 关键 contract 与输出约束
3. 工作流与状态变迁
4. 关键代码片段
5. 支撑材料与补充上下文
6. 风险、缺口与待验证点

每个条目都显示：

- 文件路径
- `bundle_role`
- 选入原因
- `excerpt_anchor`
- 原始 token 数
- 选入 token 数
- `excerpt_strategy`

### Manifest Additions

在 `files[]` 上新增：

- `bundle_role`
- `excerpt_strategy`
- `excerpt_anchor`
- `artifact_priority_reason`
- `fallback_excerpt`

在 `selection_summary` 上新增：

- `contract_files_selected`
- `workflow_files_selected`
- `selection_logic_files_selected`
- `structured_extract_files`
- `fallback_head_tail_files`

这些新增字段采用 additive 方式，不破坏现有 0.x contract。

## 4. Test Plan

### Selection Quality Tests

新增场景化测试：

- repo self-review 场景中，contract 材料必须压过 sample supporting 文档
- contract-only 场景中，visible entry / schema / template / workflow contract 必须优先进入主阅读层
- sample project 场景中，问题定义文档和 selector 逻辑优先于 DEMO 一类 supporting 文档

### Extractor Tests

- Python AST 提取函数/类稳定
- Markdown heading section 提取稳定
- JSON/YAML/TOML key-block 提取稳定
- fallback 只在结构化失败时触发

### Bundle Quality Tests

断言：

- 不再出现 repo self-review 场景下 `7/7` 条目都机械截断
- 至少一半关键代码条目来自结构化摘录
- bundle 中必须出现清晰的 contract layer

### Manifest Audit Tests

断言：

- 每个主阅读层条目都有 `bundle_role`
- 每个结构化摘录条目都有 `excerpt_anchor`
- `structured_extract_files` / `fallback_head_tail_files` 统计正确

## 5. Recommended Rollout

实现顺序固定如下：

1. 先加 artifact role 与 manifest 元数据
2. 再加 bundle v2 结构
3. 再接 Python AST extractor
4. 再接 Markdown / JSON / YAML / TOML block extractor
5. 最后调 scoring 与回归测试

原因：

- 先把审计面铺好，后续每一步才能知道质量到底有没有变好
- 先做 contract-first 和 bundle v2，就能立刻改善输出可读性
- 再加 snippet extractor，能让质量提升可被直接观察

## Defaults and Non-goals

默认选择：

- 继续使用标准库优先路线
- 继续允许 `tiktoken` 为可选精确依赖
- 首版只做确定性规则，不做 embedding / vector DB / tree-sitter

明确不做：

- 浏览器自动发送
- 外部语义检索服务
- 需要常驻索引进程的 repo graph 系统
- 为了 snippet 提取而引入跨平台复杂依赖
