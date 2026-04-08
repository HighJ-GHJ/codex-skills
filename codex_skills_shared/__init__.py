"""中文说明：跨 skill 共享的稳定公共实现层。

这个包只承接跨 skill 中立、边界清晰、对零安装运行方式友好的公共逻辑。
具体业务 workflow、模板、schema 和 skill metadata 不应放在这里。
"""

from __future__ import annotations

from .repo_paths import absolute_from_relative, ensure_within_project_root, normalize_pattern, to_repo_relative
from .token_runtime import (
    DEFAULT_TIKTOKEN,
    ExactTokenUnavailableError,
    TokenCounter,
    TokenRuntime,
    build_token_counter,
    build_token_runtime,
)

__all__ = [
    "DEFAULT_TIKTOKEN",
    "ExactTokenUnavailableError",
    "TokenCounter",
    "TokenRuntime",
    "absolute_from_relative",
    "build_token_counter",
    "build_token_runtime",
    "ensure_within_project_root",
    "normalize_pattern",
    "to_repo_relative",
]
