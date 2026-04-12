"""中文说明：`token_tools` 的兼容 shim。"""

from __future__ import annotations

from _bootstrap import ensure_repo_root_on_syspath

ensure_repo_root_on_syspath()

from prepare_web_gpt_handoff.token_tools import *  # noqa: F401,F403,E402
from prepare_web_gpt_handoff import token_tools as _package_token_tools  # noqa: E402

_TIKTOKEN = _package_token_tools._TIKTOKEN
