"""中文说明：本模块负责候选文件扫描、artifact 分类与选择策略。

这里不仅决定“选哪些文件”，还负责把输入讨论转换成可解释的选择结果：
包括 retrieval gate、多路径 query、必要性重排，以及轻量依赖提升。
"""

from __future__ import annotations

import ast
import codecs
import heapq
import re
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from itertools import count
from pathlib import Path, PurePosixPath
from typing import Any

from .config_paths import (
    GRAPH_MAX_EXPLANATION_EDGES,
    GRAPH_MAX_EXPLANATION_NODES,
    GRAPH_MAX_TWO_HOP,
    HandoffInputs,
    REPO_GRAPH_VERSION,
    SELECTOR_ENGINE_NAME,
    SELECTOR_ENGINE_VERSION,
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
GRAPH_DIRECT_ANCHOR = "direct_anchor"
GRAPH_EDGE_CONTAINS = "contains"
GRAPH_EDGE_IMPORTS = "imports"
GRAPH_EDGE_CONSTRAINS = "constrains"
GRAPH_EDGE_DEPENDS_ON = "depends_on"
GRAPH_EDGE_CONSUMES = "consumes"
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
    graph_selected: bool = False
    graph_distance: int = -1
    graph_path_types: list[str] = field(default_factory=list)
    explanation_path_ref: str = ""
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


@dataclass(frozen=True)
class TaskState:
    """中文说明：把当前 handoff 输入收敛成轻量任务状态。

    这里不保存长对话历史，只保留图选择器需要的稳定字段，用于生成 query seed
    和控制 2-hop 扩展门控。
    """

    topic: str
    goal: str
    focus_points: tuple[str, ...]
    questions: tuple[str, ...]
    blockers: tuple[str, ...]
    known_routes: tuple[str, ...]
    must_include: tuple[str, ...]
    must_exclude: tuple[str, ...]
    mentioned_paths: tuple[str, ...]
    output_requirements: tuple[str, ...]


@dataclass(frozen=True)
class GraphEdge:
    """中文说明：repo graph 的轻量边定义。

    `cost` 不是 token 成本，而是选择器在路径排序时使用的结构化距离成本。
    """

    target: str
    edge_type: str
    cost: int


@dataclass(frozen=True)
class GraphPath:
    """中文说明：记录从 task seed 到目标节点的最短解释路径。"""

    target_node: str
    path: tuple[str, ...]
    edge_types: tuple[str, ...]
    distance: int
    score_breakdown: dict[str, Any]


@dataclass(frozen=True)
class RepoGraph:
    """中文说明：运行期内存中的轻量 repo graph。

    v1 只保存当前选择器所需的最小结构信息，不做长期持久化，也不输出完整图快照。
    """

    adjacency: dict[str, tuple[GraphEdge, ...]]
    node_to_path: dict[str, str]
    file_nodes: dict[str, str]
    artifact_nodes: dict[str, tuple[str, ...]]
    symbol_nodes: dict[str, tuple[str, ...]]
    node_counts: dict[str, int]
    edge_counts: dict[str, int]


@dataclass(frozen=True)
class GraphSelectionContext:
    """中文说明：图选择阶段的输出结果。

    该结构把图扩展得到的候选、解释路径和摘要统计统一返回给 workflow，
    避免在 workflow 再次推断图选择结果。
    """

    file_paths: dict[str, GraphPath]
    selector_engine: dict[str, Any]
    repo_graph_summary: dict[str, Any]
    explanation_summary: dict[str, Any]


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


def build_task_state(inputs: HandoffInputs) -> TaskState:
    """中文说明：把 handoff 输入收敛为图选择器可消费的轻量任务状态。"""

    return TaskState(
        topic=inputs.topic,
        goal=inputs.goal,
        focus_points=tuple(inputs.focus_points),
        questions=tuple(inputs.questions),
        blockers=tuple(inputs.blockers),
        known_routes=tuple(inputs.known_routes),
        must_include=tuple(inputs.must_include),
        must_exclude=tuple(inputs.must_exclude),
        mentioned_paths=tuple(inputs.mentioned_paths),
        output_requirements=tuple(inputs.output_requirements),
    )


def _dir_node_id(relative_dir: str) -> str:
    return f"dir:{relative_dir}"


def _file_node_id(relative_path: str) -> str:
    return f"file:{relative_path}"


def _artifact_node_id(node_type: str, relative_path: str) -> str:
    return f"{node_type}:{relative_path}"


def _symbol_node_id(relative_path: str, qualname: str) -> str:
    return f"symbol:{relative_path}:{qualname}"


def _is_schema_template_candidate(relative_path: str) -> bool:
    normalized = relative_path.lower()
    parts = [part.lower() for part in PurePosixPath(relative_path).parts]
    name = Path(relative_path).name.lower()
    return (
        "schemas" in parts
        or "templates" in parts
        or name in {"reply_template.md", "manifest.schema.json", "final_reply.schema.md", "openai.yaml"}
        or normalized.endswith("config/defaults.yaml")
    )


def _artifact_node_type(info: CandidateInfo) -> str | None:
    if info.artifact_type == ARTIFACT_CONTRACT:
        if _is_schema_template_candidate(info.path):
            return "artifact_schema_template"
        return "artifact_contract"
    if info.artifact_type == ARTIFACT_WORKFLOW:
        return "artifact_workflow"
    return None


def _iter_parent_dirs(relative_path: str) -> list[str]:
    parts = list(PurePosixPath(relative_path).parts[:-1])
    if not parts:
        return ["."]
    parents = ["."]
    current: list[str] = []
    for part in parts:
        current.append(part)
        parents.append("/".join(current))
    return parents


def _iter_symbol_names(relative_path: str, content: str) -> list[str]:
    """中文说明：提取 Python 文件的顶层符号名，用于轻量 symbol 节点。"""

    if Path(relative_path).suffix.lower() != ".py":
        return []
    try:
        module = ast.parse(content)
    except SyntaxError:
        return []

    symbols: list[str] = []
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
    return symbols


def _graph_terms_for_path(relative_path: str) -> set[str]:
    normalized = relative_path.lower()
    name = Path(relative_path).name.lower()
    stem = Path(relative_path).stem.lower()
    terms = {
        normalized,
        name,
        stem.replace(".", "_"),
        stem.replace(".", ""),
    }
    if "manifest.schema" in normalized:
        terms.update({"manifest", "schema", "status", "paths", "artifacts"})
    if "reply_template" in normalized:
        terms.update({"reply", "reply_template", "template", "handoff_id", "final_reply"})
    if "defaults.yaml" in normalized:
        terms.update({"defaults", "token", "budget", "exclude", "next_actions"})
    if name == "openai.yaml":
        terms.update({"openai", "metadata", "policy", "prompt"})
    if name == "skill.md":
        terms.update({"skill", "handoff", "preview", "confirm"})
    return {term for term in terms if term and len(term) >= 3}


def _content_has_anchor(content: str, terms: set[str]) -> bool:
    lowered = content.lower()
    return any(term in lowered for term in terms)


def build_repo_graph(candidate_catalog: dict[str, CandidateInfo], dependency_map: dict[str, set[str]]) -> RepoGraph:
    """中文说明：基于已过滤候选文件构建运行期轻量 repo graph。

    图层只建立高置信结构边，不重新引入被扫描阶段排除的文件，也不做长期持久化。
    """

    adjacency_lists: dict[str, list[GraphEdge]] = {}
    node_to_path: dict[str, str] = {}
    file_nodes: dict[str, str] = {}
    artifact_nodes: dict[str, list[str]] = {}
    symbol_nodes: dict[str, list[str]] = {}
    node_counts: dict[str, int] = {
        "dir": 0,
        "file": 0,
        "artifact_contract": 0,
        "artifact_workflow": 0,
        "artifact_schema_template": 0,
        "symbol": 0,
        "task_state_anchor": 0,
    }
    edge_counts: dict[str, int] = {
        GRAPH_EDGE_CONTAINS: 0,
        GRAPH_EDGE_IMPORTS: 0,
        GRAPH_EDGE_CONSTRAINS: 0,
        GRAPH_EDGE_DEPENDS_ON: 0,
        GRAPH_EDGE_CONSUMES: 0,
    }
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(node_id: str, node_type: str, owner_path: str) -> None:
        if node_id in adjacency_lists:
            return
        adjacency_lists[node_id] = []
        node_to_path[node_id] = owner_path
        node_counts[node_type] += 1

    def add_undirected_edge(source: str, target: str, edge_type: str, cost: int) -> None:
        if source == target:
            return
        signature = tuple(sorted((source, target))) + (edge_type,)
        if signature in seen_edges:
            return
        seen_edges.add(signature)
        adjacency_lists[source].append(GraphEdge(target=target, edge_type=edge_type, cost=cost))
        adjacency_lists[target].append(GraphEdge(target=source, edge_type=edge_type, cost=cost))
        edge_counts[edge_type] += 1

    for relative_path, info in candidate_catalog.items():
        file_node = _file_node_id(relative_path)
        file_nodes[relative_path] = file_node
        add_node(file_node, "file", relative_path)

        parent_dirs = _iter_parent_dirs(relative_path)
        for index, relative_dir in enumerate(parent_dirs):
            dir_node = _dir_node_id(relative_dir)
            add_node(dir_node, "dir", relative_dir)
            if index > 0:
                parent_node = _dir_node_id(parent_dirs[index - 1])
                add_undirected_edge(parent_node, dir_node, GRAPH_EDGE_CONTAINS, 1)
        leaf_dir_node = _dir_node_id(parent_dirs[-1])
        add_undirected_edge(leaf_dir_node, file_node, GRAPH_EDGE_CONTAINS, 1)

        artifact_node_type = _artifact_node_type(info)
        if artifact_node_type:
            artifact_node = _artifact_node_id(artifact_node_type, relative_path)
            add_node(artifact_node, artifact_node_type, relative_path)
            artifact_nodes.setdefault(relative_path, []).append(artifact_node)
            add_undirected_edge(file_node, artifact_node, GRAPH_EDGE_CONTAINS, 1)

        symbol_names = _iter_symbol_names(relative_path, info.content)
        for symbol_name in symbol_names:
            symbol_node = _symbol_node_id(relative_path, symbol_name)
            add_node(symbol_node, "symbol", relative_path)
            symbol_nodes.setdefault(relative_path, []).append(symbol_node)
            add_undirected_edge(file_node, symbol_node, GRAPH_EDGE_CONTAINS, 1)

    schema_template_nodes = {
        path: nodes[0]
        for path, nodes in artifact_nodes.items()
        if nodes and nodes[0].startswith("artifact_schema_template:")
    }
    contract_nodes = {
        path: nodes[0]
        for path, nodes in artifact_nodes.items()
        if nodes and nodes[0].startswith("artifact_contract:")
    }
    workflow_nodes = {
        path: nodes[0]
        for path, nodes in artifact_nodes.items()
        if nodes and nodes[0].startswith("artifact_workflow:")
    }

    for path, dependency_paths in dependency_map.items():
        if path not in file_nodes:
            continue
        for dependency_path in dependency_paths:
            if dependency_path not in file_nodes:
                continue
            add_undirected_edge(file_nodes[path], file_nodes[dependency_path], GRAPH_EDGE_IMPORTS, 2)

    for path, contract_node in contract_nodes.items():
        content = candidate_catalog[path].content
        for target_path, target_node in schema_template_nodes.items():
            if path == target_path:
                continue
            if _content_has_anchor(content, _graph_terms_for_path(target_path)):
                add_undirected_edge(contract_node, target_node, GRAPH_EDGE_CONSTRAINS, 1)

    for path, workflow_node in workflow_nodes.items():
        content = candidate_catalog[path].content
        for target_path, target_node in {**contract_nodes, **schema_template_nodes}.items():
            if path == target_path:
                continue
            target_terms = _graph_terms_for_path(target_path)
            if _content_has_anchor(content, target_terms) or _consumes_contract_keywords(content):
                add_undirected_edge(workflow_node, target_node, GRAPH_EDGE_CONSUMES, 1)

    for path, info in candidate_catalog.items():
        if info.artifact_type in {ARTIFACT_CONTRACT, ARTIFACT_WORKFLOW}:
            continue
        content = info.content
        for target_path, target_node in schema_template_nodes.items():
            if path == target_path:
                continue
            if _content_has_anchor(content, _graph_terms_for_path(target_path)):
                add_undirected_edge(file_nodes[path], target_node, GRAPH_EDGE_DEPENDS_ON, 1)

    return RepoGraph(
        adjacency={node_id: tuple(edges) for node_id, edges in adjacency_lists.items()},
        node_to_path=node_to_path,
        file_nodes=file_nodes,
        artifact_nodes={path: tuple(nodes) for path, nodes in artifact_nodes.items()},
        symbol_nodes={path: tuple(nodes) for path, nodes in symbol_nodes.items()},
        node_counts=node_counts,
        edge_counts=edge_counts,
    )


def _task_state_text(task_state: TaskState) -> str:
    return " ".join(
        [
            task_state.topic,
            task_state.goal,
            *task_state.focus_points,
            *task_state.questions,
            *task_state.blockers,
            *task_state.known_routes,
            *task_state.output_requirements,
        ]
    )


def build_graph_seeds(
    task_state: TaskState,
    candidate_catalog: dict[str, CandidateInfo],
    repo_graph: RepoGraph,
    query_profile: dict[str, set[str]],
) -> dict[str, str]:
    """中文说明：从 task state 生成稳定 query seed。

    这里优先使用显式路径与高置信锚点，避免图层自己“发明”语义入口。
    """

    seeds: dict[str, str] = {}
    explicit_paths = {normalize_pattern(path) for path in [*task_state.must_include, *task_state.mentioned_paths]}
    for relative_path, file_node in repo_graph.file_nodes.items():
        if relative_path in explicit_paths:
            seeds[file_node] = "direct_path"

    for relative_path, info in candidate_catalog.items():
        file_node = repo_graph.file_nodes.get(relative_path)
        if file_node is None or file_node in seeds:
            continue
        query_hits = _query_hits_for_artifact(relative_path, info.artifact_type, query_profile)
        if info.artifact_type == ARTIFACT_CONTRACT and query_hits["contract"]:
            seeds[file_node] = "contract_anchor"
        elif info.artifact_type == ARTIFACT_WORKFLOW and (query_hits["contract"] or query_hits["code"]):
            seeds[file_node] = "workflow_anchor"
        elif info.artifact_type in {ARTIFACT_SELECTION_LOGIC, ARTIFACT_CODE_SNIPPET} and query_hits["code"]:
            seeds[file_node] = "code_anchor"
        elif info.artifact_type == ARTIFACT_SUPPORTING_CONTEXT and query_hits["task"]:
            seeds[file_node] = "task_anchor"

    task_text = _task_state_text(task_state).lower()
    for relative_path, symbol_node_ids in repo_graph.symbol_nodes.items():
        if not symbol_node_ids:
            continue
        file_node = repo_graph.file_nodes.get(relative_path)
        if file_node is None:
            continue
        for symbol_node in symbol_node_ids:
            symbol_name = symbol_node.rsplit(":", 1)[-1].lower()
            if len(symbol_name) < 3:
                continue
            if re.search(rf"\b{re.escape(symbol_name)}\b", task_text):
                seeds.setdefault(symbol_node, "symbol_anchor")
                break

    return seeds


def _semantic_hop_increment(edge_type: str) -> int:
    if edge_type == GRAPH_EDGE_CONTAINS:
        return 0
    return 1


def _edge_priority(edge_type: str) -> int:
    if edge_type == GRAPH_EDGE_CONSTRAINS:
        return 0
    if edge_type == GRAPH_EDGE_CONSUMES:
        return 1
    if edge_type == GRAPH_EDGE_DEPENDS_ON:
        return 2
    if edge_type == GRAPH_EDGE_IMPORTS:
        return 3
    return 4


def _path_cost_from_edge_types(edge_types: tuple[str, ...]) -> int:
    semantic_edges = [edge_type for edge_type in edge_types if edge_type != GRAPH_EDGE_CONTAINS]
    if not semantic_edges:
        return 0
    if len(semantic_edges) == 1:
        return 2 if semantic_edges[0] == GRAPH_EDGE_IMPORTS else 1
    if all(edge_type != GRAPH_EDGE_IMPORTS for edge_type in semantic_edges):
        return 3
    return 4


def _path_types_for_graph_path(graph_path: GraphPath | None) -> list[str]:
    if graph_path is None:
        return []
    semantic_types: list[str] = []
    for edge_type in graph_path.edge_types:
        if edge_type == GRAPH_EDGE_CONTAINS:
            continue
        if edge_type not in semantic_types:
            semantic_types.append(edge_type)
    return semantic_types or [GRAPH_DIRECT_ANCHOR]


def _needs_cross_file_expansion(task_state: TaskState) -> bool:
    haystack = _task_state_text(task_state).lower()
    keywords = (
        "跨文件",
        "依赖",
        "import",
        "imports",
        "workflow",
        "selector",
        "code",
        "snippet",
        "graph",
        "topology",
        "topological",
        "cross-file",
        "dependency",
    )
    return any(keyword in haystack for keyword in keywords)


def _score_breakdown_for_path(seed_reason: str, graph_path: GraphPath, path_types: list[str]) -> dict[str, Any]:
    seed_bonus = {
        "direct_path": 160,
        "contract_anchor": 140,
        "workflow_anchor": 130,
        "code_anchor": 110,
        "symbol_anchor": 100,
        "task_anchor": 80,
    }.get(seed_reason, 60)
    path_bonus = 0
    if GRAPH_EDGE_CONSTRAINS in path_types:
        path_bonus += 55
    if GRAPH_EDGE_CONSUMES in path_types:
        path_bonus += 50
    if GRAPH_EDGE_DEPENDS_ON in path_types:
        path_bonus += 35
    if GRAPH_EDGE_IMPORTS in path_types:
        path_bonus += 20
    return {
        "seed_bonus": seed_bonus,
        "path_bonus": path_bonus,
        "path_cost": _path_cost_from_edge_types(graph_path.edge_types),
        "semantic_hops": graph_path.distance,
    }


def _choose_best_graph_path(current: GraphPath | None, candidate: GraphPath) -> GraphPath:
    if current is None:
        return candidate
    current_cost = int(current.score_breakdown.get("path_cost", 999))
    candidate_cost = int(candidate.score_breakdown.get("path_cost", 999))
    if candidate_cost != current_cost:
        return candidate if candidate_cost < current_cost else current
    if candidate.distance != current.distance:
        return candidate if candidate.distance < current.distance else current
    if len(candidate.path) != len(current.path):
        return candidate if len(candidate.path) < len(current.path) else current
    return candidate if candidate.target_node < current.target_node else current


def _search_graph_paths(
    repo_graph: RepoGraph,
    seed_nodes: dict[str, str],
    semantic_hop_limit: int,
) -> dict[str, GraphPath]:
    """中文说明：在轻量 repo graph 上搜索最短解释路径。

    `contains` 边只用于在 file / artifact / symbol 之间穿梭，不计入语义 hop。
    这样既能表达结构关系，又不会把 file->artifact 的内部映射错误当作跨文件扩展。
    """

    best_paths: dict[str, GraphPath] = {}
    visited: dict[tuple[str, int], int] = {}
    queue: list[tuple[int, int, int, str, tuple[str, ...], tuple[str, ...], str]] = []
    order = count()

    for node_id, seed_reason in sorted(seed_nodes.items()):
        initial_path = (f"task_anchor:{seed_reason}", node_id)
        heapq.heappush(queue, (0, 0, next(order), node_id, initial_path, tuple(), seed_reason))

    while queue:
        path_cost, semantic_hops, _, node_id, path_nodes, edge_types, seed_reason = heapq.heappop(queue)
        state_key = (node_id, semantic_hops)
        previous_cost = visited.get(state_key)
        if previous_cost is not None and previous_cost <= path_cost:
            continue
        visited[state_key] = path_cost

        owner_path = repo_graph.node_to_path.get(node_id)
        if owner_path and owner_path in repo_graph.file_nodes:
            graph_path = GraphPath(
                target_node=node_id,
                path=path_nodes,
                edge_types=edge_types,
                distance=semantic_hops,
                score_breakdown={},
            )
            path_types = _path_types_for_graph_path(graph_path)
            graph_path = GraphPath(
                target_node=node_id,
                path=path_nodes,
                edge_types=edge_types,
                distance=semantic_hops,
                score_breakdown=_score_breakdown_for_path(seed_reason, graph_path, path_types),
            )
            best_paths[owner_path] = _choose_best_graph_path(best_paths.get(owner_path), graph_path)

        for edge in repo_graph.adjacency.get(node_id, ()):
            next_hops = semantic_hops + _semantic_hop_increment(edge.edge_type)
            if next_hops > semantic_hop_limit:
                continue
            next_edge_types = edge_types + (edge.edge_type,)
            next_cost = _path_cost_from_edge_types(next_edge_types)
            heapq.heappush(
                queue,
                (
                    next_cost,
                    next_hops,
                    next(order),
                    edge.target,
                    path_nodes + (edge.target,),
                    next_edge_types,
                    seed_reason,
                ),
            )

    return best_paths


def _candidate_graph_flags(info: CandidateInfo, graph_path: GraphPath | None) -> tuple[bool, bool]:
    if graph_path is None:
        return False, False
    path_types = _path_types_for_graph_path(graph_path)
    is_contract_neighbor = any(path_type in {GRAPH_EDGE_CONSTRAINS, GRAPH_EDGE_CONSUMES} for path_type in path_types)
    is_workflow_neighbor = any(path_type in {GRAPH_EDGE_CONSUMES, GRAPH_EDGE_DEPENDS_ON, GRAPH_EDGE_IMPORTS} for path_type in path_types)
    if info.artifact_type == ARTIFACT_CONTRACT and GRAPH_DIRECT_ANCHOR in path_types:
        is_contract_neighbor = True
    if info.artifact_type == ARTIFACT_WORKFLOW and GRAPH_DIRECT_ANCHOR in path_types:
        is_workflow_neighbor = True
    return is_contract_neighbor, is_workflow_neighbor


def _graph_score_bonus(info: CandidateInfo, graph_path: GraphPath | None) -> tuple[int, str]:
    if graph_path is None:
        return 0, ""

    path_types = _path_types_for_graph_path(graph_path)
    path_cost = int(graph_path.score_breakdown.get("path_cost", 0))
    if path_types == [GRAPH_DIRECT_ANCHOR]:
        if info.artifact_type == ARTIFACT_CONTRACT:
            return 70, "Graph seeds confirm this contract as a direct task anchor."
        if info.artifact_type == ARTIFACT_WORKFLOW:
            return 55, "Graph seeds confirm this workflow as a direct task anchor."
        return 30, "Graph seeds align this artifact with the current task state."

    bonus = 0
    if GRAPH_EDGE_CONSTRAINS in path_types:
        bonus += 110 if info.artifact_type == ARTIFACT_CONTRACT else 80
    if GRAPH_EDGE_CONSUMES in path_types:
        bonus += 95 if info.artifact_type in {ARTIFACT_WORKFLOW, ARTIFACT_SELECTION_LOGIC} else 70
    if GRAPH_EDGE_DEPENDS_ON in path_types:
        bonus += 70 if info.artifact_type in {ARTIFACT_SELECTION_LOGIC, ARTIFACT_CODE_SNIPPET, ARTIFACT_WORKFLOW} else 35
    if GRAPH_EDGE_IMPORTS in path_types:
        bonus += 45 if info.artifact_type in {ARTIFACT_SELECTION_LOGIC, ARTIFACT_CODE_SNIPPET, ARTIFACT_WORKFLOW} else 10

    if info.artifact_type == ARTIFACT_SUPPORTING_CONTEXT:
        bonus = min(bonus, 45)
    elif info.artifact_type == ARTIFACT_CONTRACT:
        bonus += 25
    elif info.artifact_type == ARTIFACT_WORKFLOW:
        bonus += 20

    reason = (
        "Graph-assisted expansion linked this artifact through "
        f"{', '.join(path_types)} with path_cost={path_cost}."
    )
    return bonus, reason


def build_graph_selection_context(
    task_state: TaskState,
    candidate_catalog: dict[str, CandidateInfo],
    dependency_map: dict[str, set[str]],
    query_profile: dict[str, set[str]],
    retrieval_gate: str,
) -> GraphSelectionContext:
    """中文说明：构建 graph-assisted 选择上下文。

    v1 只维护运行期内存图，并把图层输出限制为：
    1. 候选增强特征
    2. 最短解释路径
    3. 用于 manifest/notes 的摘要统计
    """

    repo_graph = build_repo_graph(candidate_catalog, dependency_map)
    seed_nodes = build_graph_seeds(task_state, candidate_catalog, repo_graph, query_profile)
    one_hop_paths = _search_graph_paths(repo_graph, seed_nodes, semantic_hop_limit=1)

    one_hop_contract_workflow = sum(
        1
        for relative_path, graph_path in one_hop_paths.items()
        if graph_path.distance > 0
        and candidate_catalog[relative_path].artifact_type in {ARTIFACT_CONTRACT, ARTIFACT_WORKFLOW}
    )
    two_hop_enabled = GRAPH_MAX_TWO_HOP >= 2
    should_trigger_two_hop = two_hop_enabled and (
        _needs_cross_file_expansion(task_state) or one_hop_contract_workflow < 2
    )
    file_paths = one_hop_paths
    two_hop_triggered = False
    if should_trigger_two_hop:
        two_hop_paths = _search_graph_paths(repo_graph, seed_nodes, semantic_hop_limit=min(2, GRAPH_MAX_TWO_HOP))
        if set(two_hop_paths) != set(one_hop_paths):
            two_hop_triggered = True
        file_paths = two_hop_paths

    explanation_entries: list[dict[str, Any]] = []
    for relative_path in sorted(file_paths):
        graph_path = file_paths[relative_path]
        explanation_entries.append(
            {
                "artifact_path": relative_path,
                "target_node": graph_path.target_node,
                "path": list(graph_path.path[:GRAPH_MAX_EXPLANATION_NODES]),
                "edge_types": list(graph_path.edge_types[:GRAPH_MAX_EXPLANATION_EDGES]),
                "score_breakdown": graph_path.score_breakdown,
            }
        )

    repo_graph_node_counts = dict(repo_graph.node_counts)
    repo_graph_node_counts["task_state_anchor"] = len(seed_nodes)

    return GraphSelectionContext(
        file_paths=file_paths,
        selector_engine={
            "name": SELECTOR_ENGINE_NAME,
            "version": SELECTOR_ENGINE_VERSION,
            "graph_assisted": True,
        },
        repo_graph_summary={
            "graph_version": REPO_GRAPH_VERSION,
            "node_counts": repo_graph_node_counts,
            "edge_counts": repo_graph.edge_counts,
            "two_hop_enabled": two_hop_enabled,
            "two_hop_triggered": two_hop_triggered,
        },
        explanation_summary={
            "per_artifact_paths": explanation_entries,
            "dropped_candidates": [],
        },
    )


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
) -> tuple[list[SelectedFile], dict[str, Any], list[str], GraphSelectionContext]:
    """中文说明：执行 gate、排序、必要性筛选和依赖提升，产出最终选材结果。"""

    scan = collect_project_scan(project_root, defaults)
    all_text_files = scan.all_text_files
    candidates = scan.candidates
    catalog = build_candidate_catalog(all_text_files)
    candidate_catalog = {path: catalog[path] for path in candidates}
    dependency_map = build_dependency_map(candidate_catalog)
    warnings: list[str] = []
    query_profile = derive_query_profile(inputs)
    task_state = build_task_state(inputs)
    query_terms = query_profile["all"]
    retrieval_gate = decide_retrieval_gate(inputs, query_profile)
    allowed_artifact_types = _allowed_artifact_types_for_gate(retrieval_gate)
    graph_context = build_graph_selection_context(
        task_state,
        candidate_catalog,
        dependency_map,
        query_profile,
        retrieval_gate,
    )
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
            graph_path = graph_context.file_paths.get(relative_path)
            graph_bonus, graph_reason = _graph_score_bonus(info, graph_path)
            score += graph_bonus
            if graph_reason:
                reason = f"{reason} {graph_reason}"
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

    dropped_candidates: list[dict[str, Any]] = []
    chosen_set = set(chosen_paths)
    for _, relative_path, _, reason in scored_candidates[remaining_after_mentioned:]:
        graph_path = graph_context.file_paths.get(relative_path)
        if graph_path is None:
            continue
        dropped_candidates.append(
            {
                "artifact_path": relative_path,
                "reason": "budget_or_lower_score",
                "graph_distance": graph_path.distance,
                "path_types": _path_types_for_graph_path(graph_path),
                "selection_reason": reason,
            }
        )
        if len(dropped_candidates) >= 8:
            break
    graph_context = GraphSelectionContext(
        file_paths=graph_context.file_paths,
        selector_engine=graph_context.selector_engine,
        repo_graph_summary=graph_context.repo_graph_summary,
        explanation_summary={
            "per_artifact_paths": [
                entry
                for entry in graph_context.explanation_summary["per_artifact_paths"]
                if entry["artifact_path"] in chosen_set
            ],
            "dropped_candidates": dropped_candidates,
        },
    )

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
            graph_bonus, graph_reason = _graph_score_bonus(info, graph_context.file_paths.get(relative_path))
            if graph_reason:
                reason = f"{reason} {graph_reason}"
            selection_origin = "auto"
        graph_path = graph_context.file_paths.get(relative_path)
        path_types = _path_types_for_graph_path(graph_path)
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
                graph_selected=bool(graph_path and graph_path.distance > 0),
                graph_distance=graph_path.distance if graph_path else -1,
                graph_path_types=path_types,
                explanation_path_ref=relative_path if graph_path else "",
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
    return selections, summary, warnings, graph_context
