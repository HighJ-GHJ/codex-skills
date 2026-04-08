<!--
中文说明：仓库占位 skill 的说明页。

这个 skill 用来验证 monorepo 的目录约定、metadata 完整性和文档结构，不承担
真实执行能力。
-->

# monorepo_placeholder_skill

## 作用

`monorepo_placeholder_skill` 是仓库结构验证用占位 skill。它的存在仅用于证明当前仓库已经支持多个 repo-scoped skill 共存。

## 当前状态

- 状态：`placeholder`
- 不允许 implicit invocation
- 不提供 Python 实现包
- 不提供 wrapper、sample 或 console scripts

## 使用约束

这个占位 skill 不应被当成真实可运行 skill，也不应成为共享逻辑或产品能力的依赖来源。未来接入第二个真实 skill 时，可以直接替换或删除它。
