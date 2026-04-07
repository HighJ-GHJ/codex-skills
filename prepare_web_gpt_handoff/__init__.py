"""中文说明：`prepare_web_gpt_handoff` 的稳定公共 API。

这个包是 skill 的唯一核心实现来源。外部调用、测试和兼容 wrapper 都应优先
从这里导入，而不是继续依赖 `scripts/` 下的裸模块链路。
"""

from __future__ import annotations

from .config_paths import (
    HandoffInputs,
    MIN_EXCERPT_TOKENS,
    PROJECT_ROOT_ENV_VAR,
    REPO_ROOT,
    REQUIRE_EXACT_TOKENS_ENV_VAR,
    SKILL_NAME,
    SKILL_ROOT,
    SKILL_VERSION,
    STATUS_ARCHIVED,
    STATUS_CONFIRMED,
    STATUS_PREVIEW,
    SkillDefaults,
    absolute_from_relative,
    default_project_root,
    defaults_path,
    discover_project_root,
    ensure_within_project_root,
    load_defaults,
    manifest_schema_path,
    normalize_pattern,
    read_json,
    require_exact_tokens_from_env,
    skill_root,
    to_repo_relative,
    visible_handoff_dir,
    visible_handoffs_dir,
)
from .selection import is_probably_text, resolve_pattern, scan_project_files
from .token_tools import ExactTokenUnavailableError, TokenCounter, TokenRuntime, build_token_counter, build_token_runtime
from .workflow import confirm_handoff, parse_handoff_id_from_entry, prepare_handoff, render_preview, resolve_handoff_dir

__all__ = [
    "ExactTokenUnavailableError",
    "HandoffInputs",
    "MIN_EXCERPT_TOKENS",
    "PROJECT_ROOT_ENV_VAR",
    "REPO_ROOT",
    "REQUIRE_EXACT_TOKENS_ENV_VAR",
    "SKILL_NAME",
    "SKILL_ROOT",
    "SKILL_VERSION",
    "STATUS_ARCHIVED",
    "STATUS_CONFIRMED",
    "STATUS_PREVIEW",
    "SkillDefaults",
    "TokenCounter",
    "TokenRuntime",
    "absolute_from_relative",
    "build_token_counter",
    "build_token_runtime",
    "confirm_handoff",
    "default_project_root",
    "defaults_path",
    "discover_project_root",
    "ensure_within_project_root",
    "is_probably_text",
    "load_defaults",
    "manifest_schema_path",
    "normalize_pattern",
    "parse_handoff_id_from_entry",
    "prepare_handoff",
    "read_json",
    "render_preview",
    "require_exact_tokens_from_env",
    "resolve_handoff_dir",
    "resolve_pattern",
    "scan_project_files",
    "skill_root",
    "to_repo_relative",
    "visible_handoff_dir",
    "visible_handoffs_dir",
]
