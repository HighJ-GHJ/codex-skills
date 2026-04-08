"""中文说明：跨 skill 共用的仓库路径工具。

这些函数只处理 repo-relative / absolute path 的稳定转换与边界校验，不携带
任何 handoff-specific 规则，避免共享层被业务语义污染。
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath


def normalize_pattern(value: str) -> str:
    """中文说明：把输入路径模式归一化为稳定的 POSIX 风格文本。"""

    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def to_repo_relative(path: Path, project_root: Path) -> str:
    """中文说明：把绝对路径转换为项目根相对路径。"""

    resolved_root = project_root.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Path {resolved_path} is outside project root {resolved_root}") from exc
    if not relative.parts:
        return "."
    return PurePosixPath(relative).as_posix()


def absolute_from_relative(project_root: Path, relative_path: str) -> Path:
    """中文说明：从项目根相对路径恢复绝对路径。"""

    if relative_path == ".":
        return project_root.resolve()
    return (project_root / Path(*PurePosixPath(relative_path).parts)).resolve()


def ensure_within_project_root(path: Path, project_root: Path, description: str) -> Path:
    """中文说明：确保路径没有逃逸出项目根。"""

    resolved_root = project_root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{description} must stay inside project root: {resolved_path}") from exc
    return resolved_path
