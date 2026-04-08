# Repository Guidelines

## Scope

本仓库用于维护多个 repo-scoped Codex skill，是一个以零安装使用为优先目标的 skills monorepo。当前生产级 skill 为 `prepare_web_gpt_handoff`，其 skill 壳层位于 `.agents/skills/prepare_web_gpt_handoff/`，默认产物直接输出到仓库根的 `handoffs/`。目标是可迁移、可工程化、跨平台可用；核心实现围绕 Python 3.10+，并允许可选安装 `tiktoken` 来获得精确 token 计数。

## Development Constraints

- 核心逻辑必须放在 Python 中，不要把关键流程写死在 shell 脚本里
- `manifest.json` 内部只允许记录项目根相对路径
- 当前仓库是多-skill 宿主，skill 壳层统一放在 `.agents/skills/<skill_name>/`
- `agents/openai.yaml` 视为每个 skill 的 metadata contract，更新 `SKILL.md` 时要检查它是否仍然匹配
- 默认输出目录固定为 `handoffs/`
- 不要引入浏览器、Node、Playwright、10x-chat 或本机登录态依赖
- token 预算逻辑优先使用 `tiktoken`，缺失时必须退回保守估算而不是改回字符预算
- 真实运行入口统一以仓库根包 `prepare_web_gpt_handoff/` 为准；`.agents/skills/.../scripts/*.py` 只作为兼容 wrapper 保留
- 根 README 只写仓库级信息；每个真实 skill 必须有自己的 `docs/skills/<skill_name>.md`
- 新增 skill 时至少同时提交：
  - `.agents/skills/<skill_name>/SKILL.md`
  - `.agents/skills/<skill_name>/agents/openai.yaml`
  - `docs/skills/<skill_name>.md`
- skill 间禁止直接依赖彼此内部实现；跨 skill 复用只能通过共享包
- `monorepo_placeholder_skill` 只用于仓库结构验证，不能被当成真实可运行 skill
- 当运行环境要求精确 token 稳定可用时，优先开启 strict-exact：`--require-exact-tokens` 或 `PREPARE_WEB_GPT_HANDOFF_REQUIRE_EXACT_TOKENS=1`
- 本地环境以 `environment.yml` + `requirements-dev.txt` 为准，新增依赖时同步更新 README 与 CI
- 主阅读层坚持 contract-first：优先保留 contract、workflow 和关键代码片段，不要退回“按文件平铺 + 盲截断”
- graph 层只允许作为 selector 的内部增强：负责候选扩展、最小必要子图解释和跨文件召回，不得演化成长期 memory system
- `bundle.md` 采用分层上下文模型：`stable_contract`、`dynamic_task`、`evidence`、`attachments`
- 结构化摘录优先于 `head_tail_tokens:*`；只有在结构化摘录和 typed digest 都不足时才允许 fallback
- `manifest.json` 中与 graph-assisted selector 相关的解释字段属于正式 contract，修改时必须同步更新 schema、sample 和回归测试
- 当前仓库不做 plugin / marketplace / installer 化，避免把 scope 扩到分发系统工程
- 当前仓库保持零安装优先；不要把目录改造成必须 `pip install -e .` 后才能运行的纯 `src` layout
- `examples/sample_project/handoffs/` 中的已提交快照视为 canonical golden fixture，只保留一份样例并通过 `LATEST.md` 指向它
- 只有在 schema、关键输出字段、目录结构或 preview / confirm 行为变更时才更新 golden fixture；更新时必须审阅 diff
- 优先保持最小可用实现，避免过度设计
- 注释聚焦规则、边界和异常，而不是解释显而易见的语句

## Testing

常用命令：

```bash
python -B -m unittest discover .agents/skills/prepare_web_gpt_handoff/tests -v
python -m prepare_web_gpt_handoff.prepare --help
python -m prepare_web_gpt_handoff.preview --help
python -m prepare_web_gpt_handoff.confirm --help
```

GitHub Actions 会运行：

```bash
python -B -m unittest discover .agents/skills/prepare_web_gpt_handoff/tests -v
```

repo 级测试还会校验 skill metadata 与 canonical sample snapshot，确保 public-facing contract 没有静默漂移。

测试新增约束：

- 不允许再通过 `scripts/` 目录注入 `sys.path` 来驱动主要测试
- 必须至少覆盖包导入、`python -m` 与兼容 wrapper 三类真实入口
- 必须覆盖多-skill monorepo 的基础护栏：
  - 根 README 为仓库首页
  - `.agents/skills/README.md` 存在
  - placeholder skill metadata 完整且禁用 implicit invocation
- 专属 agent 环境建议额外执行一轮 strict-exact 验证，确认 `selection_summary.token_runtime.exact_available` 为 `true`

## Cross-platform Notes

- 所有路径处理统一使用 `pathlib`
- `manifest.json` 使用 POSIX 风格相对路径
- 终端展示允许输出当前机器绝对路径，但不能把绝对路径回写到核心数据中
- 目录与文件编码统一按 UTF-8 处理
