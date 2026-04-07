"""中文说明：`config_paths` 的兼容 shim。"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from prepare_web_gpt_handoff.config_paths import *  # noqa: F401,F403,E402
