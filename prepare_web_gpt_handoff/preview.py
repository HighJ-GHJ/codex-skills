"""中文说明：渲染 handoff preview 的稳定包入口。"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import default_project_root, render_preview


def build_parser() -> argparse.ArgumentParser:
    """中文说明：构造 preview 子命令参数。"""

    parser = argparse.ArgumentParser(description="Render a previously prepared web GPT handoff preview.")
    parser.add_argument("--project-root", default=str(default_project_root()), help="Repository root for relative paths.")
    parser.add_argument("--handoff", required=True, help="handoff_id, relative handoff path, or visible entry markdown path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """中文说明：读取 preview 并输出终端文本。"""

    parser = build_parser()
    args = parser.parse_args(argv)
    print(render_preview(Path(args.project_root), args.handoff))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
