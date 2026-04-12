#!/usr/bin/env python3
"""中文说明：confirm CLI 的兼容 wrapper。"""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _bootstrap import ensure_repo_root_on_syspath
else:
    from ._bootstrap import ensure_repo_root_on_syspath

ensure_repo_root_on_syspath()

from prepare_web_gpt_handoff.confirm import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
