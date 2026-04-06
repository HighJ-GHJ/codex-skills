from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common import HandoffInputs, confirm_handoff, prepare_handoff, render_preview  # noqa: E402


FIXTURE_ROOT = TESTS_DIR / "fixtures" / "sample_project"


class PreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name) / "project"
        shutil.copytree(FIXTURE_ROOT, self.project_root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def build_inputs(self, **overrides: object) -> HandoffInputs:
        payload = {
            "mode": "strategy_research",
            "topic": "Preview fixture handoff",
            "goal": "Exercise preview and confirm output.",
            "focus_points": ["Preview should show the user enough information before confirmation."],
            "must_include": ["README.md", "docs/problem.md"],
            "must_exclude": [],
            "max_files": 3,
            "max_bundle_chars": 2200,
            "background": "",
            "known_routes": [],
            "blockers": [],
            "questions": [],
            "avoid_directions": [],
            "output_requirements": [],
            "mentioned_paths": [],
        }
        payload.update(overrides)
        return HandoffInputs(**payload)

    def test_preview_contains_required_fields(self) -> None:
        result = prepare_handoff(self.project_root, self.build_inputs())
        preview = result["preview"]
        for key in [
            "mode",
            "topic",
            "handoff_id",
            "selected_file_count",
            "truncated_file_count",
            "excluded_file_count",
            "brief_summary",
            "file_list_summary",
            "next_actions",
        ]:
            self.assertIn(key, preview)

        preview_text = render_preview(self.project_root, result["handoff_id"])
        self.assertIn("mode:", preview_text)
        self.assertIn("topic:", preview_text)
        self.assertIn("handoff_id:", preview_text)
        self.assertIn("选入文件数:", preview_text)
        self.assertIn("文件清单摘要:", preview_text)
        self.assertIn("下一步可选动作:", preview_text)

    def test_confirm_updates_status_and_delivery_report(self) -> None:
        result = prepare_handoff(self.project_root, self.build_inputs())
        confirmation = confirm_handoff(self.project_root, result["handoff_id"])
        manifest_path = self.project_root / confirmation["manifest"]["artifacts"]["manifest_json"]
        preview_path = self.project_root / confirmation["manifest"]["artifacts"]["preview_json"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        preview = json.loads(preview_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["status"], "confirmed")
        self.assertEqual(preview["status"], "confirmed")
        self.assertIn("handoff 目录相对路径", confirmation["report"])
        self.assertIn("当前机器绝对路径", confirmation["report"])
        self.assertIn("brief.md 路径", confirmation["report"])
        self.assertIn("推荐发送顺序", confirmation["report"])


if __name__ == "__main__":
    unittest.main()
