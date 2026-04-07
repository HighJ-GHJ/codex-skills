"""中文说明：仓库级公共资产回归测试。

这里校验 skill metadata、公开文档和 canonical sample snapshot，避免 public-facing
contract 在没有显式审阅的情况下发生静默漂移。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[3]
from prepare_web_gpt_handoff import parse_handoff_id_from_entry, render_preview


class RepoAssetTests(unittest.TestCase):
    def test_metadata_and_public_docs_are_present(self) -> None:
        metadata_path = REPO_ROOT / ".agents" / "skills" / "prepare_web_gpt_handoff" / "agents" / "openai.yaml"
        metadata_text = metadata_path.read_text(encoding="utf-8")
        self.assertIn('display_name: "Prepare Web GPT Handoff"', metadata_text)
        self.assertIn('short_description: "Portable handoff packaging with optional exact tokens"', metadata_text)
        self.assertIn("$prepare_web_gpt_handoff", metadata_text)
        self.assertIn("allow_implicit_invocation: true", metadata_text)

        readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Codex-first", readme_text)
        self.assertIn("不是 plugin / marketplace / installer 仓库", readme_text)
        self.assertIn("Golden Fixture", readme_text)

        agents_text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("canonical golden fixture", agents_text)
        self.assertIn("不做 plugin / marketplace / installer 化", agents_text)

    def test_canonical_sample_snapshot_is_confirmed_and_round_trippable(self) -> None:
        sample_root = REPO_ROOT / "examples" / "sample_project"
        handoffs_dir = sample_root / "handoffs"
        latest_path = handoffs_dir / "LATEST.md"
        handoff_id = parse_handoff_id_from_entry(latest_path)

        sample_dirs = [path for path in handoffs_dir.iterdir() if path.is_dir()]
        self.assertEqual(len(sample_dirs), 1)
        self.assertEqual(sample_dirs[0].name, handoff_id)

        markdown_entries = {path.name for path in handoffs_dir.glob("*.md")}
        self.assertEqual(markdown_entries, {"LATEST.md", f"{handoff_id}.md"})

        canonical_dir = handoffs_dir / handoff_id
        manifest = json.loads((canonical_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest_text = json.dumps(manifest, ensure_ascii=False)
        self.assertEqual(manifest["status"], "confirmed")
        self.assertNotIn("char_count_original", manifest_text)
        self.assertNotIn("char_count_included", manifest_text)
        self.assertIn("contract_artifacts_selected", manifest["selection_summary"])
        self.assertIn("structured_extract_files", manifest["selection_summary"])
        self.assertIn("bundle_layer_counts", manifest["selection_summary"])
        self.assertIn("strategy_version", manifest["selection_summary"])
        self.assertIn("bundle_order_version", manifest["selection_summary"])
        self.assertIn("critical_contract_items", manifest["selection_summary"])
        self.assertIn("dependency_promoted_items", manifest["selection_summary"])
        self.assertIn("token_runtime", manifest["selection_summary"])
        self.assertEqual(manifest["selection_summary"]["token_runtime"]["resolved_method"], manifest["selection_summary"]["token_count_method"])
        self.assertEqual(manifest["selection_summary"]["token_count_method"], "tiktoken:cl100k_base")
        self.assertGreater(manifest["selection_summary"]["contract_artifacts_selected"], 0)
        self.assertGreater(manifest["selection_summary"]["workflow_artifacts_selected"], 0)
        self.assertIn("context_layer", manifest["files"][0])
        self.assertIn("artifact_type", manifest["files"][0])
        self.assertIn("excerpt_strategy", manifest["files"][0])
        self.assertIn("compaction_strategy", manifest["files"][0])
        self.assertIn("dependency_promoted", manifest["files"][0])
        self.assertIn("critical_token_preserved", manifest["files"][0])
        for name in ["brief.md", "bundle.md", "manifest.json", "reply_template.md", "notes.md", "preview.json"]:
            self.assertTrue((canonical_dir / name).exists(), name)

        preview_text = render_preview(sample_root, "handoffs/LATEST.md")
        self.assertIn(f"handoff_id: {handoff_id}", preview_text)
        self.assertIn("contract 条目数:", preview_text)
        self.assertIn("top_anchors:", preview_text)


if __name__ == "__main__":
    unittest.main()
