#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from common import confirm_handoff, default_project_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Confirm a handoff and print the final delivery report.")
    parser.add_argument("--project-root", default=str(default_project_root()), help="Repository root for relative paths.")
    parser.add_argument("--handoff", required=True, help="Handoff id, handoff directory, or preview/manifest path.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = confirm_handoff(Path(args.project_root), args.handoff)
    print(result["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
