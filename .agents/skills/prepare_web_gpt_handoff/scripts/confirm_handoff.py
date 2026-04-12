#!/usr/bin/env python3
"""中文说明：confirm CLI 的兼容 wrapper。"""

from __future__ import annotations

from _bootstrap import ensure_repo_root_on_syspath

ensure_repo_root_on_syspath()

from prepare_web_gpt_handoff.confirm import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
