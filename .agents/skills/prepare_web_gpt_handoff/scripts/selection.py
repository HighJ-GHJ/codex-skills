"""中文说明：`selection` 的兼容 shim。"""

from __future__ import annotations

from _bootstrap import ensure_repo_root_on_syspath

ensure_repo_root_on_syspath()

from prepare_web_gpt_handoff.selection import *  # noqa: F401,F403,E402
