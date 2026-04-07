"""中文说明：确认交付 handoff 的稳定包入口。"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import confirm_handoff, default_project_root


def build_parser() -> argparse.ArgumentParser:
    """中文说明：构造 confirm 子命令参数。"""

    parser = argparse.ArgumentParser(description="Confirm a prepared web GPT handoff package.")
    parser.add_argument("--project-root", default=str(default_project_root()), help="Repository root for relative paths.")
    parser.add_argument("--handoff", required=True, help="handoff_id, relative handoff path, or visible entry markdown path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """中文说明：确认交付并输出正式报告。"""

    parser = build_parser()
    args = parser.parse_args(argv)
    result = confirm_handoff(Path(args.project_root), args.handoff)
    print(result["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
