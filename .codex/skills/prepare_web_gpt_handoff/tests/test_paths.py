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

from common import (  # noqa: E402
    HandoffInputs,
    absolute_from_relative,
    load_defaults,
    prepare_handoff,
    resolve_pattern,
    scan_project_files,
    to_repo_relative,
)


FIXTURE_ROOT = TESTS_DIR / "fixtures" / "sample_project"


class BaseProjectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name) / "project"
        shutil.copytree(FIXTURE_ROOT, self.project_root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def build_inputs(self, **overrides: object) -> HandoffInputs:
        payload = {
            "mode": "strategy_research",
            "topic": "Fixture handoff",
            "goal": "Prepare a stable handoff package for a strategy discussion.",
            "focus_points": ["Keep the context portable and minimal."],
            "must_include": ["README.md", "docs/problem.md"],
            "must_exclude": [],
            "max_files": 4,
            "max_bundle_chars": 2200,
            "background": "The fixture project simulates a repository with a few representative files.",
            "known_routes": ["Use a two-phase preview and confirm workflow."],
            "blockers": ["Need to keep only relative paths in the manifest."],
            "questions": ["Which files should stay in the main reading layer?"],
            "avoid_directions": ["Do not turn the task into a direct code implementation request."],
            "output_requirements": ["Return a structure that can be sent to web GPT manually."],
            "mentioned_paths": [],
        }
        payload.update(overrides)
        return HandoffInputs(**payload)


class PathTests(BaseProjectTest):
    def test_relative_paths_are_posix_and_windows_input_resolves(self) -> None:
        defaults = load_defaults()
        candidates, _ = scan_project_files(self.project_root, defaults)
        matches = resolve_pattern("src\\main.py", self.project_root, candidates)
        self.assertEqual(matches, ["src/main.py"])

        absolute_path = self.project_root / "src" / "main.py"
        relative_path = to_repo_relative(absolute_path, self.project_root)
        self.assertEqual(relative_path, "src/main.py")
        self.assertEqual(absolute_from_relative(self.project_root, relative_path), absolute_path.resolve())

    def test_prepare_creates_complete_handoff_directory(self) -> None:
        result = prepare_handoff(self.project_root, self.build_inputs())
        handoff_dir = result["handoff_dir"]
        for name in ["brief.md", "bundle.md", "manifest.json", "reply_template.md", "notes.md", "preview.json"]:
            self.assertTrue((handoff_dir / name).exists(), name)
        self.assertTrue((handoff_dir / "attachments").exists())

        manifest = json.loads((handoff_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest_text = json.dumps(manifest, ensure_ascii=False)
        self.assertTrue(manifest["paths"]["handoff_dir"].startswith(".codex/handoffs/"))
        self.assertNotIn(str(self.project_root), manifest_text)


if __name__ == "__main__":
    unittest.main()
