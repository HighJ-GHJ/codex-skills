"""中文说明：本模块负责稳定配置加载、项目根发现与路径契约。

这里的目标不是“从当前文件位置猜项目根”，而是为包入口、wrapper 脚本、
测试和 Agent 运行提供同一套仓库发现与环境开关规则，避免不同执行姿势下
出现不同的 project_root 或 token 运行策略。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from string import Template
from typing import Any, Iterable


SKILL_NAME = "prepare_web_gpt_handoff"
SKILL_VERSION = "0.2.0"
STATUS_PREVIEW = "preview"
STATUS_CONFIRMED = "confirmed"
STATUS_ARCHIVED = "archived"
MIN_EXCERPT_TOKENS = 96
PROJECT_ROOT_ENV_VAR = "PREPARE_WEB_GPT_HANDOFF_PROJECT_ROOT"
REQUIRE_EXACT_TOKENS_ENV_VAR = "PREPARE_WEB_GPT_HANDOFF_REQUIRE_EXACT_TOKENS"

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
SKILL_ROOT = REPO_ROOT / ".agents" / "skills" / SKILL_NAME


@dataclass(frozen=True)
class SkillDefaults:
    skill_name: str
    skill_version: str
    default_mode: str
    max_files: int
    max_bundle_tokens: int
    per_file_token_limit: int
    brief_summary_tokens: int
    tokenizer_encoding: str
    fallback_token_count_method: str
    excluded_dirs: tuple[str, ...]
    excluded_suffixes: tuple[str, ...]
    excluded_names: tuple[str, ...]
    default_next_actions: tuple[str, ...]


@dataclass
class HandoffInputs:
    mode: str
    topic: str
    goal: str
    focus_points: list[str] = field(default_factory=list)
    must_include: list[str] = field(default_factory=list)
    must_exclude: list[str] = field(default_factory=list)
    max_files: int = 8
    max_bundle_tokens: int = 4096
    background: str = ""
    known_routes: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    avoid_directions: list[str] = field(default_factory=list)
    output_requirements: list[str] = field(default_factory=list)
    mentioned_paths: list[str] = field(default_factory=list)
    require_exact_tokens: bool = False

    def normalized(self) -> "HandoffInputs":
        normalized = HandoffInputs(
            mode=self.mode.strip(),
            topic=self.topic.strip(),
            goal=self.goal.strip(),
            focus_points=dedupe_strings(self.focus_points),
            must_include=dedupe_strings(self.must_include),
            must_exclude=dedupe_strings(self.must_exclude),
            max_files=self.max_files,
            max_bundle_tokens=self.max_bundle_tokens,
            background=self.background.strip(),
            known_routes=dedupe_strings(self.known_routes),
            blockers=dedupe_strings(self.blockers),
            questions=dedupe_strings(self.questions),
            avoid_directions=dedupe_strings(self.avoid_directions),
            output_requirements=dedupe_strings(self.output_requirements),
            mentioned_paths=dedupe_strings(self.mentioned_paths),
            require_exact_tokens=self.require_exact_tokens,
        )
        normalized.validate()
        return normalized

    def validate(self) -> None:
        if not self.mode:
            raise ValueError("mode must not be empty")
        if not self.topic:
            raise ValueError("topic must not be empty")
        if not self.goal:
            raise ValueError("goal must not be empty")
        if self.max_files < 1:
            raise ValueError("max_files must be at least 1")
        if self.max_bundle_tokens < MIN_EXCERPT_TOKENS:
            raise ValueError(f"max_bundle_tokens must be at least {MIN_EXCERPT_TOKENS}")
        if not isinstance(self.require_exact_tokens, bool):
            raise ValueError("require_exact_tokens must be a boolean")


def skill_root() -> Path:
    return SKILL_ROOT


def _read_bool_env(name: str) -> bool:
    """中文说明：把环境变量解析为稳定布尔值，避免入口各自实现。"""

    raw = os.environ.get(name, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def require_exact_tokens_from_env() -> bool:
    """中文说明：读取 strict-exact 模式环境开关。"""

    return _read_bool_env(REQUIRE_EXACT_TOKENS_ENV_VAR)


def discover_project_root(start: Path | None = None) -> Path:
    """中文说明：从显式环境变量或当前工作目录向上发现项目根。

    包化后模块文件位置不再等于目标仓库位置，因此默认项目根不能继续绑定
    模块物理路径。这里优先尊重环境变量，其次从给定起点或当前工作目录向上
    搜索仓库标记；若都找不到，则退回起点本身。
    """

    if configured := os.environ.get(PROJECT_ROOT_ENV_VAR):
        configured_path = Path(configured).expanduser()
        if configured_path.exists():
            return configured_path.resolve()

    base = (start or Path.cwd()).expanduser().resolve()
    if base.is_file():
        base = base.parent

    for candidate in (base, *base.parents):
        if (candidate / ".git").exists():
            return candidate
        if (candidate / ".agents").exists() and (candidate / "pyproject.toml").exists():
            return candidate
    return base


def default_project_root() -> Path:
    return discover_project_root()


def defaults_path() -> Path:
    return SKILL_ROOT / "config" / "defaults.yaml"


def manifest_schema_path() -> Path:
    return SKILL_ROOT / "schemas" / "manifest.schema.json"


def visible_handoffs_dir(project_root: Path) -> Path:
    return project_root / "handoffs"


def visible_handoff_dir(project_root: Path, handoff_id: str) -> Path:
    return visible_handoffs_dir(project_root) / handoff_id


def dedupe_strings(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def normalize_pattern(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def strip_inline_comment(raw_line: str) -> str:
    in_single = False
    in_double = False
    result: list[str] = []
    for index, char in enumerate(raw_line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or raw_line[index - 1].isspace():
                break
        result.append(char)
    return "".join(result).rstrip()


def parse_scalar(value: str) -> str | int | bool:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("empty scalar values are not allowed")
    if cleaned.startswith(("'", '"')):
        quote = cleaned[0]
        if len(cleaned) < 2 or cleaned[-1] != quote:
            raise ValueError(f"unterminated quoted scalar: {value}")
        return cleaned[1:-1]
    lowered = cleaned.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if cleaned.isdigit():
        return int(cleaned)
    return cleaned


def validate_defaults(raw_defaults: dict[str, Any]) -> SkillDefaults:
    allowed_keys = {
        "skill_name",
        "skill_version",
        "default_mode",
        "max_files",
        "max_bundle_tokens",
        "per_file_token_limit",
        "brief_summary_tokens",
        "tokenizer_encoding",
        "fallback_token_count_method",
        "excluded_dirs",
        "excluded_suffixes",
        "excluded_names",
        "default_next_actions",
    }
    missing = allowed_keys.difference(raw_defaults)
    if missing:
        raise ValueError(f"Missing config keys: {', '.join(sorted(missing))}")
    unknown = set(raw_defaults).difference(allowed_keys)
    if unknown:
        raise ValueError(f"Unknown config keys: {', '.join(sorted(unknown))}")

    def require_int(key: str) -> int:
        value = raw_defaults[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{key} must be an integer")
        return value

    def require_str(key: str) -> str:
        value = raw_defaults[key]
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        if not value.strip():
            raise ValueError(f"{key} must not be empty")
        return value.strip()

    def require_str_list(key: str) -> tuple[str, ...]:
        value = raw_defaults[key]
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list")
        result: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"{key} must contain only strings")
            cleaned = item.strip()
            if not cleaned:
                raise ValueError(f"{key} must not contain empty items")
            result.append(cleaned)
        return tuple(result)

    fallback_method = require_str("fallback_token_count_method")
    if fallback_method != "ascii_div4_plus_non_ascii":
        raise ValueError("fallback_token_count_method must be ascii_div4_plus_non_ascii")

    defaults = SkillDefaults(
        skill_name=require_str("skill_name"),
        skill_version=require_str("skill_version"),
        default_mode=require_str("default_mode"),
        max_files=require_int("max_files"),
        max_bundle_tokens=require_int("max_bundle_tokens"),
        per_file_token_limit=require_int("per_file_token_limit"),
        brief_summary_tokens=require_int("brief_summary_tokens"),
        tokenizer_encoding=require_str("tokenizer_encoding"),
        fallback_token_count_method=fallback_method,
        excluded_dirs=require_str_list("excluded_dirs"),
        excluded_suffixes=require_str_list("excluded_suffixes"),
        excluded_names=require_str_list("excluded_names"),
        default_next_actions=require_str_list("default_next_actions"),
    )
    if defaults.max_files < 1:
        raise ValueError("max_files must be at least 1")
    if defaults.max_bundle_tokens < MIN_EXCERPT_TOKENS:
        raise ValueError(f"max_bundle_tokens must be at least {MIN_EXCERPT_TOKENS}")
    if defaults.per_file_token_limit < MIN_EXCERPT_TOKENS:
        raise ValueError(f"per_file_token_limit must be at least {MIN_EXCERPT_TOKENS}")
    if defaults.brief_summary_tokens < 16:
        raise ValueError("brief_summary_tokens must be at least 16")
    return defaults


def load_defaults(path: Path | None = None) -> SkillDefaults:
    source = path or defaults_path()
    expected_list_keys = {
        "excluded_dirs",
        "excluded_suffixes",
        "excluded_names",
        "default_next_actions",
    }
    expected_scalar_keys = {
        "skill_name",
        "skill_version",
        "default_mode",
        "max_files",
        "max_bundle_tokens",
        "per_file_token_limit",
        "brief_summary_tokens",
        "tokenizer_encoding",
        "fallback_token_count_method",
    }

    data: dict[str, Any] = {}
    current_list_key: str | None = None
    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        line = strip_inline_comment(raw_line)
        if not line.strip():
            continue
        if line.startswith(" "):
            if current_list_key is None or not line.startswith("  - "):
                raise ValueError(f"Unsupported indentation in {source}:{line_number}")
            data[current_list_key].append(parse_scalar(line[4:]))
            continue

        current_list_key = None
        key, separator, remainder = line.partition(":")
        if not separator:
            raise ValueError(f"Invalid config line in {source}:{line_number}: {raw_line}")
        key = key.strip()
        remainder = remainder.strip()
        if key in data:
            raise ValueError(f"Duplicate config key in {source}:{line_number}: {key}")
        if key in expected_list_keys:
            if remainder:
                raise ValueError(f"List key must use block syntax in {source}:{line_number}: {key}")
            data[key] = []
            current_list_key = key
            continue
        if key not in expected_scalar_keys:
            raise ValueError(f"Unknown config key in {source}:{line_number}: {key}")
        if not remainder:
            raise ValueError(f"Scalar key must provide a value in {source}:{line_number}: {key}")
        data[key] = parse_scalar(remainder)

    return validate_defaults(data)


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso_now() -> str:
    return now_local().isoformat(timespec="seconds")


def timestamp_for_id() -> str:
    return now_local().strftime("%Y-%m-%d_%H%M%S")


def slugify(text: str, max_length: int = 40) -> str:
    slug = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "_", text.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    slug = slug or SKILL_NAME
    return slug[:max_length].rstrip("_") or SKILL_NAME


def to_repo_relative(path: Path, project_root: Path) -> str:
    resolved_root = project_root.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Path {resolved_path} is outside project root {resolved_root}") from exc
    if not relative.parts:
        return "."
    return PurePosixPath(relative).as_posix()


def absolute_from_relative(project_root: Path, relative_path: str) -> Path:
    if relative_path == ".":
        return project_root.resolve()
    return (project_root / Path(*PurePosixPath(relative_path).parts)).resolve()


def ensure_within_project_root(path: Path, project_root: Path, description: str) -> Path:
    resolved_root = project_root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{description} must stay inside project root: {resolved_path}") from exc
    return resolved_path


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_template(template_name: str, context: dict[str, Any]) -> str:
    template_path = SKILL_ROOT / "templates" / template_name
    template = Template(template_path.read_text(encoding="utf-8"))
    return template.safe_substitute({key: stringify(value) for key, value in context.items()})


def stringify(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)
