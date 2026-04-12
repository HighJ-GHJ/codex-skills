#!/usr/bin/env python3
"""中文说明：prepare CLI 的兼容 wrapper。

真实入口位于 `prepare_web_gpt_handoff.prepare`。这里保留脚本路径，只做最薄
转发，避免旧调用方式直接失效。
"""

from __future__ import annotations

from _bootstrap import ensure_repo_root_on_syspath

ensure_repo_root_on_syspath()

from prepare_web_gpt_handoff.prepare import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
