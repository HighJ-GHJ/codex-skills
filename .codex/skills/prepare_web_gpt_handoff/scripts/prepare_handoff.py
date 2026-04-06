#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from common import HandoffInputs, default_project_root, load_defaults, prepare_handoff


def build_parser() -> argparse.ArgumentParser:
    defaults = load_defaults()
    parser = argparse.ArgumentParser(description="Prepare a web GPT handoff package in preview status.")
    parser.add_argument("--project-root", default=str(default_project_root()), help="Repository root for relative paths.")
    parser.add_argument("--mode", default=str(defaults.get("default_mode", "strategy_research")), help="Handoff mode.")
    parser.add_argument("--topic", required=True, help="Short topic for the handoff.")
    parser.add_argument("--goal", required=True, help="Task goal for web GPT.")
    parser.add_argument("--focus-point", action="append", default=[], help="Key focus point to keep web GPT on track.")
    parser.add_argument("--must-include", action="append", default=[], help="Relative file path or glob that must be selected.")
    parser.add_argument("--must-exclude", action="append", default=[], help="Relative file path or glob that must be excluded.")
    parser.add_argument("--mentioned-path", action="append", default=[], help="File explicitly mentioned in the current discussion.")
    parser.add_argument("--background", default="", help="Optional background paragraph for brief.md.")
    parser.add_argument("--known-route", action="append", default=[], help="Known route or attempted direction.")
    parser.add_argument("--blocker", action="append", default=[], help="Current blocker.")
    parser.add_argument("--question", action="append", default=[], help="Question web GPT should answer.")
    parser.add_argument("--avoid-direction", action="append", default=[], help="Direction web GPT should avoid.")
    parser.add_argument("--output-requirement", action="append", default=[], help="Output requirement for the final reply.")
    parser.add_argument("--max-files", type=int, default=int(defaults.get("max_files", 8)), help="Maximum selected files.")
    parser.add_argument(
        "--max-bundle-chars",
        type=int,
        default=int(defaults.get("max_bundle_chars", 14000)),
        help="Target maximum bundle character budget.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    inputs = HandoffInputs(
        mode=args.mode,
        topic=args.topic,
        goal=args.goal,
        focus_points=args.focus_point,
        must_include=args.must_include,
        must_exclude=args.must_exclude,
        max_files=args.max_files,
        max_bundle_chars=args.max_bundle_chars,
        background=args.background,
        known_routes=args.known_route,
        blockers=args.blocker,
        questions=args.question,
        avoid_directions=args.avoid_direction,
        output_requirements=args.output_requirement,
        mentioned_paths=args.mentioned_path,
    )
    result = prepare_handoff(Path(args.project_root), inputs)
    print(result["preview_text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
