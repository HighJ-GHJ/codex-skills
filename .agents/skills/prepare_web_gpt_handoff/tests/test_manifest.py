"""中文说明：manifest 与 bundle 相关回归测试。

这些测试保护的是外部 contract 和回归边界，而不是内部实现细节，重点覆盖
schema、预算硬约束、结构化摘录、策略评估字段和 manifest 审计字段的一致性。
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent

import prepare_web_gpt_handoff.prepare as prepare_entry_module
import prepare_web_gpt_handoff.token_tools as token_tools_module
from prepare_web_gpt_handoff import (
    ExactTokenUnavailableError,
    HandoffInputs,
    build_token_counter,
    build_token_runtime,
    load_defaults,
    manifest_schema_path,
    prepare_handoff,
)


FIXTURE_ROOT = TESTS_DIR / "fixtures" / "sample_project"


def validate_schema(instance: object, schema: dict[str, object], path: str = "$") -> None:
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(instance, dict):
            raise AssertionError(f"{path} is not an object")
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                raise AssertionError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                validate_schema(value, properties[key], f"{path}.{key}")
    elif schema_type == "array":
        if not isinstance(instance, list):
            raise AssertionError(f"{path} is not an array")
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(instance) < min_items:
            raise AssertionError(f"{path} does not meet minItems={min_items}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(instance):
                validate_schema(value, item_schema, f"{path}[{index}]")
    elif schema_type == "string":
        if not isinstance(instance, str):
            raise AssertionError(f"{path} is not a string")
    elif schema_type == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            raise AssertionError(f"{path} is not an integer")
    elif schema_type == "boolean":
        if not isinstance(instance, bool):
            raise AssertionError(f"{path} is not a boolean")

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and instance not in enum_values:
        raise AssertionError(f"{path} is not in enum {enum_values}")


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name) / "project"
        shutil.copytree(FIXTURE_ROOT, self.project_root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def build_inputs(self, **overrides: object) -> HandoffInputs:
        payload = {
            "mode": "strategy_research",
            "topic": "Manifest fixture handoff",
            "goal": "Validate manifest generation and stable file metadata.",
            "focus_points": ["Keep schema and manifest structure stable."],
            "must_include": ["README.md", "docs/problem.md", "src/main.py"],
            "must_exclude": [],
            "max_files": 4,
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

    def test_manifest_matches_schema(self) -> None:
        result = prepare_handoff(self.project_root, self.build_inputs())
        manifest = result["manifest"]
        schema = json.loads(manifest_schema_path().read_text(encoding="utf-8"))
        validate_schema(manifest, schema)

    def test_truncation_metadata_is_stable(self) -> None:
        large_context_path = self.project_root / "docs" / "large_context.md"
        large_context_path.write_text(
            large_context_path.read_text(encoding="utf-8")
            + "\n\n# Supplemental Context\n\n"
            + ("extra signal for truncation stability\n" * 400),
            encoding="utf-8",
        )
        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=["docs/large_context.md"],
                max_files=1,
                max_bundle_tokens=720,
            ),
        )
        manifest = result["manifest"]
        file_entry = manifest["files"][0]
        self.assertEqual(file_entry["path"], "docs/large_context.md")
        self.assertTrue(file_entry["truncated"])
        self.assertGreater(file_entry["token_count_original"], file_entry["token_count_included"])
        self.assertEqual(file_entry["artifact_type"], "supporting_context")
        self.assertEqual(file_entry["context_layer"], "evidence")
        self.assertEqual(file_entry["excerpt_strategy"], "section_extract")
        self.assertEqual(file_entry["compaction_strategy"], "typed_digest_compaction")
        self.assertIn("Large Context", file_entry["excerpt_anchor"])
        self.assertTrue(file_entry["truncation_method"].startswith("typed_digest_compaction:"))

        bundle_path = self.project_root / manifest["artifacts"]["bundle_md"]
        bundle_text = bundle_path.read_text(encoding="utf-8")
        self.assertIn("excerpt_strategy", bundle_text)
        self.assertIn("compaction_strategy", bundle_text)
        self.assertIn("原始 token 数", bundle_text)
        self.assertIn("Typed digest for docs/large_context.md", bundle_text)
        self.assertIn("retained anchors: Large Context", bundle_text)

    def test_auto_selection_ignores_tests_and_nested_handoffs(self) -> None:
        nested_handoff = self.project_root / "examples" / "sample" / ".codex" / "handoffs" / "old"
        nested_handoff.mkdir(parents=True, exist_ok=True)
        (nested_handoff / "brief.md").write_text("old handoff snapshot", encoding="utf-8")
        visible_handoff = self.project_root / "examples" / "sample" / "handoffs" / "latest"
        visible_handoff.mkdir(parents=True, exist_ok=True)
        (visible_handoff / "bundle.md").write_text("visible handoff snapshot", encoding="utf-8")
        tests_dir = self.project_root / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "README.md").write_text("should not be auto-selected", encoding="utf-8")

        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=["README.md"],
                max_files=4,
            ),
        )
        selected_paths = {item["path"] for item in result["manifest"]["files"]}
        self.assertNotIn("tests/README.md", selected_paths)
        self.assertNotIn("examples/sample/.codex/handoffs/old/brief.md", selected_paths)
        self.assertNotIn("examples/sample/handoffs/latest/bundle.md", selected_paths)

    def test_bundle_hard_cap_and_low_priority_drop(self) -> None:
        extra_doc = self.project_root / "docs" / "extra_context.md"
        extra_doc.write_text("# Extra\n\n" + ("context " * 600), encoding="utf-8")

        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=["README.md"],
                max_files=5,
                max_bundle_tokens=520,
                topic="Compare workflow selection and token budget tradeoffs",
                goal="Evaluate workflow, selector, and supporting docs under a tight token budget.",
                focus_points=["workflow", "selection", "token budget", "supporting context"],
                mentioned_paths=["src/main.py"],
            ),
        )
        defaults = load_defaults()
        token_counter = build_token_counter(defaults)
        bundle_path = self.project_root / result["manifest"]["artifacts"]["bundle_md"]
        bundle_text = bundle_path.read_text(encoding="utf-8")
        self.assertLessEqual(token_counter.count(bundle_text), result["manifest"]["inputs"]["max_bundle_tokens"])
        self.assertTrue(any(not item["included_in_bundle"] for item in result["manifest"]["files"]))

    def test_bundle_layer_counts_track_real_artifacts_only(self) -> None:
        result = prepare_handoff(self.project_root, self.build_inputs(max_files=3))
        layer_counts = result["manifest"]["selection_summary"]["bundle_layer_counts"]
        self.assertEqual(layer_counts["dynamic_task"], 0)
        self.assertEqual(
            layer_counts["stable_contract"] + layer_counts["evidence"] + layer_counts["attachments"],
            len(result["manifest"]["files"]),
        )

    def test_selection_summary_exposes_strategy_and_quality_metrics(self) -> None:
        result = prepare_handoff(self.project_root, self.build_inputs(max_files=3))
        selection_summary = result["manifest"]["selection_summary"]
        self.assertIn("strategy_version", selection_summary)
        self.assertIn("bundle_order_version", selection_summary)
        self.assertIn("critical_contract_items", selection_summary)
        self.assertIn("dependency_promoted_items", selection_summary)
        self.assertIn("retrieval_gate", selection_summary)
        self.assertIn("quality_metrics", selection_summary)
        self.assertIn(selection_summary["retrieval_gate"], {"brief_only", "brief_plus_contract", "full_bundle"})
        self.assertIsInstance(selection_summary["critical_contract_items"], list)
        self.assertIsInstance(selection_summary["dependency_promoted_items"], list)
        quality_metrics = selection_summary["quality_metrics"]
        for key in [
            "contract_coverage",
            "workflow_coverage",
            "structured_extract_ratio",
            "fallback_ratio",
            "budget_compliance",
            "anchor_fidelity",
            "bundle_order_valid",
        ]:
            self.assertIn(key, quality_metrics)
        self.assertTrue(quality_metrics["budget_compliance"])
        self.assertTrue(quality_metrics["anchor_fidelity"])
        self.assertTrue(quality_metrics["bundle_order_valid"])

    def test_contract_artifacts_rank_ahead_of_supporting_docs(self) -> None:
        schemas_dir = self.project_root / "schemas"
        schemas_dir.mkdir(parents=True, exist_ok=True)
        (schemas_dir / "manifest.schema.json").write_text(
            json.dumps(
                {
                    "required": ["status"],
                    "properties": {
                        "status": {"enum": ["preview", "confirmed"]},
                        "paths": {"type": "object"},
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
            "# Reply Template\n\n## Final Output\nKeep the final reply structured.\n",
            encoding="utf-8",
        )

        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=[],
                max_files=2,
                topic="Review manifest schema and reply template contract",
                goal="Prefer contract artifacts over general supporting docs.",
                focus_points=["contract", "schema", "reply template"],
            ),
        )
        selected_paths = [item["path"] for item in result["manifest"]["files"]]
        self.assertEqual(selected_paths, ["schemas/manifest.schema.json", "templates/reply_template.md"])
        self.assertTrue(all(item["artifact_type"] == "contract" for item in result["manifest"]["files"]))

    def test_retrieval_gate_prefers_brief_plus_contract_for_narrow_contract_topics(self) -> None:
        schemas_dir = self.project_root / "schemas"
        schemas_dir.mkdir(parents=True, exist_ok=True)
        (schemas_dir / "manifest.schema.json").write_text(
            json.dumps({"required": ["status"], "properties": {"status": {"enum": ["preview", "confirmed"]}}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        templates_dir = self.project_root / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        (templates_dir / "reply_template.md").write_text(
            "# Reply Contract\n\n## Output Contract\n\nReturn YAML front matter and repeat handoff_id.\n",
            encoding="utf-8",
        )
        src_dir = self.project_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "workflow.py").write_text(
            "def confirm_preview_status() -> str:\n    return 'confirmed'\n",
            encoding="utf-8",
        )

        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=[],
                max_files=4,
                topic="Review reply template and manifest status contract",
                goal="Keep the handoff focused on schema, status transition, and reply contract.",
                focus_points=["contract", "schema", "reply template", "status"],
            ),
        )
        selection_summary = result["manifest"]["selection_summary"]
        self.assertEqual(selection_summary["retrieval_gate"], "brief_plus_contract")
        included_types = {item["artifact_type"] for item in result["manifest"]["files"] if item["included_in_bundle"]}
        self.assertTrue(included_types.issubset({"contract", "workflow"}))
        self.assertGreaterEqual(selection_summary["contract_artifacts_selected"], 1)

    def test_retrieval_gate_uses_full_bundle_for_code_tradeoff_topics(self) -> None:
        src_dir = self.project_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "workflow.py").write_text(
            "from src.helpers import normalize\n\ndef prepare_bundle(items: list[str]) -> list[str]:\n    return [normalize(item) for item in items]\n",
            encoding="utf-8",
        )
        (src_dir / "helpers.py").write_text(
            "def normalize(value: str) -> str:\n    return value.strip().lower()\n",
            encoding="utf-8",
        )

        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=[],
                max_files=4,
                topic="Compare workflow selection and token budget tradeoffs",
                goal="Evaluate workflow, selector, and budget behavior together.",
                focus_points=["workflow", "selection", "token budget", "code tradeoff"],
                mentioned_paths=["src/main.py"],
            ),
        )
        selection_summary = result["manifest"]["selection_summary"]
        self.assertEqual(selection_summary["retrieval_gate"], "full_bundle")
        included_types = {item["artifact_type"] for item in result["manifest"]["files"] if item["included_in_bundle"]}
        self.assertTrue(any(artifact_type in included_types for artifact_type in {"workflow", "selection_logic", "code_snippet"}))
        self.assertTrue(any(item["artifact_type"] == "supporting_context" for item in result["manifest"]["files"]))

    def test_contract_token_preservation_survives_typed_digest(self) -> None:
        templates_dir = self.project_root / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        long_template = "\n".join(
            [
                "---",
                "schema_version: 1",
                "handoff_id: sample",
                "status: preview",
                "generated_at: now",
                "---",
                "# Reply Template",
                "",
                "## 问题定义",
            ]
            + [f"Long contract guidance line {index} with reply_template.md and status paths artifacts." for index in range(80)]
            + [
                "## 最终结论",
                "## 推荐路线",
                "## 备选路线",
                "## 关键依据",
                "## 风险与反例",
                "## 候选论文/资料",
                "## 建议下一步",
                "## 仍未解决的问题",
            ]
        )
        (templates_dir / "reply_template.md").write_text(long_template, encoding="utf-8")

        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=["templates/reply_template.md"],
                max_files=1,
                max_bundle_tokens=520,
                topic="Preserve the reply template contract under tight budget",
                goal="Keep key contract tokens visible even when compaction is required.",
                focus_points=["reply template", "status", "handoff_id", "artifacts"],
            ),
        )
        file_entry = result["manifest"]["files"][0]
        self.assertEqual(file_entry["artifact_type"], "contract")
        self.assertTrue(file_entry["critical_token_preserved"])
        bundle_text = (self.project_root / result["manifest"]["artifacts"]["bundle_md"]).read_text(encoding="utf-8")
        for token in ["handoff_id", "status", "reply_template.md", "## 问题定义", "## 最终结论"]:
            self.assertIn(token, bundle_text)

    def test_dependency_guided_promotion_marks_promoted_files(self) -> None:
        src_dir = self.project_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "workflow.py").write_text(
            "from src.helpers import normalize_status\n\n"
            "def confirm_preview_status(raw_status: str) -> str:\n"
            "    return normalize_status(raw_status)\n",
            encoding="utf-8",
        )
        (src_dir / "helpers.py").write_text(
            "def normalize_status(value: str) -> str:\n"
            "    return value.strip().lower() or 'preview'\n",
            encoding="utf-8",
        )

        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=["src/workflow.py"],
                max_files=2,
                topic="Review workflow confirmation path and imported dependency",
                goal="Keep the workflow and its imported dependency together in the main reading layer.",
                focus_points=["workflow", "confirm", "imported dependency"],
            ),
        )
        promoted = {
            item["path"]: item
            for item in result["manifest"]["files"]
            if item["dependency_promoted"]
        }
        self.assertIn("src/helpers.py", promoted)
        self.assertIn("src/helpers.py", result["manifest"]["selection_summary"]["dependency_promoted_items"])

    def test_recursive_ast_chunking_exposes_nested_anchors(self) -> None:
        src_dir = self.project_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        large_code = """
class Planner:
    def __init__(self) -> None:
        self.steps = []

    def prepare(self, items: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in items:
            cleaned.append(item.strip().lower())
        return cleaned

    def confirm(self, status: str) -> str:
        if status.strip():
            return status.strip().lower()
        return "preview"

def orchestrate(items: list[str], status: str) -> tuple[list[str], str]:
    planner = Planner()
    prepared = planner.prepare(items)
    confirmed = planner.confirm(status)
    audit_log: list[str] = []
    for index, item in enumerate(prepared):
        audit_log.append(f"{index}:{item}")
    notes: list[str] = []
    for line in audit_log:
        notes.append(line.upper())
    summary: list[str] = []
    for item in notes:
        summary.append(item.lower())
    final_lines: list[str] = []
    for line in summary:
        final_lines.append(line + ":done")
    review_lines: list[str] = []
    for line in final_lines:
        review_lines.append(line.replace("done", "reviewed"))
    archived_lines: list[str] = []
    for line in review_lines:
        archived_lines.append(line + ":archived")
    emitted_lines: list[str] = []
    for line in archived_lines:
        emitted_lines.append(line + ":emitted")
    normalized_lines: list[str] = []
    for line in emitted_lines:
        normalized_lines.append(line.lower())
    reported_lines: list[str] = []
    for line in normalized_lines:
        reported_lines.append(line + ":reported")
    return reported_lines, confirmed
""".strip()
        (src_dir / "workflow.py").write_text(large_code, encoding="utf-8")

        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=["src/workflow.py"],
                max_files=1,
                max_bundle_tokens=820,
                topic="Review nested workflow code paths",
                goal="Expose method-level anchors when the workflow file is too large for a single symbol block.",
                focus_points=["workflow", "prepare", "confirm", "orchestrate"],
            ),
        )
        file_entry = result["manifest"]["files"][0]
        self.assertEqual(file_entry["excerpt_strategy"], "symbol_extract")
        self.assertTrue(any(anchor in file_entry["excerpt_anchor"] for anchor in ["Planner.prepare", "Planner.confirm", "orchestrate::chunk_1"]))

    def test_python_and_log_paths_choose_structured_then_fallback(self) -> None:
        log_path = self.project_root / "logs" / "run.log"
        log_path.write_text(("runtime signal\n" * 400), encoding="utf-8")
        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=["src/main.py", "logs/run.log"],
                max_files=2,
                max_bundle_tokens=760,
            ),
        )
        file_map = {item["path"]: item for item in result["manifest"]["files"]}
        python_entry = file_map["src/main.py"]
        log_entry = file_map["logs/run.log"]

        self.assertEqual(python_entry["excerpt_strategy"], "symbol_extract")
        self.assertIn("choose_route", python_entry["excerpt_anchor"])
        self.assertFalse(python_entry["fallback_used"])

        self.assertEqual(log_entry["artifact_type"], "supporting_context")
        self.assertEqual(log_entry["excerpt_strategy"], "head_tail_fallback")
        self.assertTrue(log_entry["fallback_used"])

    def test_exact_token_count_path_marks_manifest_when_tokenizer_is_available(self) -> None:
        class FakeEncoding:
            def encode(self, text: str) -> list[str]:
                return list(text)

            def decode(self, tokens: list[str]) -> str:
                return "".join(tokens)

        class FakeTiktoken:
            @staticmethod
            def get_encoding(_: str) -> FakeEncoding:
                return FakeEncoding()

        with mock.patch.object(token_tools_module, "_TIKTOKEN", FakeTiktoken()):
            result = prepare_handoff(self.project_root, self.build_inputs(max_bundle_tokens=4000))
        selection_summary = result["manifest"]["selection_summary"]
        self.assertTrue(selection_summary["token_count_method"].startswith("tiktoken:"))
        self.assertEqual(selection_summary["token_runtime"]["resolved_method"], selection_summary["token_count_method"])
        self.assertTrue(selection_summary["token_runtime"]["exact_available"])

    def test_fallback_token_count_path_marks_manifest_and_notes(self) -> None:
        with mock.patch.object(token_tools_module, "_TIKTOKEN", None):
            result = prepare_handoff(self.project_root, self.build_inputs())
        selection_summary = result["manifest"]["selection_summary"]
        self.assertEqual(selection_summary["token_count_method"], "estimated:ascii_div4_plus_non_ascii")
        self.assertFalse(selection_summary["token_runtime"]["exact_available"])
        self.assertEqual(selection_summary["token_runtime"]["fallback_reason"], "tiktoken_not_installed")
        warnings = result["manifest"]["notes"]["warnings"]
        self.assertTrue(any("tiktoken" in warning for warning in warnings))

    def test_unavailable_tiktoken_encoding_gracefully_falls_back(self) -> None:
        class BrokenTiktoken:
            @staticmethod
            def get_encoding(_: str) -> object:
                raise RuntimeError("encoding fetch failed")

        with mock.patch.object(token_tools_module, "_TIKTOKEN", BrokenTiktoken()):
            result = prepare_handoff(self.project_root, self.build_inputs())
        self.assertEqual(
            result["manifest"]["selection_summary"]["token_count_method"],
            "estimated:ascii_div4_plus_non_ascii",
        )
        self.assertTrue(
            result["manifest"]["selection_summary"]["token_runtime"]["fallback_reason"].startswith(
                "get_encoding_failed:"
            )
        )

    def test_strict_exact_mode_fails_when_exact_token_counting_is_unavailable(self) -> None:
        defaults = load_defaults()
        with mock.patch.object(token_tools_module, "_TIKTOKEN", None):
            with self.assertRaises(ExactTokenUnavailableError):
                build_token_runtime(defaults, require_exact_tokens=True)

    def test_prepare_cli_exits_cleanly_when_strict_exact_cannot_be_satisfied(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(token_tools_module, "_TIKTOKEN", None):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as error:
                    prepare_entry_module.main(
                        [
                            "--project-root",
                            str(self.project_root),
                            "--mode",
                            "strategy_research",
                            "--topic",
                            "Strict exact failure",
                            "--goal",
                            "Ensure CLI exits cleanly when exact tokens are required.",
                            "--must-include",
                            "README.md",
                            "--require-exact-tokens",
                        ]
                    )
        self.assertEqual(error.exception.code, 2)
        self.assertIn("Exact token counting required but unavailable", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
