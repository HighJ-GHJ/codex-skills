"""中文说明：`token_tools` 的兼容 shim。"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from prepare_web_gpt_handoff.token_tools import *  # noqa: F401,F403,E402
from prepare_web_gpt_handoff import token_tools as _package_token_tools  # noqa: E402

_TIKTOKEN = _package_token_tools._TIKTOKEN
