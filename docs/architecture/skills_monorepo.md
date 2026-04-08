<!--
中文说明：多-skill monorepo 的仓库级架构说明。

这里定义目录边界、共享层定位和零安装原则，作为后续新增 skill 或抽共享逻辑
时的统一约束。
-->

# skills_monorepo

## 设计目标

本仓库用于承载多个 repo-scoped Codex skill，并保持以下原则：

- `git clone` / `git pull` 后可直接在仓库内使用
- skill 壳层与实现层边界清晰
- 共享逻辑通过显式共享包复用
- 不把仓库扩张成 plugin / marketplace / installer 系统

## 目录约定

- `.agents/skills/<skill_name>/`
  - skill 壳层
  - 放 `SKILL.md`、`agents/openai.yaml`、schema、templates、兼容 wrapper
- 根级 Python 包
  - 当前真实实现入口
  - 例如 `prepare_web_gpt_handoff/`
- `codex_skills_shared/`
  - 未来多个 skill 的共享实现层
- `docs/skills/`
  - 每个 skill 的独立文档
- `docs/architecture/`
  - 仓库级架构约定

## 零安装原则

仓库默认采用零安装优先策略：

- 不依赖 `pip install -e .` 才能使用
- 不采用纯 `src` layout
- 保证 `python -m <package>...` 在仓库根可直接运行

## 新 skill 的最小接入要求

新 skill 至少需要：

- `.agents/skills/<skill_name>/SKILL.md`
- `.agents/skills/<skill_name>/agents/openai.yaml`
- `docs/skills/<skill_name>.md`

如果该 skill 有真实执行能力，再补：

- 根级实现包
- 对应测试
- sample / fixture

## 依赖边界

- skill 间禁止直接依赖彼此内部实现
- 跨 skill 复用必须通过共享包
- placeholder skill 不得被当成真实执行入口

## 当前阶段

当前仓库已经是 monorepo 宿主，但只有 `prepare_web_gpt_handoff` 是生产级 skill。`monorepo_placeholder_skill` 仅用于结构验证。
