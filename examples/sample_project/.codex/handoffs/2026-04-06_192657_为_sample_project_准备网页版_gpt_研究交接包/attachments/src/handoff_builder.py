from __future__ import annotations

from pathlib import Path


def relative_paths(paths: list[Path], project_root: Path) -> list[str]:
    return [path.resolve().relative_to(project_root.resolve()).as_posix() for path in paths]


def recommended_send_order() -> list[str]:
    return ["brief.md", "bundle.md", "reply_template.md"]
