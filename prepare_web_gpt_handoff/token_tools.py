"""中文说明：本模块负责 token 计数、结构化摘录与压缩回退策略。

这里的实现要同时服务 preview、manifest 审计和 bundle 生成，因此要保证
“真正保留下来的片段锚点”与写回 metadata 的锚点保持一致，避免主阅读层
看见的内容和机器统计信息发生漂移。
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

from codex_skills_shared.token_runtime import (
    DEFAULT_TIKTOKEN as _DEFAULT_TIKTOKEN,
    ExactTokenUnavailableError,
    TokenCounter,
    TokenRuntime,
    build_token_counter as _build_shared_token_counter,
    build_token_runtime as _build_shared_token_runtime,
)


_TIKTOKEN = _DEFAULT_TIKTOKEN


ELLIPSIS = "..."
TRUNCATION_SEPARATOR = "\n\n...[truncated for bundle preview]...\n\n"
SEGMENT_SEPARATOR = "\n\n"
CRITICAL_TOKEN_HEADER = "Critical contract tokens:"

WORKFLOW_KEYWORDS = ("prepare", "render", "confirm", "preview", "bundle", "manifest", "handoff", "resolve", "validate", "entry")
SELECTION_KEYWORDS = ("select", "selector", "scan", "score", "rank", "excerpt", "budget", "token", "compact", "context")
CONTRACT_KEYWORDS = ("schema", "template", "reply", "manifest", "preview", "confirm", "output", "contract", "status", "path")
SUPPORTING_KEYWORDS = ("problem", "goal", "question", "research", "overview", "readme", "agent")
TOP_LEVEL_CONFIG_KEYS = {"required", "properties", "status", "paths", "selection_summary", "inputs", "notes", "policy", "interface"}
REPLY_TEMPLATE_FRONT_MATTER_KEYS = (
    "schema_version",
    "handoff_id",
    "topic",
    "mode",
    "source_provider",
    "source_channel",
    "generated_at",
    "generated_from",
    "reply_template_version",
    "language",
    "contains_external_sources",
    "status",
)
REPLY_TEMPLATE_REQUIRED_HEADINGS = (
    "## 问题定义",
    "## 最终结论",
    "## 推荐路线",
    "## 备选路线",
    "## 关键依据",
    "## 风险与反例",
    "## 候选论文/资料",
    "## 建议下一步",
    "## 仍未解决的问题",
)
MAX_FUNCTION_LINES = 28
MAX_CLASS_LINES = 40
MAX_STATEMENT_CHUNK_LINES = 16


@dataclass(frozen=True)
class StructuredSegment:
    anchor: str
    text: str
    summary: str
    priority: int
    snippet: str


@dataclass(frozen=True)
class ExcerptResult:
    text: str
    truncated: bool
    truncation_method: str
    excerpt_strategy: str
    excerpt_anchor: list[str]
    compaction_strategy: str
    fallback_used: bool
    critical_token_preserved: bool


def build_token_runtime(defaults: object, require_exact_tokens: bool = False) -> TokenRuntime:
    """中文说明：保持现有 patch seam，不改变上层对本模块的依赖方式。"""

    return _build_shared_token_runtime(
        defaults,
        require_exact_tokens=require_exact_tokens,
        tiktoken_module=_TIKTOKEN,
    )


def build_token_counter(defaults: object, require_exact_tokens: bool = False) -> TokenCounter:
    """中文说明：保持现有 patch seam，不改变上层对本模块的依赖方式。"""

    return _build_shared_token_counter(
        defaults,
        require_exact_tokens=require_exact_tokens,
        tiktoken_module=_TIKTOKEN,
    )


def fit_head_with_suffix(text: str, limit_tokens: int, token_counter: TokenCounter, suffix: str) -> str:
    if token_counter.count(text) <= limit_tokens:
        return text
    suffix_tokens = token_counter.count(suffix)
    if suffix_tokens >= limit_tokens:
        return token_counter.slice_head(suffix, limit_tokens)
    head = token_counter.slice_head(text, limit_tokens - suffix_tokens).rstrip()
    result = head + suffix
    while token_counter.count(result) > limit_tokens and head:
        head = token_counter.slice_head(head, max(token_counter.count(head) - 1, 0)).rstrip()
        result = head + suffix
    return result


def build_excerpt(text: str, limit_tokens: int, token_counter: TokenCounter) -> tuple[str, bool, str]:
    normalized = text.strip()
    if not normalized:
        return "", False, "empty_text"
    original_tokens = token_counter.count(normalized)
    if original_tokens <= limit_tokens:
        return normalized, False, "full_text"

    separator_tokens = token_counter.count(TRUNCATION_SEPARATOR)
    available = max(limit_tokens - separator_tokens, 2)
    head_tokens = max(1, int(available * 0.7))
    tail_tokens = max(1, available - head_tokens)

    while True:
        head_text = token_counter.slice_head(normalized, head_tokens).rstrip()
        tail_text = token_counter.slice_tail(normalized, tail_tokens).lstrip()
        excerpt = head_text + TRUNCATION_SEPARATOR + tail_text
        excerpt_tokens = token_counter.count(excerpt)
        if excerpt_tokens <= limit_tokens:
            return excerpt, True, f"head_tail_tokens:{token_counter.count(head_text)}+{token_counter.count(tail_text)}"
        if head_tokens <= 1 and tail_tokens <= 1:
            head_only = fit_head_with_suffix(normalized, limit_tokens, token_counter, "\n...[truncated]")
            return head_only, True, f"head_tokens:{token_counter.count(head_only)}"
        if head_tokens >= tail_tokens and head_tokens > 1:
            head_tokens -= 1
        elif tail_tokens > 1:
            tail_tokens -= 1


def fit_text_to_token_limit(text: str, limit_tokens: int, token_counter: TokenCounter) -> str:
    cleaned = " ".join(text.split())
    if token_counter.count(cleaned) <= limit_tokens:
        return cleaned
    return fit_head_with_suffix(cleaned, limit_tokens, token_counter, ELLIPSIS)


def _artifact_focus_keywords(artifact_type: str) -> tuple[str, ...]:
    if artifact_type == "workflow":
        return WORKFLOW_KEYWORDS
    if artifact_type == "selection_logic":
        return SELECTION_KEYWORDS
    if artifact_type == "contract":
        return CONTRACT_KEYWORDS
    return SUPPORTING_KEYWORDS


def _score_anchor(anchor: str, artifact_type: str, query_terms: set[str], body_hint: str = "") -> int:
    haystack = f"{anchor} {body_hint}".lower().replace("-", "_")
    score = 40
    for term in query_terms:
        if term in haystack:
            score += 30
    for keyword in _artifact_focus_keywords(artifact_type):
        if keyword in haystack:
            score += 35
    return score


def _first_sentence(text: str, max_length: int = 160) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return "Relevant excerpt."
    match = re.match(r"(.{1,%d}?[\.\!\?。；;])" % max_length, cleaned)
    if match:
        return match.group(1).strip()
    return cleaned[:max_length].rstrip() + (ELLIPSIS if len(cleaned) > max_length else "")


def _extract_python_segments(text: str, artifact_type: str, query_terms: set[str]) -> list[StructuredSegment]:
    try:
        module = ast.parse(text)
    except SyntaxError:
        return []

    lines = text.splitlines()
    segments: list[StructuredSegment] = []
    top_level_names = {
        node.name
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }

    def block_for_node(node: ast.AST) -> str:
        start = max(getattr(node, "lineno", 1) - 1, 0)
        end = max(getattr(node, "end_lineno", getattr(node, "lineno", 1)), getattr(node, "lineno", 1))
        return "\n".join(lines[start:end]).strip()

    def line_span(node: ast.AST) -> int:
        return max(getattr(node, "end_lineno", getattr(node, "lineno", 1)) - getattr(node, "lineno", 1) + 1, 1)

    def make_segment(anchor: str, block_text: str, doc_hint: str, snippet: str, priority_hint: str) -> StructuredSegment:
        summary = f"{anchor}: {_first_sentence(doc_hint or block_text, 120)}"
        return StructuredSegment(
            anchor=anchor,
            text=block_text,
            summary=summary,
            priority=_score_anchor(priority_hint, artifact_type, query_terms, doc_hint or block_text[:160]),
            snippet=snippet,
        )

    def chunk_statements(anchor_prefix: str, body: list[ast.stmt]) -> list[StructuredSegment]:
        chunks: list[StructuredSegment] = []
        current_nodes: list[ast.stmt] = []
        current_start: int | None = None
        current_end: int | None = None
        chunk_index = 1
        for statement in body:
            if isinstance(statement, ast.Expr) and isinstance(getattr(statement, "value", None), ast.Constant) and isinstance(statement.value.value, str):
                continue
            statement_start = getattr(statement, "lineno", None)
            statement_end = getattr(statement, "end_lineno", statement_start)
            if statement_start is None or statement_end is None:
                continue
            projected_end = statement_end if current_end is None else statement_end
            projected_start = statement_start if current_start is None else current_start
            projected_span = projected_end - projected_start + 1
            if current_nodes and projected_span > MAX_STATEMENT_CHUNK_LINES:
                block_text = "\n".join(lines[current_start - 1 : current_end]).strip()
                if block_text:
                    chunks.append(
                        make_segment(
                            f"{anchor_prefix}::chunk_{chunk_index}",
                            block_text,
                            block_text,
                            lines[current_start - 1].strip(),
                            anchor_prefix,
                        )
                    )
                    chunk_index += 1
                current_nodes = []
                current_start = None
                current_end = None
            current_nodes.append(statement)
            current_start = statement_start if current_start is None else current_start
            current_end = statement_end
        if current_nodes and current_start is not None and current_end is not None:
            block_text = "\n".join(lines[current_start - 1 : current_end]).strip()
            if block_text:
                chunks.append(
                    make_segment(
                        f"{anchor_prefix}::chunk_{chunk_index}",
                        block_text,
                        block_text,
                        lines[current_start - 1].strip(),
                        anchor_prefix,
                    )
                )
        return chunks

    import_end = 0
    for node in module.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_end = max(import_end, getattr(node, "end_lineno", node.lineno))
        else:
            break
    if import_end:
        import_block = "\n".join(lines[:import_end]).strip()
        if import_block:
            segments.append(
                StructuredSegment(
                    anchor="<imports>",
                    text=import_block,
                    summary="Import block showing the module dependencies and entrypoint surface.",
                    priority=_score_anchor("imports", artifact_type, query_terms),
                    snippet=lines[0].strip(),
                )
            )

    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        name = node.name
        block_text = block_for_node(node)
        if not block_text:
            continue
        start_index = max(node.lineno - 1, 0)
        docstring = ast.get_docstring(node) or lines[start_index].strip()
        call_targets: list[str] = []
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            called_name = None
            if isinstance(child.func, ast.Name):
                called_name = child.func.id
            elif isinstance(child.func, ast.Attribute):
                called_name = child.func.attr
            if called_name and called_name in top_level_names and called_name not in call_targets:
                call_targets.append(called_name)
        summary_hint = docstring
        if call_targets:
            summary_hint += f" Calls: {', '.join(call_targets[:4])}."

        if isinstance(node, ast.ClassDef):
            if line_span(node) <= MAX_CLASS_LINES:
                segments.append(make_segment(name, block_text, summary_hint, lines[start_index].strip(), name))
            else:
                header_text = "\n".join(lines[start_index : min(start_index + 4, len(lines))]).strip()
                segments.append(make_segment(name, header_text, summary_hint, lines[start_index].strip(), name))
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                method_anchor = f"{name}.{child.name}"
                method_text = block_for_node(child)
                if not method_text:
                    continue
                method_doc = ast.get_docstring(child) or lines[max(child.lineno - 1, 0)].strip()
                if line_span(child) <= MAX_FUNCTION_LINES:
                    segments.append(
                        make_segment(
                            method_anchor,
                            method_text,
                            method_doc,
                            lines[max(child.lineno - 1, 0)].strip(),
                            method_anchor,
                        )
                    )
                else:
                    header_text = "\n".join(lines[max(child.lineno - 1, 0) : min(getattr(child, "lineno", 1) + 2, len(lines))]).strip()
                    segments.append(
                        make_segment(
                            method_anchor,
                            header_text,
                            method_doc,
                            lines[max(child.lineno - 1, 0)].strip(),
                            method_anchor,
                        )
                    )
                    segments.extend(chunk_statements(method_anchor, child.body))
            continue

        if line_span(node) <= MAX_FUNCTION_LINES:
            segments.append(make_segment(name, block_text, summary_hint, lines[start_index].strip(), name))
        else:
            header_text = "\n".join(lines[start_index : min(start_index + 4, len(lines))]).strip()
            segments.append(make_segment(name, header_text, summary_hint, lines[start_index].strip(), name))
            segments.extend(chunk_statements(name, node.body))

    return segments


def _extract_markdown_segments(text: str, artifact_type: str, query_terms: set[str]) -> list[StructuredSegment]:
    lines = text.splitlines()
    heading_pattern = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
    sections: list[tuple[str, int, int]] = []
    current_title: str | None = None
    current_start = 0

    for index, line in enumerate(lines):
        match = heading_pattern.match(line)
        if not match:
            continue
        title = match.group(2).strip()
        if current_title is not None:
            sections.append((current_title, current_start, index))
        current_title = title
        current_start = index

    if current_title is not None:
        sections.append((current_title, current_start, len(lines)))

    if not sections:
        cleaned = text.strip()
        if not cleaned:
            return []
        return [
            StructuredSegment(
                anchor="document",
                text=cleaned,
                summary=_first_sentence(cleaned),
                priority=_score_anchor("document", artifact_type, query_terms, cleaned[:160]),
                snippet=cleaned.splitlines()[0].strip(),
            )
        ]

    segments: list[StructuredSegment] = []
    for title, start, end in sections:
        block_text = "\n".join(lines[start:end]).strip()
        body = "\n".join(lines[start + 1 : end]).strip()
        summary = f"{title}: {_first_sentence(body or title)}"
        segments.append(
            StructuredSegment(
                anchor=title,
                text=block_text,
                summary=summary,
                priority=_score_anchor(title, artifact_type, query_terms, body[:160]),
                snippet=lines[start].strip(),
            )
        )
    return segments


def _extract_yaml_segments(text: str, artifact_type: str, query_terms: set[str]) -> list[StructuredSegment]:
    lines = text.splitlines()
    segments: list[StructuredSegment] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or line.startswith((" ", "\t")) or ":" not in stripped:
            index += 1
            continue
        key = stripped.split(":", 1)[0].strip().strip("'\"")
        start = index
        index += 1
        while index < len(lines):
            next_line = lines[index]
            if next_line.strip() and not next_line.startswith((" ", "\t")) and ":" in next_line:
                break
            index += 1
        block_text = "\n".join(lines[start:index]).strip()
        summary = f"{key}: {_first_sentence(block_text)}"
        priority = _score_anchor(key, artifact_type, query_terms, block_text[:160])
        if key in TOP_LEVEL_CONFIG_KEYS:
            priority += 35
        segments.append(
            StructuredSegment(
                anchor=key,
                text=block_text,
                summary=summary,
                priority=priority,
                snippet=lines[start].strip(),
            )
        )
    return segments


def _extract_toml_segments(text: str, artifact_type: str, query_terms: set[str]) -> list[StructuredSegment]:
    lines = text.splitlines()
    segments: list[StructuredSegment] = []
    current_anchor = "<root>"
    start = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if index > start:
                block_text = "\n".join(lines[start:index]).strip()
                if block_text:
                    segments.append(
                        StructuredSegment(
                            anchor=current_anchor,
                            text=block_text,
                            summary=f"{current_anchor}: {_first_sentence(block_text)}",
                            priority=_score_anchor(current_anchor, artifact_type, query_terms, block_text[:160]),
                            snippet=block_text.splitlines()[0].strip(),
                        )
                    )
            current_anchor = stripped.strip("[]")
            start = index
    block_text = "\n".join(lines[start:]).strip()
    if block_text:
        segments.append(
            StructuredSegment(
                anchor=current_anchor,
                text=block_text,
                summary=f"{current_anchor}: {_first_sentence(block_text)}",
                priority=_score_anchor(current_anchor, artifact_type, query_terms, block_text[:160]),
                snippet=block_text.splitlines()[0].strip(),
            )
        )
    return segments


def _build_nested_json_fragment(path_parts: tuple[str, ...], value: object) -> object:
    fragment: object = value
    for key in reversed(path_parts):
        fragment = {key: fragment}
    return fragment


def _extract_json_segments(text: str, artifact_type: str, query_terms: set[str]) -> list[StructuredSegment]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []

    segments: list[StructuredSegment] = []

    def visit(value: object, path_parts: tuple[str, ...]) -> None:
        if not isinstance(value, dict):
            return
        for key, child in value.items():
            current_path = path_parts + (key,)
            anchor = ".".join(current_path)
            fragment = _build_nested_json_fragment(current_path, child)
            block_text = json.dumps(fragment, ensure_ascii=False, indent=2)
            summary = f"{anchor}: {_first_sentence(block_text)}"
            priority = _score_anchor(anchor, artifact_type, query_terms, block_text[:160])
            if key in TOP_LEVEL_CONFIG_KEYS:
                priority += 35
            segments.append(
                StructuredSegment(
                    anchor=anchor,
                    text=block_text,
                    summary=summary,
                    priority=priority,
                    snippet=json.dumps({key: child}, ensure_ascii=False)[:160],
                )
            )
            if len(current_path) < 2 or key in {"properties", "paths", "selection_summary", "inputs", "notes"}:
                visit(child, current_path)

    visit(payload, ())
    return segments


def _extract_segments(path: str, text: str, artifact_type: str, query_terms: set[str]) -> tuple[str, list[StructuredSegment]]:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return "symbol_extract", _extract_python_segments(text, artifact_type, query_terms)
    if suffix in {".md", ".rst"}:
        return "section_extract", _extract_markdown_segments(text, artifact_type, query_terms)
    if suffix == ".json":
        return "key_block_extract", _extract_json_segments(text, artifact_type, query_terms)
    if suffix in {".yaml", ".yml"}:
        return "key_block_extract", _extract_yaml_segments(text, artifact_type, query_terms)
    if suffix == ".toml":
        return "key_block_extract", _extract_toml_segments(text, artifact_type, query_terms)
    return "full_text", []


def _critical_contract_tokens(path: str, text: str) -> tuple[str, ...]:
    if "reply_template" in path:
        desired = (
            "handoff_id",
            "preview",
            "confirmed",
            "archived",
            "brief.md",
            "bundle.md",
            "reply_template.md",
            *REPLY_TEMPLATE_FRONT_MATTER_KEYS,
            *REPLY_TEMPLATE_REQUIRED_HEADINGS,
        )
    elif "schema" in path or path.endswith(".json"):
        desired = (
            "handoff_id",
            "preview",
            "confirmed",
            "archived",
            "status",
            "paths",
            "artifacts",
            "brief.md",
            "bundle.md",
            "reply_template.md",
        )
    else:
        desired = (
            "handoff_id",
            "preview",
            "confirmed",
            "archived",
            "brief.md",
            "bundle.md",
            "reply_template.md",
        )
    present = []
    for token in desired:
        if token in text and token not in present:
            present.append(token)
    return tuple(present)


def _append_critical_contract_tokens(
    excerpt: str,
    critical_tokens: tuple[str, ...],
    limit_tokens: int,
    token_counter: TokenCounter,
) -> tuple[str, bool]:
    if not critical_tokens:
        return excerpt, True
    missing_tokens = [token for token in critical_tokens if token not in excerpt]
    if not missing_tokens:
        return excerpt, True

    base_lines = [excerpt.rstrip(), "", CRITICAL_TOKEN_HEADER]
    candidate = "\n".join(base_lines).strip()
    if token_counter.count(candidate) > limit_tokens:
        return excerpt, False
    for token in missing_tokens:
        candidate_line = f"- {token}"
        if token_counter.count(candidate + "\n" + candidate_line) > limit_tokens:
            return excerpt, False
        candidate += "\n" + candidate_line
    return candidate.strip(), True


def _build_contract_token_excerpt(
    path: str,
    critical_tokens: tuple[str, ...],
    limit_tokens: int,
    token_counter: TokenCounter,
) -> str:
    if not critical_tokens:
        return ""
    lines = [f"Typed digest for {path}", CRITICAL_TOKEN_HEADER]
    excerpt = "\n".join(lines)
    for token in critical_tokens:
        candidate = excerpt + f"\n- {token}"
        if token_counter.count(candidate) > limit_tokens:
            break
        excerpt = candidate
    return excerpt if token_counter.count(excerpt) <= limit_tokens else ""


def _render_structured_excerpt(
    segments: list[StructuredSegment],
    limit_tokens: int,
    token_counter: TokenCounter,
) -> tuple[str, list[str]]:
    if not segments:
        return "", []

    ranked = sorted(enumerate(segments), key=lambda item: (-item[1].priority, item[0]))
    chosen_indexes: list[int] = []
    current_tokens = 0

    for index, segment in ranked:
        segment_text = segment.text.strip()
        if not segment_text:
            continue
        segment_tokens = token_counter.count(segment_text)
        if segment_tokens > limit_tokens:
            continue
        extra_tokens = segment_tokens if not chosen_indexes else segment_tokens + token_counter.count(SEGMENT_SEPARATOR)
        if current_tokens + extra_tokens <= limit_tokens:
            chosen_indexes.append(index)
            current_tokens += extra_tokens

    if not chosen_indexes:
        return "", []

    chosen_indexes.sort()
    excerpt = SEGMENT_SEPARATOR.join(segments[index].text.strip() for index in chosen_indexes if segments[index].text.strip()).strip()
    if token_counter.count(excerpt) > limit_tokens:
        return "", []
    anchors = [segments[index].anchor for index in chosen_indexes]
    return excerpt, anchors


def _build_typed_digest(
    path: str,
    artifact_type: str,
    strategy: str,
    segments: list[StructuredSegment],
    limit_tokens: int,
    token_counter: TokenCounter,
    critical_tokens: tuple[str, ...] = (),
) -> tuple[str, list[str], bool]:
    """中文说明：在结构化摘录放不下时，生成可审计的确定性摘要。

    返回值中的 anchors 必须对应真正进入摘要的片段锚点，后续会直接写入
    manifest / preview，用于解释“摘要到底保留了哪几段”。
    """
    if not segments:
        return "", [], not critical_tokens

    ranked_segments = sorted(segments, key=lambda item: (-item.priority, item.anchor))
    base_lines = [
        f"Typed digest for {path}",
        f"- artifact_type: {artifact_type}",
        f"- excerpt_strategy: {strategy}",
    ]
    retained_anchors: list[str] = []
    detail_lines = ["- key points:"]
    preserved_lines = [CRITICAL_TOKEN_HEADER] if critical_tokens else []
    preserved_tokens: list[str] = []

    def compose_digest(extra_lines: list[str] | None = None) -> str:
        anchor_line = f"- retained anchors: {', '.join(retained_anchors) if retained_anchors else 'none'}"
        lines = [*base_lines, anchor_line, *preserved_lines, *detail_lines]
        if extra_lines:
            lines.extend(extra_lines)
        return "\n".join(lines)

    digest = compose_digest()
    if token_counter.count(digest) > limit_tokens:
        contract_excerpt = _build_contract_token_excerpt(path, critical_tokens, limit_tokens, token_counter)
        if contract_excerpt:
            return contract_excerpt, retained_anchors, all(token in contract_excerpt for token in critical_tokens)
        return fit_text_to_token_limit(digest, limit_tokens, token_counter), retained_anchors, False

    if critical_tokens:
        for token in critical_tokens:
            candidate_line = f"- {token}"
            candidate_lines = [*base_lines, f"- retained anchors: {', '.join(retained_anchors) if retained_anchors else 'none'}", *preserved_lines, candidate_line, *detail_lines]
            candidate_digest = "\n".join(candidate_lines)
            if token_counter.count(candidate_digest) <= limit_tokens:
                preserved_lines.append(candidate_line)
                preserved_tokens.append(token)
                digest = compose_digest()

    for segment in ranked_segments:
        candidate_line = f"  - {segment.summary}"
        candidate_anchors = [*retained_anchors, segment.anchor]
        anchor_line = f"- retained anchors: {', '.join(candidate_anchors)}"
        candidate_lines = [*base_lines, anchor_line, *preserved_lines, *detail_lines, candidate_line]
        candidate_digest = "\n".join(candidate_lines)
        if token_counter.count(candidate_digest) <= limit_tokens:
            detail_lines.append(candidate_line)
            retained_anchors = candidate_anchors
            digest = compose_digest()

    minimal_snippets = [segment.snippet for segment in ranked_segments if segment.snippet]
    if minimal_snippets:
        snippet_header = "\n- minimal snippets:"
        if token_counter.count(digest + snippet_header) <= limit_tokens:
            digest += snippet_header
            for snippet in minimal_snippets[:3]:
                candidate_line = f"\n  - {snippet}"
                if token_counter.count(digest + candidate_line) <= limit_tokens:
                    digest += candidate_line

    if token_counter.count(digest) > limit_tokens:
        contract_excerpt = _build_contract_token_excerpt(path, critical_tokens, limit_tokens, token_counter)
        if contract_excerpt:
            return contract_excerpt, retained_anchors, all(token in contract_excerpt for token in critical_tokens)
        return fit_text_to_token_limit(digest, limit_tokens, token_counter), retained_anchors, False
    return digest, retained_anchors, all(token in digest for token in critical_tokens)


def build_artifact_excerpt(
    path: str,
    text: str,
    artifact_type: str,
    limit_tokens: int,
    token_counter: TokenCounter,
    query_terms: set[str],
) -> ExcerptResult:
    """中文说明：按“结构化摘录 -> typed digest -> head/tail fallback”生成 artifact 摘录。

    这个顺序是当前 skill 的核心约束：优先保留有锚点、可解释的上下文，
    只有在前两层都不能满足 token 预算时才允许退回机械截断。
    """
    normalized = text.strip()
    if not normalized:
        return ExcerptResult("", False, "empty_text", "empty_text", [], "none", False, False)

    original_tokens = token_counter.count(normalized)
    strategy, segments = _extract_segments(path, normalized, artifact_type, query_terms)
    critical_tokens = _critical_contract_tokens(path, normalized) if artifact_type == "contract" else ()

    if strategy != "full_text" and segments:
        structured_excerpt, anchors = _render_structured_excerpt(segments, limit_tokens, token_counter)
        if structured_excerpt:
            critical_token_preserved = True
            if critical_tokens:
                structured_excerpt, critical_token_preserved = _append_critical_contract_tokens(
                    structured_excerpt,
                    critical_tokens,
                    limit_tokens,
                    token_counter,
                )
                if not critical_token_preserved:
                    structured_excerpt = ""
            if structured_excerpt:
                truncated = structured_excerpt != normalized
                return ExcerptResult(
                    text=structured_excerpt,
                    truncated=truncated,
                    truncation_method=strategy,
                    excerpt_strategy=strategy,
                    excerpt_anchor=anchors,
                    compaction_strategy="none",
                    fallback_used=False,
                    critical_token_preserved=critical_token_preserved,
                )

        digest, retained_anchors, critical_token_preserved = _build_typed_digest(
            path,
            artifact_type,
            strategy,
            segments,
            limit_tokens,
            token_counter,
            critical_tokens,
        )
        if digest and token_counter.count(digest) <= limit_tokens:
            return ExcerptResult(
                text=digest,
                truncated=True,
                truncation_method=f"typed_digest_compaction:{strategy}",
                excerpt_strategy=strategy,
                excerpt_anchor=retained_anchors,
                compaction_strategy="typed_digest_compaction",
                fallback_used=False,
                critical_token_preserved=critical_token_preserved,
            )

    if original_tokens <= limit_tokens:
        return ExcerptResult(
            normalized,
            False,
            "full_text",
            "full_text",
            [],
            "none",
            False,
            all(token in normalized for token in critical_tokens),
        )

    if critical_tokens:
        token_excerpt = _build_contract_token_excerpt(path, critical_tokens, limit_tokens, token_counter)
        if token_excerpt:
            return ExcerptResult(
                text=token_excerpt,
                truncated=True,
                truncation_method="typed_digest_compaction:critical_tokens",
                excerpt_strategy=strategy if strategy != "full_text" else "full_text",
                excerpt_anchor=[],
                compaction_strategy="typed_digest_compaction",
                fallback_used=False,
                critical_token_preserved=all(token in token_excerpt for token in critical_tokens),
            )

    excerpt, truncated, method = build_excerpt(normalized, limit_tokens, token_counter)
    return ExcerptResult(
        text=excerpt,
        truncated=truncated,
        truncation_method=method,
        excerpt_strategy="head_tail_fallback",
        excerpt_anchor=[],
        compaction_strategy=method.split(":", 1)[0],
        fallback_used=True,
        critical_token_preserved=all(token in excerpt for token in critical_tokens),
    )


def excerpt_language_for_path(path: str, compaction_strategy: str) -> str:
    if compaction_strategy == "typed_digest_compaction":
        return "text"
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".md": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".txt": "text",
        ".log": "text",
    }.get(suffix, "text")
