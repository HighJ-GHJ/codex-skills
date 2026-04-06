# prepare_web_gpt_handoff

`prepare_web_gpt_handoff` 是一个 repo-scoped Codex skill，用来把当前与 Codex 的策略讨论或资料检索上下文整理成一个可手动发送给网页版 GPT 的 handoff 包。它只负责整理、打包、预览、确认和交付，不负责自动打开浏览器、自动发送消息，也不负责把外部回复自动导回仓库。

仓库目标是长期维护、轻依赖、跨平台。当前版本已经包含可运行脚本、模板、schema、测试、GitHub Actions CI，以及一个真实示例项目与示例 handoff 快照。

## 做什么

- 生成结构化的 `brief.md`
- 选择最小必要文件并生成 `bundle.md`
- 生成稳定可读的 `manifest.json`
- 生成 `reply_template.md` 和 `notes.md`
- 生成 `preview.json` 并进入预览态
- 在确认后更新状态并输出正式交付路径报告

## 不做什么

- 不依赖浏览器、Playwright、10x-chat、Node 或本机登录态
- 不把机器绝对路径写入 `manifest.json`
- 不自动发送给网页版 GPT
- 不自动回灌 `final_reply.md`

## 目录结构

```text
.
├─ .codex/
│  ├─ handoffs/
│  └─ skills/
│     └─ prepare_web_gpt_handoff/
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

## 运行方式

建议从仓库根目录运行。当前仓库已经按 repo-scoped `.codex/` 方式组织；如果后续要让 Codex 自动以该目录作为项目根，建议在仓库根目录初始化 Git。

生成并进入预览态：

```bash
python .codex/skills/prepare_web_gpt_handoff/scripts/prepare_handoff.py --mode strategy_research --topic "为 handoff skill 设计可迁移的工程结构" --goal "整理当前讨论并交接给网页版 GPT 继续策略论证" --focus-point "保持跨平台、轻依赖、可长期维护" --must-include README.md --must-include .codex/skills/prepare_web_gpt_handoff/scripts/common.py --max-files 6 --max-bundle-chars 12000
```

重新查看预览：

```bash
python .codex/skills/prepare_web_gpt_handoff/scripts/render_preview.py --handoff .codex/handoffs/2026-04-06_180000_prepare_web_gpt_handoff
```

确认交付：

```bash
python .codex/skills/prepare_web_gpt_handoff/scripts/confirm_handoff.py --handoff .codex/handoffs/2026-04-06_180000_prepare_web_gpt_handoff
```

## 输出文件说明

每次生成都会创建：

- `.codex/handoffs/YYYY-MM-DD_HHMMSS_<slug>/brief.md`
- `.codex/handoffs/YYYY-MM-DD_HHMMSS_<slug>/bundle.md`
- `.codex/handoffs/YYYY-MM-DD_HHMMSS_<slug>/manifest.json`
- `.codex/handoffs/YYYY-MM-DD_HHMMSS_<slug>/reply_template.md`
- `.codex/handoffs/YYYY-MM-DD_HHMMSS_<slug>/notes.md`
- `.codex/handoffs/YYYY-MM-DD_HHMMSS_<slug>/preview.json`
- `.codex/handoffs/YYYY-MM-DD_HHMMSS_<slug>/attachments/`

`manifest.json` 中所有路径都以项目根相对路径记录，便于迁移和后续自动化处理。正式交付报告会同时显示当前机器的绝对路径，方便手动定位文件。

## 真实示例

仓库包含一个可直接阅读的演示输入项目：

- [examples/sample_project/README.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/README.md)
- [examples/sample_project/DEMO.md](/Users/highj/Projects/HighJ/codex-skill-prepare-web-gpt-handoff/examples/sample_project/DEMO.md)

该示例会配套一个真实生成的 handoff 快照，展示 `brief.md`、`bundle.md`、`manifest.json`、`reply_template.md`、`notes.md` 与 `preview.json` 的实际形态。具体路径见示例项目内的说明文档。

## 预览 / 确认 / 交付流程

1. 运行 `prepare_handoff.py` 生成 handoff 包，`manifest.status` 初始为 `preview`
2. 查看终端预览或再次运行 `render_preview.py`
3. 用户显式确认后运行 `confirm_handoff.py`
4. 确认脚本会把 `manifest.status` 更新为 `confirmed`，并输出推荐发送顺序：
   1. `brief.md`
   2. `bundle.md`
   3. `reply_template.md`

## 测试

```bash
python -m unittest discover .codex/skills/prepare_web_gpt_handoff/tests -v
```

## 示例生成命令

下面的命令会以 `examples/sample_project` 作为项目根生成一个新的 handoff：

```bash
python .codex/skills/prepare_web_gpt_handoff/scripts/prepare_handoff.py \
  --project-root examples/sample_project \
  --mode strategy_research \
  --topic "为 sample_project 准备网页版 GPT 研究交接包" \
  --goal "把当前策略问题与最小必要材料整理给网页版 GPT 继续研究" \
  --focus-point "保持 minimal_sufficient_context" \
  --focus-point "明确 handoff_id 回显与最终收口格式" \
  --must-include README.md \
  --must-include docs/overview.md \
  --must-include docs/research_questions.md \
  --must-include src/selector.py \
  --must-include logs/strategy.log
```
