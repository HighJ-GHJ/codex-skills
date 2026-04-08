# codex-skills workspace

这是一个 Codex-first、repo-scoped 的 **skills monorepo**。仓库目标不是发布 plugin / marketplace / installer，而是把多个 skill 连同文档、样例、测试和共享实现一起放进同一个工作区，保证在另一台电脑上 `git clone` / `git pull` 后，直接进入仓库即可继续使用和开发。

当前仓库已经明确采用“零安装优先”的工程契约：

- skill 目录统一放在 `.agents/skills/`
- 当前真实可用的生产级 skill 只有 `prepare_web_gpt_handoff`
- 不做纯 `src` layout
- 不要求先执行 `pip install -e .`
- 共享代码通过根级 Python 包复用，而不是通过 skill 之间互相透穿

## 当前 Skills

| Skill | 状态 | 用途 | 文档 |
| --- | --- | --- | --- |
| `prepare_web_gpt_handoff` | production | 把当前 Codex 策略讨论整理成可发送给 web GPT 的 handoff 包 | [`docs/skills/prepare_web_gpt_handoff.md`](docs/skills/prepare_web_gpt_handoff.md) |
| `monorepo_placeholder_skill` | placeholder | 用于验证多-skill 仓库目录、metadata 和索引结构 | [`docs/skills/monorepo_placeholder_skill.md`](docs/skills/monorepo_placeholder_skill.md) |

Skill 壳层索引见：

- [`.agents/skills/README.md`](.agents/skills/README.md)

仓库级架构说明见：

- [`docs/architecture/skills_monorepo.md`](docs/architecture/skills_monorepo.md)

## 仓库结构

```text
.
├─ .agents/skills/              # repo-scoped skill 壳层
├─ codex_skills_shared/         # 多 skill 共享实现
├─ prepare_web_gpt_handoff/     # 当前生产级 skill 的实现包
├─ docs/
│  ├─ architecture/
│  └─ skills/
├─ examples/
├─ handoffs/
├─ AGENTS.md
├─ environment.yml
├─ pyproject.toml
└─ requirements-dev.txt
```

## 本地环境

推荐环境：

- [`environment.yml`](environment.yml)
- [`requirements.txt`](requirements.txt)
- [`requirements-dev.txt`](requirements-dev.txt)

初始化方式：

```bash
conda env create -f environment.yml
conda activate prepare-web-gpt-handoff
```

如果只想在现有环境中补依赖：

```bash
python -m pip install -r requirements-dev.txt
```

当前仓库坚持 token-first 预算。安装并预热 `tiktoken` 后，`prepare_web_gpt_handoff` 会使用 `tiktoken:cl100k_base`；否则会回退到保守估算。专属环境中如需把精确 token 当成正式运行契约，继续使用 strict-exact：

```bash
python -m prepare_web_gpt_handoff.prepare --require-exact-tokens ...
```

## 默认使用方式

本仓库默认是在仓库根直接工作，而不是先安装成全局包。当前生产级 skill 的推荐入口仍然是：

```bash
python -m prepare_web_gpt_handoff.prepare --help
python -m prepare_web_gpt_handoff.preview --help
python -m prepare_web_gpt_handoff.confirm --help
```

兼容 wrapper 仍然保留在 `.agents/skills/prepare_web_gpt_handoff/scripts/`，但真实实现统一位于根级包中。

## 测试

统一回归：

```bash
python -B -m unittest discover .agents/skills/prepare_web_gpt_handoff/tests -v
```

repo 级测试会同时保护：

- skill metadata
- monorepo 文档和目录约定
- canonical sample / Golden Fixture
- 当前 skill 的 entrypoint、strict-exact 和 graph-assisted contract

## 边界

- 当前仓库不是 plugin / marketplace / installer 仓库
- 当前不做长期 memory system
- graph 层只作为 selector 的内部增强
- 新 skill 必须具备独立文档、metadata 和最小 repo 级契约

当前最完整、最可直接使用的 skill 文档见：

- [`docs/skills/prepare_web_gpt_handoff.md`](docs/skills/prepare_web_gpt_handoff.md)
