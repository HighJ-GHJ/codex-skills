"""中文说明：本模块负责候选文件扫描、artifact 分类与选择策略。

这里不仅决定“选哪些文件”，还负责把输入讨论转换成可解释的选择结果：
包括 retrieval gate、多路径 query、必要性重排，以及轻量依赖提升。
"""

from __future__ import annotations

import ast
import codecs
import re
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any

from .config_paths import (
    HandoffInputs,
    SkillDefaults,
    absolute_from_relative,
    dedupe_strings,
    ensure_within_project_root,
    normalize_pattern,
    to_repo_relative,
)
from .token_tools import TokenCounter


MENTIONED_PATH_PATTERN = re.compile(r"[A-Za-z0-9_./\\-]+\.[A-Za-z0-9_]+")
QUERY_TERM_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")

ARTIFACT_CONTRACT = "contract"
ARTIFACT_WORKFLOW = "workflow"
ARTIFACT_SELECTION_LOGIC = "selection_logic"
ARTIFACT_CODE_SNIPPET = "code_snippet"
ARTIFACT_SUPPORTING_CONTEXT = "supporting_context"
ARTIFACT_ATTACHMENTS_ONLY = "attachments_only"

CONTEXT_LAYER_STABLE_CONTRACT = "stable_contract"
CONTEXT_LAYER_DYNAMIC_TASK = "dynamic_task"
CONTEXT_LAYER_EVIDENCE = "evidence"
CONTEXT_LAYER_ATTACHMENTS = "attachments"

PROTECTED_ARTIFACT_TYPES = {ARTIFACT_CONTRACT}
RETRIEVAL_GATE_BRIEF_ONLY = "brief_only"
RETRIEVAL_GATE_BRIEF_PLUS_CONTRACT = "brief_plus_contract"
RETRIEVAL_GATE_FULL_BUNDLE = "full_bundle"
STRATEGY_VERSION = "context_strategy_v0_3"
ENGLISH_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "into",
    "your",
    "their",
    "have",
    "need",
    "keep",
    "make",
    "mode",
    "topic",
    "goal",
    "focus",
    "task",
    "handoff",
    "package",
    "current",
    "should",
    "would",
    "will",
    "then",
    "when",
    "where",
    "what",
    "which",
}


@dataclass
class SelectedFile:
    """中文说明：主阅读层与附件层之间共享的 artifact 选择结果。"""

    path: str
    absolute_path: Path
    type: str
    status: str
    included_in_bundle: bool
    reason: str
    token_count_original: int
    token_count_included: int
    truncated: bool
    truncation_method: str
    priority: int
    selection_origin: str
    context_layer: str
    artifact_type: str
    excerpt_strategy: str = "not_rendered"
    excerpt_anchor: list[str] = field(default_factory=list)
    compaction_strategy: str = "none"
    selection_reason: str = ""
    fallback_used: bool = False
    dependency_promoted: bool = False
    critical_token_preserved: bool = False
    attachment_path: str = ""
    excerpt: str = ""
    content: str = ""
    preferred_context_layer: str = CONTEXT_LAYER_EVIDENCE
    preferred_artifact_type: str = ARTIFACT_SUPPORTING_CONTEXT

    def to_manifest(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("absolute_path")
        data.pop("excerpt")
        data.pop("content")
        data.pop("selection_origin")
        data.pop("preferred_context_layer")
        data.pop("preferred_artifact_type")
        return data


@dataclass(frozen=True)
class ProjectScan:
    all_text_files: dict[str, Path]
    candidates: dict[str, Path]
    binary_count: int
    excluded_count: int


@dataclass(frozen=True)
class CandidateInfo:
    """中文说明：候选文件的静态信息，用于后续 gate、排序和依赖分析。"""

    path: str
    absolute_path: Path
    content: str
    file_type: str
    artifact_type: str
    context_layer: str
    base_reason: str
    base_priority: int


def file_type_for_path(relative_path: str) -> str:
    suffix = Path(relative_path).suffix.lower()
    parts = PurePosixPath(relative_path).parts
    if suffix in {".md", ".rst", ".txt"}:
        return "documentation"
    if suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".c", ".cc", ".cpp"}:
        return "code"
    if suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}:
        return "config"
    if suffix == ".log" or "log" in {part.lower() for part in parts}:
        return "log"
    return "other"


def is_probably_text(path: Path) -> bool:
    sample = path.read_bytes()[:2048]
    if b"\x00" in sample:
        return False
    try:
        decoder = codecs.getincrementaldecoder("utf-8")()
        decoder.decode(sample, final=False)
    except UnicodeDecodeError:
        return False
    return True


def contains_subpath(parts: tuple[str, ...], target_parts: tuple[str, ...]) -> bool:
    if not target_parts or len(parts) < len(target_parts):
        return False
    target_length = len(target_parts)
    for index in range(len(parts) - target_length + 1):
        if parts[index : index + target_length] == target_parts:
            return True
    return False


def should_exclude(relative_path: str, defaults: SkillDefaults) -> bool:
    parts = PurePosixPath(relative_path).parts
    filename = Path(relative_path).name
    suffix = Path(relative_path).suffix.lower()

    if filename in defaults.excluded_names:
        return True
    if suffix in defaults.excluded_suffixes:
        return True
    for part in parts[:-1]:
        if part in defaults.excluded_dirs:
            return True
    if contains_subpath(parts, (".codex", "handoffs")):
        return True
    for excluded_dir in defaults.excluded_dirs:
        normalized_dir = normalize_pattern(excluded_dir)
        if normalized_dir and (
            relative_path == normalized_dir or relative_path.startswith(normalized_dir + "/")
        ):
            return True
    return False


def scan_text_files(project_root: Path) -> tuple[dict[str, Path], int]:
    text_files: dict[str, Path] = {}
    binary_count = 0
    for path in sorted(project_root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = to_repo_relative(path, project_root)
        if not is_probably_text(path):
            binary_count += 1
            continue
        text_files[relative_path] = path
    return text_files, binary_count


def collect_project_scan(project_root: Path, defaults: SkillDefaults) -> ProjectScan:
    all_text_files, binary_count = scan_text_files(project_root)
    candidates = {
        relative_path: path
        for relative_path, path in all_text_files.items()
        if not should_exclude(relative_path, defaults)
    }
    excluded_count = binary_count + (len(all_text_files) - len(candidates))
    return ProjectScan(
        all_text_files=all_text_files,
        candidates=candidates,
        binary_count=binary_count,
        excluded_count=excluded_count,
    )


def scan_project_files(project_root: Path, defaults: SkillDefaults) -> tuple[dict[str, Path], int]:
    scan = collect_project_scan(project_root, defaults)
    return scan.candidates, scan.excluded_count


def detect_mentioned_paths(texts: list[str], candidates: dict[str, Path]) -> list[str]:
    hits: list[str] = []
    available = set(candidates)
    basenames: dict[str, list[str]] = {}
    for relative_path in candidates:
        basenames.setdefault(Path(relative_path).name, []).append(relative_path)
    for text in texts:
        for token in MENTIONED_PATH_PATTERN.findall(text):
            normalized = normalize_pattern(token)
            if normalized in available and normalized not in hits:
                hits.append(normalized)
                continue
            basename = Path(normalized).name
            for candidate in basenames.get(basename, []):
                if candidate not in hits:
                    hits.append(candidate)
    return hits


def normalize_query_term(term: str) -> str | None:
    cleaned = term.strip().lower().replace("-", "_")
    cleaned = cleaned.strip("_")
    if not cleaned:
        return None
    if cleaned.isascii() and cleaned in ENGLISH_STOP_WORDS:
        return None
    return cleaned


def _collect_query_terms(texts: list[str]) -> set[str]:
    terms: set[str] = set()
    for text in texts:
        normalized_text = normalize_pattern(text)
        for token in QUERY_TERM_PATTERN.findall(normalized_text):
            normalized = normalize_query_term(token)
            if normalized:
                terms.add(normalized)
        path_stem = Path(normalized_text).stem
        normalized_stem = normalize_query_term(path_stem)
        if normalized_stem:
            terms.add(normalized_stem)
    return terms


def derive_query_profile(inputs: HandoffInputs) -> dict[str, set[str]]:
    """中文说明：把任务输入拆成 task / contract / code 三条 query lane。"""

    task_texts = [
        inputs.topic,
        inputs.goal,
        inputs.background,
        *inputs.focus_points,
        *inputs.questions,
        *inputs.known_routes,
        *inputs.blockers,
    ]
    task_query = _collect_query_terms(task_texts)
    contract_query = set(task_query)
    contract_query.update(
        {
            "contract",
            "schema",
            "template",
            "reply",
            "manifest",
            "preview",
            "confirm",
            "status",
            "paths",
            "artifacts",
            "policy",
            "handoff_id",
        }
    )
    code_query = _collect_query_terms(
        [
            *inputs.must_include,
            *inputs.mentioned_paths,
            *inputs.focus_points,
            *inputs.questions,
            "workflow selection token budget excerpt dependency helper snippet code tradeoff",
        ]
    )
    code_query.update(
        {
            "workflow",
            "prepare",
            "preview",
            "confirm",
            "select",
            "selector",
            "token",
            "budget",
            "excerpt",
            "dependency",
            "helper",
            "snippet",
            "code",
            "tradeoff",
        }
    )
    all_terms = set(task_query) | set(contract_query) | set(code_query)
    return {
        "task": task_query,
        "contract": contract_query,
        "code": code_query,
        "all": all_terms,
    }


def derive_query_terms(inputs: HandoffInputs) -> set[str]:
    texts = [
        inputs.topic,
        inputs.goal,
        inputs.background,
        *inputs.focus_points,
        *inputs.questions,
        *inputs.known_routes,
        *inputs.blockers,
        *inputs.mentioned_paths,
        *inputs.must_include,
    ]
    return _collect_query_terms(texts)


def classify_artifact(relative_path: str, file_type: str) -> tuple[str, str, str, int]:
    normalized = relative_path.lower()
    name = Path(relative_path).name.lower()
    parts = [part.lower() for part in PurePosixPath(relative_path).parts]

    if (
        name == "skill.md"
        or name == "openai.yaml"
        or "schemas" in parts
        or "templates" in parts
        or normalized.endswith("config/defaults.yaml")
        or name in {"manifest.schema.json", "final_reply.schema.md"}
    ):
        return (
            ARTIFACT_CONTRACT,
            CONTEXT_LAYER_STABLE_CONTRACT,
            "Contract artifact that defines output shape, prompt framing, or handoff policy.",
            2,
        )

    if name in {"prepare_handoff.py", "render_preview.py", "confirm_handoff.py", "workflow.py"}:
        return (
            ARTIFACT_WORKFLOW,
            CONTEXT_LAYER_EVIDENCE,
            "Workflow artifact that controls handoff creation, preview, or confirmation state.",
            3,
        )

    if name in {"selection.py", "token_tools.py", "selector.py"}:
        return (
            ARTIFACT_SELECTION_LOGIC,
            CONTEXT_LAYER_EVIDENCE,
            "Selection logic artifact that determines ranking, extraction, or budget behavior.",
            4,
        )

    if file_type == "code":
        return (
            ARTIFACT_CODE_SNIPPET,
            CONTEXT_LAYER_EVIDENCE,
            "Code artifact that grounds the current technical discussion.",
            5,
        )

    if file_type in {"documentation", "config", "log", "other"}:
        return (
            ARTIFACT_SUPPORTING_CONTEXT,
            CONTEXT_LAYER_EVIDENCE,
            "Supporting context artifact that helps frame the task without defining the contract.",
            6,
        )

    return (
        ARTIFACT_SUPPORTING_CONTEXT,
        CONTEXT_LAYER_EVIDENCE,
        "Supporting context artifact selected as a minimal reference.",
        6,
    )


def _artifact_base_score(artifact_type: str) -> int:
    return {
        ARTIFACT_CONTRACT: 940,
        ARTIFACT_WORKFLOW: 860,
        ARTIFACT_SELECTION_LOGIC: 800,
        ARTIFACT_CODE_SNIPPET: 720,
        ARTIFACT_SUPPORTING_CONTEXT: 620,
        ARTIFACT_ATTACHMENTS_ONLY: 80,
    }[artifact_type]


def _path_matches_query(relative_path: str, query_terms: set[str]) -> list[str]:
    haystack = normalize_pattern(relative_path).lower()
    hits = [term for term in sorted(query_terms) if term in haystack]
    return hits[:3]


def _query_hits_for_artifact(relative_path: str, artifact_type: str, query_profile: dict[str, set[str]]) -> dict[str, list[str]]:
    task_hits = _path_matches_query(relative_path, query_profile["task"])
    contract_hits = _path_matches_query(relative_path, query_profile["contract"])
    code_hits = _path_matches_query(relative_path, query_profile["code"])
    if artifact_type == ARTIFACT_CONTRACT:
        return {
            "task": task_hits,
            "contract": contract_hits,
            "code": code_hits[:1],
        }
    if artifact_type == ARTIFACT_WORKFLOW:
        return {
            "task": task_hits[:1],
            "contract": contract_hits[:2],
            "code": code_hits,
        }
    if artifact_type in {ARTIFACT_SELECTION_LOGIC, ARTIFACT_CODE_SNIPPET}:
        return {
            "task": task_hits,
            "contract": contract_hits[:1],
            "code": code_hits,
        }
    return {
        "task": task_hits,
        "contract": contract_hits[:1],
        "code": code_hits[:1],
    }


def _contains_focus_text(inputs: HandoffInputs, keywords: tuple[str, ...]) -> bool:
    haystack = " ".join(
        [inputs.topic, inputs.goal, *inputs.focus_points, *inputs.questions, *inputs.known_routes, *inputs.blockers]
    ).lower()
    return any(keyword in haystack for keyword in keywords)


def decide_retrieval_gate(inputs: HandoffInputs, query_profile: dict[str, set[str]]) -> str:
    """中文说明：根据任务范围和关注点决定 brief / contract / full bundle 三档检索门控。"""

    explicit_code_paths = any(Path(normalize_pattern(path)).suffix.lower() == ".py" for path in [*inputs.must_include, *inputs.mentioned_paths])
    code_focus = explicit_code_paths or _contains_focus_text(
        inputs,
        ("workflow", "selection", "selector", "token", "budget", "excerpt", "code", "tradeoff", "dependency", "helper"),
    )
    contract_focus = _contains_focus_text(
        inputs,
        ("contract", "schema", "template", "reply", "manifest", "status", "paths", "artifacts", "policy", "handoff_id"),
    )
    narrow_scope = (
        len(query_profile["task"]) <= 12
        and len(inputs.focus_points) <= 4
        and len(inputs.questions) <= 2
        and len(inputs.must_include) <= 2
    )
    if code_focus or len(inputs.must_include) >= 3 or len(inputs.mentioned_paths) > 1:
        return RETRIEVAL_GATE_FULL_BUNDLE
    if not inputs.must_include and not inputs.mentioned_paths and not contract_focus and len(query_profile["task"]) <= 6:
        return RETRIEVAL_GATE_BRIEF_ONLY
    if contract_focus and narrow_scope:
        return RETRIEVAL_GATE_BRIEF_PLUS_CONTRACT
    return RETRIEVAL_GATE_BRIEF_PLUS_CONTRACT


def _allowed_artifact_types_for_gate(retrieval_gate: str) -> set[str]:
    if retrieval_gate == RETRIEVAL_GATE_BRIEF_ONLY:
        return set()
    if retrieval_gate == RETRIEVAL_GATE_BRIEF_PLUS_CONTRACT:
        return {ARTIFACT_CONTRACT, ARTIFACT_WORKFLOW}
    return {
        ARTIFACT_CONTRACT,
        ARTIFACT_WORKFLOW,
        ARTIFACT_SELECTION_LOGIC,
        ARTIFACT_CODE_SNIPPET,
        ARTIFACT_SUPPORTING_CONTEXT,
    }


def _artifact_query_hits_for_reason(query_hits: dict[str, list[str]]) -> list[str]:
    ordered: list[str] = []
    for lane in ("task", "contract", "code"):
        for hit in query_hits[lane]:
            if hit not in ordered:
                ordered.append(hit)
    return ordered[:4]


def score_candidate(
    relative_path: str,
    file_type: str,
    artifact_type: str,
    mentioned_paths: set[str],
    query_profile: dict[str, set[str]],
    dependency_reason: str = "",
) -> tuple[int, str, int]:
    _ = file_type
    score = _artifact_base_score(artifact_type)
    _, _, base_reason, base_priority = classify_artifact(relative_path, file_type_for_path(relative_path))
    reasons = [base_reason]
    query_hits = _query_hits_for_artifact(relative_path, artifact_type, query_profile)
    display_hits = _artifact_query_hits_for_reason(query_hits)
    if relative_path in mentioned_paths:
        score += 140
        reasons.append("The current discussion explicitly mentions this artifact.")
    if display_hits:
        score += min(150, 30 * len(display_hits))
        reasons.append(f"Path and name align with current task-specific query lanes: {', '.join(display_hits)}.")
    if query_hits["contract"] and artifact_type == ARTIFACT_CONTRACT:
        score += 35
    if query_hits["code"] and artifact_type in {ARTIFACT_WORKFLOW, ARTIFACT_SELECTION_LOGIC, ARTIFACT_CODE_SNIPPET}:
        score += 35
    if query_hits["task"] and artifact_type == ARTIFACT_SUPPORTING_CONTEXT:
        score += 20
    if artifact_type == ARTIFACT_SUPPORTING_CONTEXT and not query_hits["task"]:
        score -= 120
        reasons.append("Only provides broad background and is not currently necessary.")
    if dependency_reason:
        score += 180
        reasons.append(dependency_reason)

    name = Path(relative_path).name
    parts = PurePosixPath(relative_path).parts
    if name in {"README.md", "AGENTS.md"} and artifact_type == ARTIFACT_SUPPORTING_CONTEXT:
        score += 30
        reasons.append("Provides repository-level framing for the discussion.")
    if parts and parts[0] == "docs":
        score += 25
    if artifact_type == ARTIFACT_CONTRACT and any(token in relative_path.lower() for token in ["schema", "template", "reply", "manifest", "preview", "confirm"]):
        score += 40
    if artifact_type == ARTIFACT_WORKFLOW and any(token in relative_path.lower() for token in ["workflow", "prepare", "preview", "confirm"]):
        score += 30
    if artifact_type == ARTIFACT_SELECTION_LOGIC and any(token in relative_path.lower() for token in ["select", "selector", "token", "budget", "excerpt"]):
        score += 30

    return score, " ".join(reasons), base_priority


def _module_name_for_path(relative_path: str) -> str | None:
    path = PurePosixPath(relative_path)
    if path.suffix != ".py":
        return None
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)


def _resolve_import_to_path(module_name: str, module_index: dict[str, str]) -> str | None:
    current = module_name
    while current:
        if current in module_index:
            return module_index[current]
        if "." not in current:
            break
        current = current.rsplit(".", 1)[0]
    return None


def build_dependency_map(catalog: dict[str, CandidateInfo]) -> dict[str, set[str]]:
    """中文说明：为仓库内 Python 候选文件建立轻量静态依赖图。"""

    module_index = {
        module_name: path
        for path in catalog
        if (module_name := _module_name_for_path(path)) is not None
    }
    dependency_map: dict[str, set[str]] = {}
    for path, info in catalog.items():
        if info.file_type != "code" or Path(path).suffix.lower() != ".py":
            continue
        try:
            module = ast.parse(info.content)
        except SyntaxError:
            continue
        dependencies: set[str] = set()
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    resolved = _resolve_import_to_path(alias.name, module_index)
                    if resolved and resolved != path:
                        dependencies.add(resolved)
            elif isinstance(node, ast.ImportFrom):
                base_module = node.module or ""
                for alias in node.names:
                    resolved = _resolve_import_to_path(f"{base_module}.{alias.name}" if base_module else alias.name, module_index)
                    if resolved is None and base_module:
                        resolved = _resolve_import_to_path(base_module, module_index)
                    if resolved and resolved != path:
                        dependencies.add(resolved)
        dependency_map[path] = dependencies
    return dependency_map


def _consumes_contract_keywords(content: str) -> bool:
    lowered = content.lower()
    return any(
        keyword in lowered
        for keyword in ("handoff_id", "reply_template", "manifest", "preview", "confirm", "status", "paths", "artifacts", "schema")
    )


def compute_dependency_promotions(
    preliminary_paths: list[str],
    catalog: dict[str, CandidateInfo],
    dependency_map: dict[str, set[str]],
) -> dict[str, str]:
    """中文说明：计算需要因依赖关系被提升或显式标记的 artifact。

    这里不只标记“原本没入选、后来被救回来的依赖”，也会标记那些本来就靠前，
    但同时满足“是关键 workflow 直接依赖”或“直接消费 contract”的条目，
    这样 manifest 的依赖元数据才更贴近真实因果关系。
    """

    promoted: dict[str, str] = {}
    for path in preliminary_paths:
        info = catalog[path]
        if info.artifact_type == ARTIFACT_WORKFLOW:
            for dependency_path in sorted(dependency_map.get(path, set())):
                if dependency_path == path:
                    continue
                promoted.setdefault(
                    dependency_path,
                    f"Promoted as a direct dependency of workflow artifact {path}.",
                )

    if any(catalog[path].artifact_type == ARTIFACT_CONTRACT for path in preliminary_paths):
        for path, info in catalog.items():
            if info.artifact_type not in {ARTIFACT_WORKFLOW, ARTIFACT_SELECTION_LOGIC, ARTIFACT_CODE_SNIPPET}:
                continue
            if _consumes_contract_keywords(info.content):
                promoted.setdefault(
                    path,
                    "Promoted as a direct consumer of contract artifacts needed to interpret output shape and status.",
                )
    return promoted


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def build_candidate_catalog(paths: dict[str, Path]) -> dict[str, CandidateInfo]:
    """中文说明：把候选路径一次性读取为带类型与基础语义标签的 catalog。"""

    catalog: dict[str, CandidateInfo] = {}
    for relative_path, absolute_path in paths.items():
        content = read_text_file(absolute_path)
        file_type = file_type_for_path(relative_path)
        artifact_type, context_layer, base_reason, base_priority = classify_artifact(relative_path, file_type)
        catalog[relative_path] = CandidateInfo(
            path=relative_path,
            absolute_path=absolute_path,
            content=content,
            file_type=file_type,
            artifact_type=artifact_type,
            context_layer=context_layer,
            base_reason=base_reason,
            base_priority=base_priority,
        )
    return catalog


def resolve_pattern(pattern: str, project_root: Path, candidates: dict[str, Path]) -> list[str]:
    normalized = normalize_pattern(pattern)
    if not normalized:
        return []
    absolute_candidate = Path(normalized)
    if absolute_candidate.is_absolute():
        try:
            normalized = to_repo_relative(ensure_within_project_root(absolute_candidate, project_root, "pattern"), project_root)
        except ValueError:
            return []
    if any(token in normalized for token in ["*", "?", "["]):
        return sorted(relative for relative in candidates if fnmatch(relative, normalized))
    concrete = absolute_from_relative(project_root, normalized)
    if concrete.exists():
        try:
            concrete = ensure_within_project_root(concrete, project_root, "pattern")
        except ValueError:
            return []
        if concrete.is_file():
            try:
                return [to_repo_relative(concrete, project_root)]
            except ValueError:
                return []
        if concrete.is_dir():
            prefix = normalize_pattern(to_repo_relative(concrete, project_root))
            return sorted(
                relative
                for relative in candidates
                if relative == prefix or relative.startswith(prefix + "/")
            )
    return [relative for relative in candidates if relative == normalized]


def select_files(
    project_root: Path,
    inputs: HandoffInputs,
    defaults: SkillDefaults,
    token_counter: TokenCounter,
) -> tuple[list[SelectedFile], dict[str, int | str], list[str]]:
    """中文说明：执行 gate、排序、必要性筛选和依赖提升，产出最终选材结果。"""

    scan = collect_project_scan(project_root, defaults)
    all_text_files = scan.all_text_files
    candidates = scan.candidates
    catalog = build_candidate_catalog(all_text_files)
    candidate_catalog = {path: catalog[path] for path in candidates}
    dependency_map = build_dependency_map(candidate_catalog)
    warnings: list[str] = []
    query_profile = derive_query_profile(inputs)
    query_terms = query_profile["all"]
    retrieval_gate = decide_retrieval_gate(inputs, query_profile)
    allowed_artifact_types = _allowed_artifact_types_for_gate(retrieval_gate)
    mentioned = dedupe_strings(
        inputs.mentioned_paths
        + detect_mentioned_paths(
            [inputs.background, *inputs.focus_points, *inputs.questions, *inputs.known_routes, *inputs.blockers],
            candidates,
        )
    )

    exclude_matches: set[str] = set()
    for pattern in inputs.must_exclude:
        matches = resolve_pattern(pattern, project_root, all_text_files)
        if not matches:
            warnings.append(f"must_exclude 未匹配到任何文件：{pattern}")
        exclude_matches.update(matches)

    selected_paths: list[str] = []
    for pattern in inputs.must_include:
        matches = resolve_pattern(pattern, project_root, all_text_files)
        if not matches:
            warnings.append(f"must_include 未匹配到任何文件：{pattern}")
            continue
        for relative_path in matches:
            if relative_path in exclude_matches:
                warnings.append(f"文件同时命中 must_include 与 must_exclude，已按排除处理：{relative_path}")
                continue
            if relative_path not in selected_paths:
                selected_paths.append(relative_path)

    mentioned_matches: list[str] = []
    for pattern in mentioned:
        matches = resolve_pattern(pattern, project_root, candidates)
        for relative_path in matches:
            if relative_path in exclude_matches or relative_path in selected_paths or relative_path in mentioned_matches:
                continue
            if retrieval_gate != RETRIEVAL_GATE_FULL_BUNDLE and candidate_catalog[relative_path].artifact_type not in allowed_artifact_types:
                continue
            if relative_path not in exclude_matches:
                mentioned_matches.append(relative_path)

    mentioned_set = set(mentioned_matches)
    def rank_candidates(dependency_promotions: dict[str, str]) -> list[tuple[int, str, int, str]]:
        scored_candidates: list[tuple[int, str, int, str]] = []
        for relative_path in candidates:
            if relative_path in exclude_matches or relative_path in selected_paths or relative_path in mentioned_set:
                continue
            info = candidate_catalog[relative_path]
            if relative_path not in dependency_promotions and info.artifact_type not in allowed_artifact_types:
                continue
            score, reason, priority = score_candidate(
                relative_path,
                info.file_type,
                info.artifact_type,
                mentioned_set,
                query_profile,
                dependency_promotions.get(relative_path, ""),
            )
            scored_candidates.append((score, relative_path, priority, reason))
        scored_candidates.sort(key=lambda item: (-item[0], item[2], item[1]))
        return scored_candidates

    remaining_budget = max(inputs.max_files - len(selected_paths), 0)
    preliminary_ranked = rank_candidates({})
    preliminary_mentioned = mentioned_matches[:remaining_budget]
    preliminary_remaining = max(remaining_budget - len(preliminary_mentioned), 0)
    preliminary_auto = [relative_path for _, relative_path, _, _ in preliminary_ranked[:preliminary_remaining]]
    dependency_promotions = compute_dependency_promotions(selected_paths + preliminary_mentioned + preliminary_auto, candidate_catalog, dependency_map)

    scored_candidates = rank_candidates(dependency_promotions)
    chosen_mentioned = mentioned_matches[:remaining_budget]
    remaining_after_mentioned = max(remaining_budget - len(chosen_mentioned), 0)
    auto_paths = [relative_path for _, relative_path, _, _ in scored_candidates[:remaining_after_mentioned]]
    chosen_paths = selected_paths + chosen_mentioned + auto_paths

    selections: list[SelectedFile] = []
    for relative_path in chosen_paths:
        info = catalog[relative_path]
        preferred_artifact_type = info.artifact_type
        preferred_context_layer = info.context_layer
        base_reason = info.base_reason
        base_priority = info.base_priority
        if relative_path in selected_paths:
            reason = f"User explicitly requested this artifact. {base_reason}"
            priority = 1
            selection_origin = "must_include"
        elif relative_path in mentioned_matches:
            reason = f"The current discussion explicitly mentions this artifact. {base_reason}"
            priority = min(base_priority, 2)
            selection_origin = "mentioned"
        else:
            _, reason, priority = score_candidate(
                relative_path,
                info.file_type,
                preferred_artifact_type,
                mentioned_set,
                query_profile,
                dependency_promotions.get(relative_path, ""),
            )
            selection_origin = "auto"
        selections.append(
            SelectedFile(
                path=relative_path,
                absolute_path=info.absolute_path,
                type=info.file_type,
                status="selected",
                included_in_bundle=False,
                reason=reason,
                token_count_original=token_counter.count(info.content),
                token_count_included=0,
                truncated=False,
                truncation_method="not_rendered",
                priority=priority,
                selection_origin=selection_origin,
                context_layer=preferred_context_layer,
                artifact_type=preferred_artifact_type,
                selection_reason=reason,
                dependency_promoted=relative_path in dependency_promotions,
                preferred_context_layer=preferred_context_layer,
                preferred_artifact_type=preferred_artifact_type,
                content=info.content,
            )
        )

    summary = {
        "total_candidate_files": len(candidates),
        "excluded_files": scan.excluded_count + len(exclude_matches.intersection(candidates)),
        "token_count_method": token_counter.method_name,
        "retrieval_gate": retrieval_gate,
    }
    return selections, summary, warnings
