# Repository Guidelines

## Scope

本仓库用于维护 `prepare_web_gpt_handoff` 这个 repo-scoped Codex skill。默认目标是可迁移、可工程化、跨平台可用，并围绕 Python 3.10+ 与标准库实现。

## Development Constraints

- 核心逻辑必须放在 Python 中，不要把关键流程写死在 shell 脚本里
- `manifest.json` 内部只允许记录项目根相对路径
- 默认输出目录固定为 `.codex/handoffs/`
- 不要引入浏览器、Node、Playwright、10x-chat 或本机登录态依赖
- 优先保持最小可用实现，避免过度设计
- 注释聚焦规则、边界和异常，而不是解释显而易见的语句

## Testing

常用命令：

```bash
python -B -m unittest discover .codex/skills/prepare_web_gpt_handoff/tests -v
python .codex/skills/prepare_web_gpt_handoff/scripts/prepare_handoff.py --help
python .codex/skills/prepare_web_gpt_handoff/scripts/render_preview.py --help
python .codex/skills/prepare_web_gpt_handoff/scripts/confirm_handoff.py --help
```

GitHub Actions 会运行：

```bash
python -B -m unittest discover .codex/skills/prepare_web_gpt_handoff/tests -v
```

## Cross-platform Notes

- 所有路径处理统一使用 `pathlib`
- `manifest.json` 使用 POSIX 风格相对路径
- 终端展示允许输出当前机器绝对路径，但不能把绝对路径回写到核心数据中
- 目录与文件编码统一按 UTF-8 处理
