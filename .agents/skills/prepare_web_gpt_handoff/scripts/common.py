"""中文说明：旧 `scripts/common.py` 的兼容 shim。

这个文件不再承担全系统 barrel 导出职责，只保留少量稳定 API，供历史测试、
旧文档和兼容调用路径过渡使用。真实实现统一位于仓库根的
`prepare_web_gpt_handoff` 包中。
"""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _bootstrap import ensure_repo_root_on_syspath
else:
    from ._bootstrap import ensure_repo_root_on_syspath

REPO_ROOT = ensure_repo_root_on_syspath()

from prepare_web_gpt_handoff import (  # noqa: E402
    ExactTokenUnavailableError,
    HandoffInputs,
    MIN_EXCERPT_TOKENS,
    PROJECT_ROOT_ENV_VAR,
    REPO_ROOT as PACKAGE_REPO_ROOT,
    REQUIRE_EXACT_TOKENS_ENV_VAR,
    SKILL_NAME,
    SKILL_ROOT,
    SKILL_VERSION,
    STATUS_ARCHIVED,
    STATUS_CONFIRMED,
    STATUS_PREVIEW,
    SkillDefaults,
    TokenCounter,
    TokenRuntime,
    absolute_from_relative,
    build_token_counter,
    build_token_runtime,
    confirm_handoff,
    default_project_root,
    defaults_path,
    discover_project_root,
    ensure_within_project_root,
    is_probably_text,
    load_defaults,
    manifest_schema_path,
    normalize_pattern,
    parse_handoff_id_from_entry,
    prepare_handoff,
    read_json,
    render_preview,
    require_exact_tokens_from_env,
    resolve_handoff_dir,
    resolve_pattern,
    scan_project_files,
    skill_root,
    to_repo_relative,
    visible_handoff_dir,
    visible_handoffs_dir,
)

assert PACKAGE_REPO_ROOT == REPO_ROOT

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
