---
name: prepare_web_gpt_handoff
description: Prepare a portable handoff package for continuing the current Codex strategy discussion or research task in web GPT. Use it to generate brief.md, bundle.md, manifest.json, reply_template.md, notes.md, and preview.json, then wait for explicit user confirmation before final delivery.
---

# prepare_web_gpt_handoff

Use this skill when the user wants to move a strategy discussion, option comparison, or research-oriented thread from Codex to web GPT without automating the browser. This skill is for packaging context, not for sending messages or importing replies.

## Workflow

1. Extract or confirm the handoff inputs from the current discussion:
   - `mode`
   - `topic`
   - `goal`
   - `focus_points`
   - `must_include`
   - `must_exclude`
   - `max_files`
   - `max_bundle_chars`
2. If the discussion already contains richer context, also pass optional inputs so `brief.md` is stronger:
   - `background`
   - `known_route`
   - `blocker`
   - `question`
   - `avoid_direction`
   - `output_requirement`
   - `mentioned_path`
3. Run the generator from the repository root:

```bash
python .codex/skills/prepare_web_gpt_handoff/scripts/prepare_handoff.py --mode strategy_research --topic "..." --goal "..." --focus-point "..." --must-include README.md
```

4. Show the preview and stop. Do not treat preview as final delivery.
5. Only after the user explicitly confirms, run:

```bash
python .codex/skills/prepare_web_gpt_handoff/scripts/confirm_handoff.py --handoff .codex/handoffs/<handoff_id>
```

## Guardrails

- Keep the task framed as strategy discussion or research, not code implementation
- Prefer minimal sufficient context over large bundles
- Keep all manifest paths relative to the project root
- Do not automate browser actions
- Do not assume Codex can remember the handoff later; always rely on `handoff_id`

## Outputs

The handoff package always includes:

- `brief.md`
- `bundle.md`
- `manifest.json`
- `reply_template.md`
- `notes.md`
- `preview.json`
- `attachments/`

The recommended send order is:

1. `brief.md`
2. `bundle.md`
3. `reply_template.md`
