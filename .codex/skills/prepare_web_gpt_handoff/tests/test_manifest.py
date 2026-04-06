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

from common import HandoffInputs, manifest_schema_path, prepare_handoff  # noqa: E402


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
            "max_bundle_chars": 2400,
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
        result = prepare_handoff(
            self.project_root,
            self.build_inputs(
                must_include=["docs/large_context.md"],
                max_files=1,
                max_bundle_chars=1200,
            ),
        )
        manifest = result["manifest"]
        file_entry = manifest["files"][0]
        self.assertEqual(file_entry["path"], "docs/large_context.md")
        self.assertTrue(file_entry["truncated"])
        self.assertGreater(file_entry["char_count_original"], file_entry["char_count_included"])
        self.assertNotEqual(file_entry["truncation_method"], "full_text")

        bundle_path = self.project_root / manifest["artifacts"]["bundle_md"]
        bundle_text = bundle_path.read_text(encoding="utf-8")
        self.assertIn("截断说明", bundle_text)
        self.assertIn("truncated", bundle_text)


if __name__ == "__main__":
    unittest.main()
