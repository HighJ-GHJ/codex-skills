"""中文说明：兼容 wrapper 的统一引导逻辑。

集中处理 repo root 解析与 `sys.path` 注入，避免每个 wrapper 重复拷贝同一段
样板代码，降低目录层级或入口调整时的维护成本。
"""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_root_on_syspath() -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    return repo_root

