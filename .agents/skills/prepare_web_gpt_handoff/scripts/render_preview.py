#!/usr/bin/env python3
"""中文说明：preview CLI 的兼容 wrapper。"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from prepare_web_gpt_handoff.preview import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
