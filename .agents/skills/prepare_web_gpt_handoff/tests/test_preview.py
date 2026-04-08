"""中文说明：preview / confirm 与用户可见输出回归测试。

这些测试保护两阶段交付流程、preview 字段完整性，以及用户在 handoffs/ 中
看到的统计信息与主阅读层排序是否一致。
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
from prepare_web_gpt_handoff import HandoffInputs, confirm_handoff, prepare_handoff, render_preview


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
            "max_bundle_tokens": 900,
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
            "contract_count",
            "workflow_count",
            "structured_extract_count",
            "fallback_count",
            "retrieval_gate",
            "quality_metrics",
            "selector_engine",
            "repo_graph",
            "explanation",
            "brief_summary",
            "file_list_summary",
            "top_anchors",
            "next_actions",
        ]:
            self.assertIn(key, preview)

        preview_text = render_preview(self.project_root, result["handoff_id"])
        self.assertIn("mode:", preview_text)
        self.assertIn("topic:", preview_text)
        self.assertIn("handoff_id:", preview_text)
        self.assertIn("选入文件数:", preview_text)
        self.assertIn("contract 条目数:", preview_text)
        self.assertIn("结构化摘录数:", preview_text)
        self.assertIn("top_anchors:", preview_text)
        self.assertIn("文件清单摘要:", preview_text)
        self.assertIn("下一步可选动作:", preview_text)
        self.assertIn("selector_engine:", preview_text)
        self.assertIn("two_hop_triggered:", preview_text)
        self.assertIn("explanation_coverage:", preview_text)
        self.assertIn("retrieval_gate", preview)
        self.assertIn("bundle_order_valid", preview["quality_metrics"])
        self.assertTrue(preview["selector_engine"]["graph_assisted"])

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
        latest_entry = (self.project_root / "handoffs" / "LATEST.md").read_text(encoding="utf-8")
        self.assertIn("status: `confirmed`", latest_entry)
        self.assertTrue((self.project_root / "handoffs" / result["handoff_id"] / "bundle.md").exists())

    def test_visible_entry_files_round_trip_through_cli_inputs(self) -> None:
        result = prepare_handoff(self.project_root, self.build_inputs())
        preview_text = render_preview(self.project_root, "handoffs/LATEST.md")
        self.assertIn(f"handoff_id: {result['handoff_id']}", preview_text)

        confirmation = confirm_handoff(self.project_root, f"handoffs/{result['handoff_id']}.md")
        self.assertEqual(confirmation["manifest"]["status"], "confirmed")

    def test_bundle_places_contract_and_workflow_before_supporting_context(self) -> None:
        schemas_dir = self.project_root / "schemas"
        schemas_dir.mkdir(parents=True, exist_ok=True)
        (schemas_dir / "manifest.schema.json").write_text(
            json.dumps(
                {
                    "required": ["handoff_id", "status", "paths", "artifacts"],
                    "properties": {
                        "status": {"enum": ["preview", "confirmed", "archived"]},
                        "paths": {"type": "object"},
                        "artifacts": {"type": "object"},
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        templates_dir = self.project_root / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        (templates_dir / "reply_template.md").write_text(
            "# Reply Template\n\n## Output Contract\nKeep handoff_id and status stable.\n",
            encoding="utf-8",
        )
        src_dir = self.project_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "workflow.py").write_text(
            "def build_preview_state() -> str:\n    return 'preview'\n\n"
            "def confirm_state() -> str:\n    return 'confirmed'\n",
            encoding="utf-8",
        )

        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=["README.md", "schemas/manifest.schema.json", "templates/reply_template.md", "src/workflow.py"],
                max_files=4,
                topic="Verify contract and workflow ordering in the bundle",
                goal="Keep contract and workflow entries ahead of supporting context in the main reading layer.",
                focus_points=["contract", "workflow", "ordering"],
            ),
        )
        bundle_text = (self.project_root / result["manifest"]["artifacts"]["bundle_md"]).read_text(encoding="utf-8")
        contract_index = bundle_text.index("### schemas/manifest.schema.json")
        workflow_index = bundle_text.index("### src/workflow.py")
        supporting_index = bundle_text.index("### README.md")
        self.assertLess(contract_index, workflow_index)
        self.assertLess(workflow_index, supporting_index)
        self.assertTrue(result["preview"]["quality_metrics"]["bundle_order_valid"])


if __name__ == "__main__":
    unittest.main()
