# Contract-Snippet Selection Research Summary

本研究聚焦一个非常具体的问题：对于 `prepare_web_gpt_handoff` 这类“把 Codex 当前策略讨论转交给 web GPT”的 handoff 包，怎样才能稳定挑中最有价值的 contract 产物和代码片段，而不是机械地按文件做 head/tail 截断。

当前研究只服务本仓库，不试图泛化成一个通用的代码检索系统。证据优先级是：

1. 论文
2. 官方技术文档
3. 少量高质量工程实践或 benchmark 描述

## 1. 本地基线审计

研究先基于当前 skill 的真实输出做了 3 个 baseline 场景。

### Baseline Matrix

| Scenario | Handoff ID | Selected | Truncated | 主要优点 | 主要缺点 | 对设计的启发 |
| --- | --- | ---: | ---: | --- | --- | --- |
| repo self-review | `2026-04-06_222129_验证当前_skill_产出的_handoff_质量是否可靠` | 7 | 7 | `brief.md` framing 很稳，preview / manifest / visible entry 都正常 | 7/7 条目都被截断；supporting doc 进入主阅读层；缺少显式 contract layer；代码还是整文件 head/tail | 需要 artifact-first 选择；structured snippet 必须优先于整文件截断 |
| sample_project | `2026-04-06_211116_为_sample_project_准备网页版_gpt_研究交接包` | 6 | 1 | 主阅读层相对精简，问题文档、研究问题、selector 原型、日志都进入了 bundle；整体最接近“minimal_sufficient_context” | `DEMO.md` 这种 supporting 文档仍会进主阅读层；没有显式区分 contract / workflow / supporting 层 | 说明当前规则对小项目还能工作，但一旦进入 repo-self-review 就会暴露 artifact 粒度不够的问题 |
| contract-only | `2026-04-06_225758_只审查_handoff_contract_与输出约束是否完整` | 7 | 4 | schema、reply contract、`openai.yaml` 已能进主阅读层，说明 must-include 路径是可靠的 | 仍然会补进 `AGENTS.md` 这种 supporting doc；workflow 还是大文件截断；没有把 visible entry / status transition / manifest sample 提升为一级 contract | contract-first 思路是对的，但当前自动补选和 bundle 结构还没有真正“以 contract 为中心” |

### 基线结论

- 当前 skill 的**工程正确性**已经足够可靠，但**主阅读层质量**还没有形成鲜明特色。
- 问题不在“没有预算控制”，而在“预算花在了文件级材料上，而不是 artifact 级材料上”。
- 对 repo self-review 这种复杂场景，现有选择器会把 `README.md`、`AGENTS.md`、`SKILL.md`、大代码文件都塞进 bundle，然后统一压成 `head_tail_tokens:*`。这在格式上可用，但对 web GPT 来说不够高价值。
- contract-only 场景说明：只要用户显式指定，schema/template/workflow contract 就能稳定进入 bundle；问题在于自动补选仍然缺少 “contract before commentary” 的强偏置。

## 2. 证据抽取矩阵

下面的矩阵把每份外部证据统一抽成 8 项，避免研究结论退化成散文式综述。

| Source | 解决的问题 | 检索单位 | Chunk 单位 | 排序 / rerank 信号 | 结构信息是否参与 | 如何定义“有用上下文” | 对效率 / 可迁移性的启发 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [RepoCoder (EMNLP 2023)](https://aclanthology.org/2023.emnlp-main.151/) | 仓库级 code completion 如何利用散落在不同文件中的信息 | 跨文件代码片段 | 多粒度 completion 场景，强调 repository info 不是单文件补充 | similarity retriever + iterative retrieval-generation | 结构参与有限，重点是迭代检索 | 有用上下文是“能提升 completion 的跨文件知识”，而不是所有相关文本 | 支持“必须有 retrieval pipeline”；但仅靠相似度还不够解释 current skill 的 contract 选择问题 |
| [Repoformer (ICML 2024)](https://proceedings.mlr.press/v235/wu24a.html) | 为什么不是所有 completion 都应该触发 retrieval | 检索是否发生本身也要被预测 | 仍以 repository context 为单位，但强调 selective retrieval | self-evaluation policy，判断 retrieval 是否必要 | 不是主要贡献点 | 有用上下文不只是 relevant，还必须“必要”；无用 context 甚至有害 | 直接支持本 skill 不要默认多塞材料；对 token 预算和 bundle 克制非常关键 |
| [DraCo / Dataflow-Guided Retrieval Augmentation (ACL 2024)](https://aclanthology.org/2024.acl-long.431/) | import relation 或 text similarity 不足以找到 completion 真正依赖的上下文 | code entities + repo-specific context graph | entity / relation 级别，不是整文件 | dataflow relation + precise retrieval | 是，核心是 repo-specific context graph | 有用上下文应与目标 completion 的真实依赖关系对齐 | 支持我们在 selector 中引入“workflow edges / status transition / artifact dependency”一类结构信号，而不是只看路径或文件类型 |
| [CodeRAG (EMNLP 2025)](https://aclanthology.org/2025.emnlp-main.1187/) | 现有 repo-level RAG 会出现 query 构造差、单路径检索、retriever 与 code LM 不对齐 | multi-path retrieval | 不强调整文件，强调 necessary knowledge 的筛选 | log-probability query construction + multi-path retrieval + BestFit reranking | 间接参与，通过 multi-path + reranking | 有用上下文必须同时满足 relevant 和 necessary | 直接支持“contract layer 不该只靠一条路径自动补选”；未来可为 contract/workflow/selection_logic 设计多路径打分 |
| [RepoBench benchmark summary](https://huggingface.co/papers/2306.03091) | 如何评估 repository-level code completion，不只看单文件 | retrieval / completion / pipeline 三类任务 | cross-file snippet | 以 benchmark 任务形式定义 relevance | 结构信息不是主线 | 有用上下文是“最 relevant code snippets from other files as cross-file context” | 说明我们后续评测也该分解成 retrieval-like、bundle-like、pipeline-like 三层，而不是只看 token 限额 |
| [SWE-QA benchmark summary](https://huggingface.co/papers/2509.14635) | 仓库级代码问答需要跨文件、多跳依赖和架构理解 | repository-level QA context | question-answer supporting spans | context augmentation strategies + agent reasoning | 是，突出 architecture / long-range dependency | 有用上下文应能支持 intention understanding、cross-file reasoning、multi-hop dependency analysis | 支持把 handoff 质量定义为 coverage / precision / explainability，而不是仅仅“有没有把文件放进去” |
| [cAST summary](https://huggingface.co/papers?q=factored+structure) | line-based chunking 会破坏语义结构 | code chunks | AST node / merged sibling nodes | respect size limits while preserving semantic units | 是，核心贡献 | 有用上下文应该是 self-contained、semantically coherent unit | 直接支持本 skill 的代码摘录器要按 `ast` 的 symbol / node 级别工作，而不是 head/tail |
| [Azure AI Search: Chunk large documents](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-chunk-documents) | 文本太大时如何做更稳妥的 chunking | document chunks | fixed / variable / semantic chunks | overlap + content shape + query characteristics | 是，heading / sentence / semantic chunking 都被显式推荐 | 有用上下文是能在限制内保持语义连贯、避免 truncation 丢信息的 chunk | 支持 token-first；也支持我们将文档按 heading section、代码按结构化片段切分；“先保证 chunk 质量，再谈 retrieval” |
| [Azure AI Search: Chunk by document layout or structure](https://learn.microsoft.com/en-us/azure/search/search-how-to-semantic-chunking) | 多文档/长文如何按 layout 组织高质量 chunk | document sections | heading + semantically coherent paragraphs / sentences | parent-child indexing + section-aware chunking | 是，显式把 headings 和 child chunk 作为结构元数据 | 有用上下文是带 headings、带 parent-child 关系的 section chunk | 直接启发我们给 bundle 条目增加 `excerpt_anchor` 和 `bundle_role`，把 section / symbol / key-block 作为一等元数据 |
| [Anthropic long-context prompting](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices#structure-prompts-with-xml-tags) | 多文档长上下文如何提高读取质量 | documents with metadata | document-level blocks | quote-first + query-at-end + metadata clarity | 是，用 XML/document tags 承载 metadata | 有用上下文不只是内容本身，还包括 source / metadata / quote anchor | 直接支持“contract layer + workflow layer + snippet layer”的 bundle v2 结构，也支持 quote-first / anchor-first handoff formatting |

### 关于 repo-QA 证据的说明

最初规划里列出的 “On Improving Repository-Level Code Question Answering: A Repobench Study” 在本次检索中没有找到稳定、可核对的官方公开页面，因此没有硬编进最终证据池。为了保持研究真实性，这里使用了更容易核验的 repo-QA 邻近证据：

- RepoBench 的 benchmark 定义
- SWE-QA 的 repo-level QA benchmark 描述

它们已经足够支撑“仓库级问题回答需要跨文件、多跳依赖、架构理解与更严格评测指标”这一类结论。

## 3. 从证据到设计空间

将外部证据和本地 baseline 一起映射，可以得到 5 个真正可行的设计方向。

### A. Contract-first deterministic selector

能解决：

- supporting 文档压过关键 contract 的问题
- 主阅读层没有 contract layer 的问题

实现成本：

- 低到中
- 不需要新依赖

需要新增的元数据：

- `bundle_role`
- `artifact_priority_reason`

适配性：

- 非常适合 v1
- 完全符合轻依赖、跨平台、可工程化约束

### B. AST-based code snippet extractor

能解决：

- 大代码文件统一 head/tail 截断的问题
- 代码主阅读层无法解释“为什么是这段”的问题

实现成本：

- 中
- Python 可用标准库 `ast`

需要新增的元数据：

- `excerpt_strategy`
- `excerpt_anchor`

适配性：

- 适合 v1
- 先支持 Python，其他语言保持兜底策略

### C. Dependency-guided snippet promotion

能解决：

- workflow / status transition / contract 生成逻辑不容易从代码中被挑中的问题

实现成本：

- 中到高
- 需要在当前 repo 内定义轻量依赖图或调用链启发式

适配性：

- 更适合 v2
- 可以先做 workflow-specific heuristics，而不是完整 repo graph

### D. Bundle v2 with contract / workflow / snippet layers

能解决：

- 当前 bundle 只有“文档 / 代码 / 配置日志”的粗结构，无法表达交接重点

实现成本：

- 低到中

适配性：

- 非常适合 v1
- 几乎是把研究结论显式反映到输出 contract 的必要步骤

### E. Quote-first / anchor-first web GPT handoff formatting

能解决：

- web GPT 拿到 bundle 后仍需自己猜“这段来自哪里、该如何引用”的问题

实现成本：

- 低

适配性：

- 适合 v1
- 与 Anthropic 的 long-context / metadata / quote-first 建议高度一致

## 4. 研究结论

### 强相关结论

这些结论与当前仓库的痛点直接吻合，应该进入下一轮实现：

- **并不是所有看起来相关的材料都应该进入主阅读层。** Repoformer 和 CodeRAG 都说明了“relevant”不够，必须进一步判断“necessary”。
- **代码片段不能继续按整文件裁剪。** cAST 和 Azure 的结构化 chunking 说明，语义单元必须被完整保存；否则 chunk 的可解释性和消费质量都会下降。
- **contract 不是 supporting context，而应是一级材料。** 对 handoff 包来说，schema / template / visible entry / status transition 比普通说明文档更接近“系统边界”。
- **多文档交接包必须带 metadata 和锚点。** Anthropic 的长上下文指南明确支持“带 source/metadata 的文档块”和“quote-first”的组织方式。
- **评测不能只看 token 限额。** RepoBench、SWE-QA 一类工作都说明：真正的评测要看检索是否找对、是否支撑多跳推理、是否覆盖关键结构关系。

### 有启发但暂不适用的结论

- 多路径检索、BestFit reranking、repo-specific context graph 都很有价值，但对当前 skill 的 v1 来说太重。
- 这类能力更适合作为 v2 的“研究预留”接口，而不是一开始就变成强依赖。

## 5. 推荐路线

基于本地 baseline 与外部证据，推荐路线如下：

1. **先做 contract-first deterministic selector**
2. **同时做 Python AST snippet extractor**
3. **把 bundle 升级成 contract / workflow / snippet 分层结构**
4. **在 manifest 中增加 excerpt / anchor / role 审计元数据**
5. **把 dependency-guided promotion 作为下一阶段增强**

也就是说，当前 skill 的特色不应该是“会打包”，而应该是：

**在轻依赖前提下，用确定性规则稳定挑中最有价值的 contract 与代码片段，并把这些片段以可解释、可引用、可追踪的方式交付给 web GPT。**
