"""中文说明：真实入口一致性回归测试。

这些测试直接覆盖当前进程、`python -m` 和旧 wrapper 脚本三种入口，确保它们
在同一解释器环境下得到一致的 token 运行契约，不再出现“单测全绿但 CLI 分叉”。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from prepare_web_gpt_handoff import HandoffInputs, build_token_runtime, load_defaults, parse_handoff_id_from_entry, prepare_handoff


TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[3]
FIXTURE_ROOT = TESTS_DIR / "fixtures" / "sample_project"
WRAPPER_PREPARE = REPO_ROOT / ".agents" / "skills" / "prepare_web_gpt_handoff" / "scripts" / "prepare_handoff.py"
WRAPPER_PREVIEW = REPO_ROOT / ".agents" / "skills" / "prepare_web_gpt_handoff" / "scripts" / "render_preview.py"


class EntrypointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _make_project(self, name: str) -> Path:
        project_root = self.base_dir / name
        shutil.copytree(FIXTURE_ROOT, project_root)
        return project_root

    def _build_inputs(self, require_exact_tokens: bool = False) -> HandoffInputs:
        return HandoffInputs(
            mode="strategy_research",
            topic="Entrypoint consistency handoff",
            goal="Keep package, module, and wrapper entrypoints aligned.",
            focus_points=["Protect real runtime contract consistency."],
            must_include=["README.md", "docs/problem.md", "src/main.py"],
            must_exclude=[],
            max_files=4,
            max_bundle_tokens=900,
            background="",
            known_routes=[],
            blockers=[],
            questions=[],
            avoid_directions=[],
            output_requirements=[],
            mentioned_paths=[],
            require_exact_tokens=require_exact_tokens,
        )

    def _read_latest_manifest(self, project_root: Path) -> dict[str, object]:
        latest_entry = project_root / "handoffs" / "LATEST.md"
        handoff_id = parse_handoff_id_from_entry(latest_entry)
        manifest_path = project_root / "handoffs" / handoff_id / "manifest.json"
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def test_package_module_and_wrapper_entrypoints_share_token_runtime(self) -> None:
        package_project = self._make_project("package")
        module_project = self._make_project("module")
        wrapper_project = self._make_project("wrapper")

        direct_manifest = prepare_handoff(package_project, self._build_inputs())["manifest"]

        subprocess.run(
            [
                sys.executable,
                "-m",
                "prepare_web_gpt_handoff.prepare",
                "--project-root",
                str(module_project),
                "--mode",
                "strategy_research",
                "--topic",
                "Entrypoint consistency handoff",
                "--goal",
                "Keep package, module, and wrapper entrypoints aligned.",
                "--focus-point",
                "Protect real runtime contract consistency.",
                "--must-include",
                "README.md",
                "--must-include",
                "docs/problem.md",
                "--must-include",
                "src/main.py",
                "--max-files",
                "4",
                "--max-bundle-tokens",
                "900",
            ],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        module_manifest = self._read_latest_manifest(module_project)

        subprocess.run(
            [
                sys.executable,
                str(WRAPPER_PREPARE),
                "--project-root",
                str(wrapper_project),
                "--mode",
                "strategy_research",
                "--topic",
                "Entrypoint consistency handoff",
                "--goal",
                "Keep package, module, and wrapper entrypoints aligned.",
                "--focus-point",
                "Protect real runtime contract consistency.",
                "--must-include",
                "README.md",
                "--must-include",
                "docs/problem.md",
                "--must-include",
                "src/main.py",
                "--max-files",
                "4",
                "--max-bundle-tokens",
                "900",
            ],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        wrapper_manifest = self._read_latest_manifest(wrapper_project)

        direct_method = direct_manifest["selection_summary"]["token_count_method"]
        module_method = module_manifest["selection_summary"]["token_count_method"]
        wrapper_method = wrapper_manifest["selection_summary"]["token_count_method"]

        self.assertEqual(direct_method, module_method)
        self.assertEqual(module_method, wrapper_method)

        direct_runtime = direct_manifest["selection_summary"]["token_runtime"]
        self.assertEqual(direct_runtime, module_manifest["selection_summary"]["token_runtime"])
        self.assertEqual(direct_runtime, wrapper_manifest["selection_summary"]["token_runtime"])

        exact_available = build_token_runtime(load_defaults()).exact_available
        if exact_available:
            self.assertEqual(direct_method, "tiktoken:cl100k_base")

    def test_wrapper_preview_reads_module_generated_handoff(self) -> None:
        project_root = self._make_project("preview")
        result = prepare_handoff(project_root, self._build_inputs())
        handoff_id = result["handoff_id"]

        completed = subprocess.run(
            [
                sys.executable,
                str(WRAPPER_PREVIEW),
                "--project-root",
                str(project_root),
                "--handoff",
                f"handoffs/{handoff_id}.md",
            ],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        self.assertIn(f"handoff_id: {handoff_id}", completed.stdout)
        self.assertIn("token_count_method:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
