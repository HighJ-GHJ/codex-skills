# Contract-Snippet Selection Design Principles

这些原则是从当前仓库的 baseline 和外部证据中抽出来的，后续实现和测试都应该以它们为准，而不是回到“能跑就行”的文件级打包思路。

## 1. Contract Before Commentary

优先交付系统边界和输出约束，再交付解释性说明。

对本 skill 来说，一级材料包括：

- `manifest.schema.json`
- `final_reply.schema.md`
- `reply_template.md`
- `openai.yaml`
- `SKILL.md`
- 负责 `prepare / preview / confirm / visible entry` 的 workflow contract

README、AGENTS、DEMO、样例说明都属于 commentary 或 supporting context，除非 topic 明确要求，否则不能压过 contract。

## 2. Structured Snippet Before Head-Tail Fallback

只要文件能被结构化切分，就不应该直接走整文件 `head_tail_tokens:*`。

优先级固定为：

1. symbol / section / key-block 提取
2. 结构化提取不足时再补局部 head-tail
3. 彻底无法结构化时才整文件 head-tail

这个原则会直接决定 snippet extractor 的实现顺序和测试策略。

## 3. Necessary Context Before Maximal Context

“相关”不等于“应该打包”。主阅读层只应该保留完成当前策略判断所必需的材料。

判断标准不是“这个文件看起来和主题有关”，而是：

- 它是否定义了任务边界
- 它是否决定了输出 contract
- 它是否解释了核心 workflow
- 它是否承载关键选择逻辑

其余材料默认进入 `attachments/`。

## 4. Anchored Excerpts Before Anonymous Chunks

每个进入 bundle 的摘录都必须带锚点，不能只给出一段匿名文本。

锚点优先级：

- Python: `function/class/module import block`
- Markdown: `heading section`
- JSON/YAML/TOML: `key path / top-level block`
- 兜底: `head_tail_tokens:*`

后续 manifest 应能明确回答：

- 摘了哪一段
- 为什么是这段
- 用的什么摘录策略

## 5. Explainable Selection Before Opaque Scoring

选择器可以打分，但分数本身不是目标。真正需要稳定的是“为什么被选中”的解释。

因此后续实现中，每个主阅读层条目都要有：

- `bundle_role`
- `artifact_priority_reason`
- `excerpt_strategy`
- `excerpt_anchor`

如果某条解释写不出来，通常就说明这条不该进主阅读层。

## 6. Workflow Edges Matter More Than File Boundaries

对 handoff skill 来说，真正重要的不是文件边界，而是 workflow 边界：

- handoff id 如何分配
- handoff dir 如何解析
- preview 如何生成
- confirm 如何更新状态
- visible entry 如何写入

因此 snippet 选择应优先围绕这些 workflow edges，而不是简单按“哪个文件在 `scripts/` 目录下”。

## 7. Human-Readable Contract Layer

web GPT 的消费对象不是原始 repo，而是 handoff 包。bundle 必须显式呈现一个人类可读的 contract layer。

这意味着 bundle 结构至少要区分：

- 问题定义
- contract 与输出约束
- workflow 与状态变迁
- 关键代码片段
- supporting context

当前“文档 / 代码 / 配置日志”的粗分法不够表达这个层次。

## 8. Token Discipline Is Necessary But Not Sufficient

token-first 预算仍然必须保留，但它只是约束，不是质量本身。

真正的质量指标应固定为三类：

- `coverage`: 是否覆盖任务边界、contract、workflow、关键选择逻辑
- `precision`: 是否避免无关 supporting 材料挤占主阅读层
- `explainability`: 是否能解释每个片段为什么被选、摘了哪一段

后续实现和测试都应围绕这三项写，而不是只断言 bundle 没超 `max_bundle_tokens`。
