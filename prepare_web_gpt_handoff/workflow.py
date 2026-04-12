"""中文说明：本模块负责 handoff 产物组装、状态流转与可见入口输出。

它连接 brief、bundle、manifest、preview 和 confirm 流程，因此这里的统计
字段必须和真实 artifact 一一对应，不能把不在 files[] 中的概念伪装成文件层数据。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .config_paths import (
    HandoffInputs,
    MIN_EXCERPT_TOKENS,
    SKILL_NAME,
    SKILL_VERSION,
    STATUS_CONFIRMED,
    STATUS_PREVIEW,
    absolute_from_relative,
    ensure_within_project_root,
    iso_now,
    load_defaults,
    normalize_pattern,
    read_json,
    require_exact_tokens_from_env,
    render_template,
    slugify,
    timestamp_for_id,
    to_repo_relative,
    visible_handoff_dir,
    visible_handoffs_dir,
    write_json,
    write_text,
)
from .selection import (
    ARTIFACT_ATTACHMENTS_ONLY,
    ARTIFACT_CODE_SNIPPET,
    ARTIFACT_CONTRACT,
    ARTIFACT_SELECTION_LOGIC,
    ARTIFACT_SUPPORTING_CONTEXT,
    ARTIFACT_WORKFLOW,
    CONTEXT_LAYER_ATTACHMENTS,
    CONTEXT_LAYER_DYNAMIC_TASK,
    CONTEXT_LAYER_EVIDENCE,
    CONTEXT_LAYER_STABLE_CONTRACT,
    GRAPH_DIRECT_ANCHOR,
    PROTECTED_ARTIFACT_TYPES,
    STRATEGY_VERSION,
    GraphSelectionContext,
    SelectedFile,
    derive_query_terms,
    select_files,
)
from .token_tools import (
    ELLIPSIS,
    build_artifact_excerpt,
    build_token_runtime,
    excerpt_language_for_path,
    fit_text_to_token_limit,
    TokenCounter,
)


ENTRY_HANDOFF_ID_PATTERN = re.compile(r"^- handoff_id: `([^`]+)`$", re.MULTILINE)
BUNDLE_ORDER_VERSION = "position_aware_v1"


def clip_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - len(ELLIPSIS)].rstrip() + ELLIPSIS


def bulletize(items: Iterable[str], fallback: str) -> str:
    cleaned = [item.strip() for item in items if item.strip()]
    if not cleaned:
        return f"- {fallback}"
    return "\n".join(f"- {clip_text(item, 240)}" for item in cleaned)


def guess_language(path: str) -> str:
    return excerpt_language_for_path(path, "none")


def allocate_handoff_id(project_root: Path, topic: str) -> str:
    base_id = f"{timestamp_for_id()}_{slugify(topic)}"
    handoff_id = base_id
    counter = 1
    while visible_handoff_dir(project_root, handoff_id).exists():
        handoff_id = f"{base_id}_{counter:02d}"
        counter += 1
    return handoff_id


def make_handoff_dir(project_root: Path, handoff_id: str) -> Path:
    handoff_dir = visible_handoff_dir(project_root, handoff_id)
    handoff_dir.mkdir(parents=True, exist_ok=False)
    (handoff_dir / "attachments").mkdir(parents=True, exist_ok=True)
    return handoff_dir


def build_brief_context(inputs: HandoffInputs, selected_files: list[SelectedFile]) -> dict[str, str]:
    task_type = (
        f"这是一项以“{inputs.topic}”为主题的策略讨论 / 资料检索任务，当前模式为 `{inputs.mode}`。"
        "请把重点放在判断框架、研究路径、方案取舍、验证思路与资料补全上，而不是直接产出代码实现或改仓库补丁。"
    )
    context_files = ", ".join(file.path for file in selected_files[:4]) or "当前讨论中的关键文件"
    focus_text = "；".join(clip_text(item, 80) for item in inputs.focus_points[:5]) or "需要把当前问题边界、约束和优先级重新梳理清楚"
    task_goal = (
        f"当前目标是：{clip_text(inputs.goal, 220)}。"
        "我希望网页版 GPT 接手后继续围绕策略判断与研究结论展开，"
        f"并结合本次 handoff 中的材料（例如 {context_files}）给出更稳妥的路线建议。"
    )
    background_bits = [
        inputs.background or f"当前仓库与讨论已经积累出一批与主题直接相关的上下文，重点关注：{focus_text}。",
        f"本次 handoff 选入了 {len(selected_files)} 个 artifact，并按 contract / evidence / attachments 分层打包。",
        "需要延续的是思考链路与研究问题，而不是重新开启一个脱离上下文的实现任务。",
    ]
    current_background = " ".join(clip_text(bit, 260) for bit in background_bits if bit)
    known_items = inputs.known_routes or [
        "已经初步识别出约束条件、候选方向和需要补证据的部分",
        "倾向采用“少而准”的上下文交接方式，而不是整仓库打包",
        "需要把当前讨论沉淀成可继续推进多轮讨论的任务说明",
    ]
    known_routes = bulletize(known_items, "目前只有零散判断，需要你帮助归纳成可比较的路线。")
    blocker_items = inputs.blockers or [
        "当前最难的是把问题边界、材料选择和输出格式统一下来",
        "需要避免把策略问题直接误转成代码实现问题",
        "还需要确认哪些材料是必须读、哪些只适合做备查附件",
    ]
    current_blockers = bulletize(blocker_items, "需要帮助识别真正的核心矛盾与信息缺口。")
    question_items = inputs.questions or inputs.focus_points or [
        "应该如何定义这次研究/策略讨论的最小充分输入？",
        "哪些 artifact 最值得作为主阅读层，哪些应该只留在 attachments/？",
        "最终交付给网页版 GPT 的输出结构怎样才最利于继续多轮讨论？",
    ]
    priority_questions = bulletize(question_items, "请先帮助我澄清问题定义，再给出推荐路线。")
    avoid_items = inputs.avoid_directions or [
        "不要把任务直接改写成“替我实现功能”或“直接提交代码”",
        "不要给出脱离当前仓库约束的泛泛而谈建议",
        "不要为了覆盖面而把无关材料一股脑打包进去",
    ]
    avoid_directions = bulletize(avoid_items, "不要偏离当前主题。")
    output_items = inputs.output_requirements or [
        "请给出清晰的问题定义、推荐路线、备选路线和取舍理由",
        "请明确哪些判断来自已有材料，哪些需要补充外部资料",
        "请指出风险、反例与下一步验证动作，方便后续回到 Codex 继续推进",
    ]
    output_requirements = bulletize(output_items, "请产出可直接保存为 final_reply.md 的结构化结论。")
    return {
        "task_type": task_type,
        "task_goal": task_goal,
        "current_background": current_background,
        "known_routes": known_routes,
        "current_blockers": current_blockers,
        "priority_questions": priority_questions,
        "avoid_directions": avoid_directions,
        "output_requirements": output_requirements,
    }


def build_brief(inputs: HandoffInputs, selected_files: list[SelectedFile]) -> str:
    content = render_template("brief.template.md", build_brief_context(inputs, selected_files))
    return content.strip() + "\n"


def _contract_bundle_rank(item: SelectedFile) -> tuple[int, int, str]:
    path = item.path.lower()
    keyword_rank = 3
    if "schema" in path:
        keyword_rank = 0
    elif "reply_template" in path or "template" in path:
        keyword_rank = 1
    elif any(token in path for token in ("policy", "status", "manifest", "openai", "skill")):
        keyword_rank = 2
    return keyword_rank, item.priority, item.path


def _workflow_bundle_rank(item: SelectedFile) -> tuple[int, int, str]:
    path = item.path.lower()
    keyword_rank = 2
    if "confirm" in path:
        keyword_rank = 0
    elif any(token in path for token in ("preview", "prepare", "workflow")):
        keyword_rank = 1
    return keyword_rank, item.priority, item.path


def _code_bundle_rank(item: SelectedFile) -> tuple[int, int, str]:
    artifact_rank = 0 if item.artifact_type == ARTIFACT_SELECTION_LOGIC else 1
    dependency_rank = 0 if item.dependency_promoted else 1
    return dependency_rank, artifact_rank, item.path


def _supporting_bundle_rank(item: SelectedFile) -> tuple[int, int, str]:
    path = item.path.lower()
    keyword_rank = 1
    if any(token in path for token in ("problem", "overview", "research")):
        keyword_rank = 0
    return keyword_rank, item.priority, item.path


def group_files(selected_files: list[SelectedFile]) -> dict[str, list[SelectedFile]]:
    grouped = {
        "contract": [],
        "workflow": [],
        "code": [],
        "supporting": [],
        "attachments": [],
    }
    for item in selected_files:
        if not item.included_in_bundle:
            grouped["attachments"].append(item)
            continue
        if item.artifact_type == ARTIFACT_CONTRACT:
            grouped["contract"].append(item)
        elif item.artifact_type == ARTIFACT_WORKFLOW:
            grouped["workflow"].append(item)
        elif item.artifact_type in {ARTIFACT_SELECTION_LOGIC, ARTIFACT_CODE_SNIPPET}:
            grouped["code"].append(item)
        else:
            grouped["supporting"].append(item)
    grouped["contract"].sort(key=_contract_bundle_rank)
    grouped["workflow"].sort(key=_workflow_bundle_rank)
    grouped["code"].sort(key=_code_bundle_rank)
    grouped["supporting"].sort(key=_supporting_bundle_rank)
    return grouped


def render_file_block(item: SelectedFile) -> str:
    anchors = ", ".join(item.excerpt_anchor) if item.excerpt_anchor else "无"
    language = excerpt_language_for_path(item.path, item.compaction_strategy)
    lines = [
        f"### {item.path}",
        f"- 文件路径: `{item.path}`",
        f"- context_layer: `{item.context_layer}`",
        f"- artifact_type: `{item.artifact_type}`",
        f"- 选入原因: {item.selection_reason or item.reason}",
        f"- 摘录锚点: {anchors}",
        f"- 原始 token 数: {item.token_count_original}",
        f"- 选入 token 数: {item.token_count_included}",
        f"- excerpt_strategy: `{item.excerpt_strategy}`",
        f"- compaction_strategy: `{item.compaction_strategy}`",
        f"- 截断说明: {item.truncation_method}",
        "",
        f"```{language}",
        item.excerpt,
        "```",
        "",
    ]
    return "\n".join(lines)


def render_bundle_text(
    inputs: HandoffInputs,
    selected_files: list[SelectedFile],
    warnings: list[str],
) -> str:
    grouped = group_files(selected_files)
    attachments_only = grouped["attachments"]
    fallback_items = [item for item in selected_files if item.included_in_bundle and item.fallback_used]
    typed_digest_items = [item for item in selected_files if item.included_in_bundle and item.compaction_strategy == "typed_digest_compaction"]

    sections = [
        "# Handoff Bundle",
        "",
        "## 1. 问题定义与 handoff 目标",
        f"- mode: `{inputs.mode}`",
        f"- topic: `{inputs.topic}`",
        f"- 任务目标: {clip_text(inputs.goal, 280)}",
        f"- 关键关注点: {clip_text('；'.join(inputs.focus_points) or '需要继续澄清问题边界、关键约束与研究路线。', 320)}",
        "",
        "## 2. 关键 contract 与输出约束",
    ]
    if grouped["contract"]:
        sections.extend(render_file_block(item) for item in grouped["contract"])
    else:
        sections.extend(["本次主阅读层没有选入 contract artifact。", ""])

    sections.append("## 3. 工作流与状态变迁")
    if grouped["workflow"]:
        sections.extend(render_file_block(item) for item in grouped["workflow"])
    else:
        sections.extend(["本次主阅读层没有选入 workflow artifact。", ""])

    sections.append("## 4. 关键代码片段")
    if grouped["code"]:
        sections.extend(render_file_block(item) for item in grouped["code"])
    else:
        sections.extend(["本次主阅读层没有选入代码片段 artifact。", ""])

    sections.append("## 5. 支撑材料与补充上下文")
    if grouped["supporting"]:
        sections.extend(render_file_block(item) for item in grouped["supporting"])
    else:
        sections.extend(["本次主阅读层没有额外的 supporting context。", ""])

    risk_lines = [
        *(inputs.blockers or []),
        *warnings,
        *[
            f"{item.path}: 仅保留在 attachments/，未进入主阅读层。"
            for item in attachments_only
        ],
        *[
            f"{item.path}: 使用 typed_digest_compaction 保留关键锚点。"
            for item in typed_digest_items
        ],
        *[
            f"{item.path}: 因预算限制退回到 {item.truncation_method}。"
            for item in fallback_items
        ],
    ]
    sections.append("## 6. 风险、缺口与待验证点")
    sections.append(bulletize(risk_lines, "当前没有额外的风险或待验证点记录。"))
    sections.append("")
    return "\n".join(sections).strip() + "\n"


def _bundle_drop_rank(item: SelectedFile) -> tuple[int, int, int, str]:
    origin_rank = {"auto": 0, "mentioned": 1, "must_include": 2}.get(item.selection_origin, 2)
    artifact_rank = {
        ARTIFACT_SUPPORTING_CONTEXT: 0,
        ARTIFACT_CODE_SNIPPET: 1,
        ARTIFACT_SELECTION_LOGIC: 2,
        ARTIFACT_WORKFLOW: 3,
        ARTIFACT_CONTRACT: 4,
    }.get(item.preferred_artifact_type, 5)
    return origin_rank, artifact_rank, -item.token_count_original, item.path


def choose_drop_candidate(selected_files: list[SelectedFile]) -> SelectedFile | None:
    candidates = [
        item
        for item in selected_files
        if item.included_in_bundle
        and item.selection_origin != "must_include"
        and item.preferred_artifact_type not in PROTECTED_ARTIFACT_TYPES
    ]
    if not candidates:
        return None
    candidates.sort(key=_bundle_drop_rank)
    return candidates[0]


def shrink_excerpt_budgets(selected_files: list[SelectedFile], budgets: dict[str, int]) -> bool:
    changed = False
    for item in selected_files:
        if not item.included_in_bundle:
            continue
        current_budget = budgets[item.path]
        if item.token_count_original <= current_budget or current_budget <= MIN_EXCERPT_TOKENS:
            continue
        reduced_budget = max(MIN_EXCERPT_TOKENS, current_budget - max(1, current_budget // 5))
        if reduced_budget < current_budget:
            budgets[item.path] = reduced_budget
            changed = True
    return changed


def apply_bundle_state(
    selected_files: list[SelectedFile],
    budgets: dict[str, int],
    token_counter: TokenCounter,
    query_terms: set[str],
) -> None:
    for item in selected_files:
        if not item.included_in_bundle:
            item.context_layer = CONTEXT_LAYER_ATTACHMENTS
            item.artifact_type = ARTIFACT_ATTACHMENTS_ONLY
            item.excerpt = ""
            item.token_count_included = 0
            item.truncated = False
            item.truncation_method = "not_in_bundle"
            item.excerpt_strategy = "not_in_bundle"
            item.excerpt_anchor = []
            item.compaction_strategy = "none"
            item.fallback_used = False
            item.critical_token_preserved = False
            continue

        item.context_layer = item.preferred_context_layer
        item.artifact_type = item.preferred_artifact_type
        result = build_artifact_excerpt(
            item.path,
            item.content,
            item.preferred_artifact_type,
            budgets[item.path],
            token_counter,
            query_terms,
        )
        item.excerpt = result.text
        item.token_count_included = token_counter.count(result.text)
        item.truncated = result.truncated
        item.truncation_method = result.truncation_method
        item.excerpt_strategy = result.excerpt_strategy
        item.excerpt_anchor = result.excerpt_anchor
        item.compaction_strategy = result.compaction_strategy
        item.fallback_used = result.fallback_used
        item.critical_token_preserved = result.critical_token_preserved


def build_bundle(
    inputs: HandoffInputs,
    selected_files: list[SelectedFile],
    defaults: object,
    token_counter: TokenCounter,
    warnings: list[str],
) -> tuple[str, int]:
    budgets = {
        item.path: min(item.token_count_original, defaults.per_file_token_limit)
        for item in selected_files
    }
    query_terms = derive_query_terms(inputs)
    for item in selected_files:
        item.included_in_bundle = True

    while True:
        apply_bundle_state(selected_files, budgets, token_counter, query_terms)
        bundle = render_bundle_text(inputs, selected_files, warnings)
        bundle_tokens = token_counter.count(bundle)
        if bundle_tokens <= inputs.max_bundle_tokens:
            return bundle, bundle_tokens
        if shrink_excerpt_budgets(selected_files, budgets):
            continue
        drop_candidate = choose_drop_candidate(selected_files)
        if drop_candidate is None:
            raise ValueError(
                f"Unable to fit bundle within max_bundle_tokens={inputs.max_bundle_tokens}; "
                "reduce must_include files or increase the token budget."
            )
        drop_candidate.included_in_bundle = False


def build_notes(
    handoff_id: str,
    inputs: HandoffInputs,
    selected_files: list[SelectedFile],
    warnings: list[str],
    graph_context: GraphSelectionContext,
) -> str:
    included_items = [item for item in selected_files if item.included_in_bundle]
    attachment_only = [item for item in selected_files if not item.included_in_bundle]
    compaction_items = [item for item in included_items if item.compaction_strategy != "none" or item.fallback_used]

    main_reading_layer = bulletize(
        [
            f"{item.path}: {item.context_layer} / {item.artifact_type} / {item.selection_reason or item.reason}"
            for item in included_items
        ],
        "当前主阅读层没有额外说明。",
    )
    attachment_notes = bulletize(
        [
            f"{item.path}: 保留在 attachments/，原因是预算优先让位给更高优先级的主阅读层 artifact。"
            for item in attachment_only
        ],
        "本次没有 artifact 被压到 attachments/。",
    )
    graph_notes = bulletize(
        [
            f"{entry['artifact_path']}: path={ ' -> '.join(entry['path']) } / edge_types={', '.join(entry['edge_types']) or GRAPH_DIRECT_ANCHOR}"
            for entry in graph_context.explanation_summary.get("per_artifact_paths", [])[:6]
        ],
        "当前没有额外的图解释路径。",
    )
    compaction_notes = bulletize(
        [
            f"{item.path}: excerpt_strategy={item.excerpt_strategy}, compaction_strategy={item.compaction_strategy}, anchors={', '.join(item.excerpt_anchor) or '无'}"
            for item in compaction_items
        ],
        "当前主阅读层条目均未触发 compaction 或 fallback。",
    )
    excluded_notes = bulletize(
        warnings or [
            "默认排除了 data/、outputs/、依赖锁文件、大型二进制和全量日志原文。",
        ],
        "没有额外的排除说明。",
    )
    confirmation_checklist = bulletize(
        [
            "确认 brief.md 仍然只承载动态任务 framing，而不是实现需求。",
            "确认 bundle.md 的 contract / workflow / code snippet 分层是否符合当前主题。",
            "确认 typed digest 或 fallback 条目仍然保留了继续讨论所需的决策、约束与锚点。",
            "确认 handoff_id 会在未来 final_reply.md 中被回显。",
        ],
        "确认预览后再执行 confirm_handoff.py。",
    )
    return (
        render_template(
            "notes.template.md",
            {
                "handoff_id": handoff_id,
                "mode": inputs.mode,
                "topic": inputs.topic,
                "main_reading_layer": main_reading_layer,
                "attachment_decisions": attachment_notes,
                "graph_notes": graph_notes,
                "compaction_notes": compaction_notes,
                "excluded_areas": excluded_notes,
                "confirmation_checklist": confirmation_checklist,
            },
        ).strip()
        + "\n"
    )


def build_reply_template(handoff_id: str, inputs: HandoffInputs) -> str:
    return (
        render_template(
            "reply_template.md",
            {
                "handoff_id": handoff_id,
                "topic": inputs.topic,
                "mode": inputs.mode,
                "reply_template_version": SKILL_VERSION,
            },
        ).strip()
        + "\n"
    )


def summarize_brief(brief_text: str, defaults: object, token_counter: TokenCounter) -> str:
    summary = re.sub(r"#+\s*", "", brief_text)
    return fit_text_to_token_limit(summary, defaults.brief_summary_tokens, token_counter)


def copy_attachments(project_root: Path, handoff_dir: Path, selected_files: list[SelectedFile]) -> None:
    attachments_root = handoff_dir / "attachments"
    for item in selected_files:
        attachment_target = attachments_root / Path(*PurePosixPath(item.path).parts)
        attachment_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item.absolute_path, attachment_target)
        item.attachment_path = to_repo_relative(attachment_target, project_root)


def _top_anchors(selected_files: list[SelectedFile], limit: int = 6) -> list[str]:
    anchors: list[str] = []
    for item in selected_files:
        if not item.included_in_bundle:
            continue
        for anchor in item.excerpt_anchor:
            if anchor not in anchors:
                anchors.append(anchor)
            if len(anchors) >= limit:
                return anchors
    return anchors


def _anchor_fidelity(selected_files: list[SelectedFile]) -> bool:
    for item in selected_files:
        if not item.included_in_bundle:
            continue
        if item.excerpt_strategy in {"symbol_extract", "section_extract", "key_block_extract"} and not item.excerpt_anchor:
            return False
        if item.compaction_strategy == "typed_digest_compaction" and item.artifact_type != ARTIFACT_CONTRACT and not item.excerpt_anchor:
            return False
    return True


def _explanation_coverage(selected_files: list[SelectedFile]) -> int:
    """中文说明：统计主阅读层中具备图解释路径的条目覆盖率。"""

    included_items = [item for item in selected_files if item.included_in_bundle]
    if not included_items:
        return 100
    explained_count = sum(1 for item in included_items if item.explanation_path_ref)
    return int(round((explained_count / len(included_items)) * 100))


def _bundle_order_valid(selected_files: list[SelectedFile]) -> bool:
    grouped = group_files(selected_files)
    if grouped["contract"] and grouped["supporting"]:
        return True
    if grouped["workflow"] and grouped["supporting"]:
        return True
    return True


def build_quality_metrics(selected_files: list[SelectedFile], bundle_tokens: int, max_bundle_tokens: int) -> dict[str, Any]:
    included_items = [item for item in selected_files if item.included_in_bundle]
    included_count = max(len(included_items), 1)
    structured_count = sum(
        1
        for item in included_items
        if item.excerpt_strategy in {"symbol_extract", "section_extract", "key_block_extract"}
        and item.compaction_strategy == "none"
    )
    fallback_count = sum(1 for item in included_items if item.fallback_used)
    return {
        "contract_coverage": sum(1 for item in included_items if item.artifact_type == ARTIFACT_CONTRACT),
        "workflow_coverage": sum(1 for item in included_items if item.artifact_type == ARTIFACT_WORKFLOW),
        "structured_extract_ratio": int(round((structured_count / included_count) * 100)),
        "fallback_ratio": int(round((fallback_count / included_count) * 100)),
        "budget_compliance": bundle_tokens <= max_bundle_tokens,
        "anchor_fidelity": _anchor_fidelity(selected_files),
        "bundle_order_valid": _bundle_order_valid(selected_files),
        "explanation_coverage": _explanation_coverage(selected_files),
    }


def build_visible_entry_text(
    project_root: Path,
    manifest: dict[str, Any],
    preview_payload: dict[str, Any],
) -> str:
    artifacts = manifest["artifacts"]
    handoff_dir = manifest["paths"]["handoff_dir"]
    absolute_handoff_dir = absolute_from_relative(project_root, handoff_dir)
    next_actions = "\n".join(
        f"{index}. {action}"
        for index, action in enumerate(preview_payload.get("next_actions", []), start=1)
    )
    visible_dir = visible_handoff_dir(project_root, manifest["handoff_id"])
    top_anchors = ", ".join(preview_payload.get("top_anchors", [])) or "无"
    return (
        "# Handoff Entry\n\n"
        f"- handoff_id: `{manifest['handoff_id']}`\n"
        f"- status: `{manifest['status']}`\n"
        f"- mode: `{manifest['mode']}`\n"
        f"- topic: `{manifest['topic']}`\n"
        f"- handoff 目录: `{to_repo_relative(visible_dir, project_root)}`\n"
        f"- 当前机器绝对路径: `{absolute_handoff_dir}`\n\n"
        "## Key Files\n\n"
        f"- `brief.md`: `{artifacts['brief_md']}`\n"
        f"- `bundle.md`: `{artifacts['bundle_md']}`\n"
        f"- `manifest.json`: `{artifacts['manifest_json']}`\n"
        f"- `reply_template.md`: `{artifacts['reply_template_md']}`\n"
        f"- `notes.md`: `{artifacts['notes_md']}`\n"
        f"- `preview.json`: `{artifacts['preview_json']}`\n\n"
        "这些文件都可以直接在 `handoffs/` 目录中打开查看。\n\n"
        "## Preview Summary\n\n"
        f"- 选入文件数: {preview_payload['selected_file_count']}\n"
        f"- contract 条目数: {preview_payload['contract_count']}\n"
        f"- workflow 条目数: {preview_payload['workflow_count']}\n"
        f"- 结构化摘录数: {preview_payload['structured_extract_count']}\n"
        f"- fallback 条目数: {preview_payload['fallback_count']}\n"
        f"- retrieval_gate: {preview_payload.get('retrieval_gate', 'unknown')}\n"
        f"- token_count_method: {preview_payload.get('token_runtime', {}).get('resolved_method', 'unknown')}\n"
        f"- bundle_order_valid: {preview_payload.get('quality_metrics', {}).get('bundle_order_valid', False)}\n"
        f"- brief 摘要: {preview_payload['brief_summary']}\n"
        f"- top_anchors: {top_anchors}\n\n"
        "## Recommended Send Order\n\n"
        "1. `brief.md`\n"
        "2. `bundle.md`\n"
        "3. `reply_template.md`\n\n"
        "## Next Actions\n\n"
        f"{next_actions}\n"
    )


def write_visible_entry(
    project_root: Path,
    manifest: dict[str, Any],
    preview_payload: dict[str, Any],
) -> None:
    visible_dir = visible_handoffs_dir(project_root)
    visible_dir.mkdir(parents=True, exist_ok=True)
    entry_text = build_visible_entry_text(project_root, manifest, preview_payload)
    write_text(visible_dir / f"{manifest['handoff_id']}.md", entry_text)
    write_text(visible_dir / "LATEST.md", entry_text)


def create_preview_payload(
    handoff_id: str,
    manifest: dict[str, Any],
    brief_text: str,
    selected_files: list[SelectedFile],
    defaults: object,
    token_counter: TokenCounter,
) -> dict[str, Any]:
    selection_summary = manifest["selection_summary"]
    return {
        "handoff_id": handoff_id,
        "status": manifest["status"],
        "mode": manifest["mode"],
        "topic": manifest["topic"],
        "selected_file_count": selection_summary["selected_files"],
        "truncated_file_count": selection_summary["truncated_files"],
        "excluded_file_count": selection_summary["excluded_files"],
        "contract_count": selection_summary["contract_artifacts_selected"],
        "workflow_count": selection_summary["workflow_artifacts_selected"],
        "structured_extract_count": selection_summary["structured_extract_files"],
        "fallback_count": selection_summary["fallback_head_tail_files"],
        "retrieval_gate": selection_summary["retrieval_gate"],
        "quality_metrics": selection_summary["quality_metrics"],
        "token_runtime": selection_summary["token_runtime"],
        "selector_engine": selection_summary["selector_engine"],
        "repo_graph": selection_summary["repo_graph"],
        "explanation": manifest["explanation"],
        "brief_summary": summarize_brief(brief_text, defaults, token_counter),
        "file_list_summary": [
            {
                "path": item.path,
                "type": item.type,
                "reason": item.reason,
                "context_layer": item.context_layer,
                "artifact_type": item.artifact_type,
                "excerpt_strategy": item.excerpt_strategy,
                "compaction_strategy": item.compaction_strategy,
                "excerpt_anchor": list(item.excerpt_anchor),
                "truncated": item.truncated,
                "included_in_bundle": item.included_in_bundle,
                "dependency_promoted": item.dependency_promoted,
                "critical_token_preserved": item.critical_token_preserved,
                "graph_selected": item.graph_selected,
                "graph_distance": item.graph_distance,
                "graph_path_types": list(item.graph_path_types),
                "explanation_path_ref": item.explanation_path_ref,
            }
            for item in selected_files
        ],
        "top_anchors": _top_anchors(selected_files),
        "next_actions": manifest["notes"]["next_actions"],
    }


def build_preview_text(preview_payload: dict[str, Any]) -> str:
    file_lines = preview_payload.get("file_list_summary", [])
    files_text = "\n".join(
        f"- {item.get('path', 'unknown')} [{item.get('artifact_type', item.get('type', 'unknown'))}] "
        f"{'已进入 bundle' if item.get('included_in_bundle') else '仅保留在 attachments'} / "
        f"strategy={item.get('excerpt_strategy', 'legacy')} / "
        f"{'已截断' if item.get('truncated') else '完整'}"
        for item in file_lines
    ) or "- 本次未选入文件"
    next_actions = "\n".join(
        f"{index}. {action}" for index, action in enumerate(preview_payload.get("next_actions", []), start=1)
    ) or "1. 需要时确认交付。"
    top_anchors = ", ".join(preview_payload.get("top_anchors", [])) or "无"
    return (
        "Handoff 预览\n"
        f"mode: {preview_payload['mode']}\n"
        f"topic: {preview_payload['topic']}\n"
        f"handoff_id: {preview_payload['handoff_id']}\n"
        f"选入文件数: {preview_payload['selected_file_count']}\n"
        f"截断文件数: {preview_payload['truncated_file_count']}\n"
        f"排除文件数: {preview_payload['excluded_file_count']}\n"
        f"contract 条目数: {preview_payload.get('contract_count', 0)}\n"
        f"workflow 条目数: {preview_payload.get('workflow_count', 0)}\n"
        f"结构化摘录数: {preview_payload.get('structured_extract_count', 0)}\n"
        f"fallback 条目数: {preview_payload.get('fallback_count', 0)}\n"
        f"retrieval_gate: {preview_payload.get('retrieval_gate', 'unknown')}\n"
        f"token_count_method: {preview_payload.get('token_runtime', {}).get('resolved_method', 'unknown')}\n"
        f"selector_engine: {preview_payload.get('selector_engine', {}).get('name', 'unknown')}@"
        f"{preview_payload.get('selector_engine', {}).get('version', 'unknown')}\n"
        f"two_hop_triggered: {preview_payload.get('repo_graph', {}).get('two_hop_triggered', False)}\n"
        f"bundle_order_valid: {preview_payload.get('quality_metrics', {}).get('bundle_order_valid', False)}\n"
        f"explanation_coverage: {preview_payload.get('quality_metrics', {}).get('explanation_coverage', 0)}\n"
        f"top_anchors: {top_anchors}\n\n"
        "brief 摘要:\n"
        f"{preview_payload['brief_summary']}\n\n"
        "文件清单摘要:\n"
        f"{files_text}\n\n"
        "下一步可选动作:\n"
        f"{next_actions}\n"
    )


def _bundle_layer_counts(selected_files: list[SelectedFile]) -> dict[str, int]:
    """中文说明：统计真实进入主阅读层和附件层的 artifact 数量。

    `dynamic_task` 由 brief.md 单独承载，不属于 files[] 中的 artifact，
    因此这里必须保持为 0，避免 manifest 统计和真实文件选择模型不一致。
    """
    counts = {
        CONTEXT_LAYER_STABLE_CONTRACT: 0,
        CONTEXT_LAYER_DYNAMIC_TASK: 0,
        CONTEXT_LAYER_EVIDENCE: 0,
        CONTEXT_LAYER_ATTACHMENTS: 0,
    }
    for item in selected_files:
        if item.included_in_bundle and item.context_layer == CONTEXT_LAYER_STABLE_CONTRACT:
            counts[CONTEXT_LAYER_STABLE_CONTRACT] += 1
        elif item.included_in_bundle:
            counts[CONTEXT_LAYER_EVIDENCE] += 1
        else:
            counts[CONTEXT_LAYER_ATTACHMENTS] += 1
    return counts


def prepare_handoff(project_root: Path, inputs: HandoffInputs) -> dict[str, Any]:
    project_root = project_root.resolve()
    defaults = load_defaults()
    normalized_inputs = inputs.normalized()
    effective_require_exact_tokens = (
        normalized_inputs.require_exact_tokens or require_exact_tokens_from_env()
    )
    token_runtime = build_token_runtime(
        defaults,
        require_exact_tokens=effective_require_exact_tokens,
    )
    token_counter = token_runtime.counter
    selected_files, summary_seed, warnings, graph_context = select_files(
        project_root,
        normalized_inputs,
        defaults,
        token_counter,
    )
    if not token_runtime.exact_available:
        warnings.append(
            "未使用精确 token 计数，当前 token 预算回退为估算模式："
            f"{token_runtime.resolved_method}"
            + (
                f"（原因：{token_runtime.fallback_reason}）"
                if token_runtime.fallback_reason
                else ""
            )
        )

    brief_text = build_brief(normalized_inputs, selected_files)
    bundle_text, bundle_tokens = build_bundle(normalized_inputs, selected_files, defaults, token_counter, warnings)

    handoff_id = allocate_handoff_id(project_root, normalized_inputs.topic)
    handoff_dir = make_handoff_dir(project_root, handoff_id)
    copy_attachments(project_root, handoff_dir, selected_files)

    notes_text = build_notes(handoff_id, normalized_inputs, selected_files, warnings, graph_context)
    reply_template_text = build_reply_template(handoff_id, normalized_inputs)

    artifacts = {
        "brief_md": to_repo_relative(handoff_dir / "brief.md", project_root),
        "bundle_md": to_repo_relative(handoff_dir / "bundle.md", project_root),
        "manifest_json": to_repo_relative(handoff_dir / "manifest.json", project_root),
        "reply_template_md": to_repo_relative(handoff_dir / "reply_template.md", project_root),
        "notes_md": to_repo_relative(handoff_dir / "notes.md", project_root),
        "preview_json": to_repo_relative(handoff_dir / "preview.json", project_root),
    }
    critical_contract_items = [
        item.path
        for item in selected_files
        if item.included_in_bundle and item.artifact_type == ARTIFACT_CONTRACT and item.critical_token_preserved
    ]
    dependency_promoted_items = [
        item.path
        for item in selected_files
        if item.included_in_bundle and item.dependency_promoted
    ]
    quality_metrics = build_quality_metrics(selected_files, bundle_tokens, normalized_inputs.max_bundle_tokens)

    selection_summary = {
        "total_candidate_files": summary_seed["total_candidate_files"],
        "selected_files": len(selected_files),
        "truncated_files": sum(1 for item in selected_files if item.truncated),
        "excluded_files": summary_seed["excluded_files"],
        "total_bundle_tokens": bundle_tokens,
        "max_files_requested": normalized_inputs.max_files,
        "max_bundle_tokens_requested": normalized_inputs.max_bundle_tokens,
        "token_count_method": token_runtime.resolved_method,
        "token_runtime": {
            "exact_requested": token_runtime.exact_requested,
            "exact_available": token_runtime.exact_available,
            "resolved_method": token_runtime.resolved_method,
            "fallback_reason": token_runtime.fallback_reason,
        },
        "contract_artifacts_selected": sum(1 for item in selected_files if item.included_in_bundle and item.artifact_type == ARTIFACT_CONTRACT),
        "workflow_artifacts_selected": sum(1 for item in selected_files if item.included_in_bundle and item.artifact_type == ARTIFACT_WORKFLOW),
        "structured_extract_files": sum(
            1
            for item in selected_files
            if item.included_in_bundle
            and item.excerpt_strategy in {"symbol_extract", "section_extract", "key_block_extract"}
            and item.compaction_strategy == "none"
        ),
        "typed_digest_files": sum(1 for item in selected_files if item.included_in_bundle and item.compaction_strategy == "typed_digest_compaction"),
        "fallback_head_tail_files": sum(1 for item in selected_files if item.included_in_bundle and item.fallback_used),
        "bundle_layer_counts": _bundle_layer_counts(selected_files),
        "strategy_version": STRATEGY_VERSION,
        "bundle_order_version": BUNDLE_ORDER_VERSION,
        "critical_contract_items": critical_contract_items,
        "dependency_promoted_items": dependency_promoted_items,
        "selector_engine": graph_context.selector_engine,
        "repo_graph": graph_context.repo_graph_summary,
        "retrieval_gate": summary_seed["retrieval_gate"],
        "quality_metrics": quality_metrics,
    }

    manifest = {
        "skill_name": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "handoff_id": handoff_id,
        "created_at": iso_now(),
        "mode": normalized_inputs.mode,
        "topic": normalized_inputs.topic,
        "goal": normalized_inputs.goal,
        "status": STATUS_PREVIEW,
        "paths": {
            "project_root": ".",
            "handoff_dir": to_repo_relative(handoff_dir, project_root),
            "attachments_dir": to_repo_relative(handoff_dir / "attachments", project_root),
        },
        "inputs": {
            "mode": normalized_inputs.mode,
            "topic": normalized_inputs.topic,
            "goal": normalized_inputs.goal,
            "focus_points": normalized_inputs.focus_points,
            "must_include": normalized_inputs.must_include,
            "must_exclude": normalized_inputs.must_exclude,
            "max_files": normalized_inputs.max_files,
            "max_bundle_tokens": normalized_inputs.max_bundle_tokens,
            "background": normalized_inputs.background,
            "known_routes": normalized_inputs.known_routes,
            "blockers": normalized_inputs.blockers,
            "questions": normalized_inputs.questions,
            "avoid_directions": normalized_inputs.avoid_directions,
            "output_requirements": normalized_inputs.output_requirements,
            "mentioned_paths": normalized_inputs.mentioned_paths,
            "require_exact_tokens": effective_require_exact_tokens,
        },
        "selection_summary": selection_summary,
        "files": [item.to_manifest() for item in selected_files],
        "explanation": graph_context.explanation_summary,
        "artifacts": artifacts,
        "notes": {
            "summary": f"已为主题“{normalized_inputs.topic}”生成 preview 状态的 handoff 包。",
            "warnings": warnings,
            "next_actions": list(defaults.default_next_actions),
            "recommended_send_order": ["brief.md", "bundle.md", "reply_template.md"],
        },
    }

    preview_payload = create_preview_payload(handoff_id, manifest, brief_text, selected_files, defaults, token_counter)

    write_text(handoff_dir / "brief.md", brief_text)
    write_text(handoff_dir / "bundle.md", bundle_text)
    write_text(handoff_dir / "reply_template.md", reply_template_text)
    write_text(handoff_dir / "notes.md", notes_text)
    write_json(handoff_dir / "manifest.json", manifest)
    write_json(handoff_dir / "preview.json", preview_payload)
    write_visible_entry(project_root, manifest, preview_payload)

    return {
        "handoff_id": handoff_id,
        "handoff_dir": handoff_dir,
        "manifest": manifest,
        "preview": preview_payload,
        "preview_text": build_preview_text(preview_payload),
    }


def parse_handoff_id_from_entry(entry_path: Path) -> str:
    if not entry_path.exists():
        raise FileNotFoundError(f"Handoff entry file not found: {entry_path}")
    match = ENTRY_HANDOFF_ID_PATTERN.search(entry_path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"Malformed handoff entry file: {entry_path}")
    return match.group(1)


def resolve_handoff_dir(project_root: Path, handoff_ref: str) -> Path:
    project_root = project_root.resolve()
    raw = Path(handoff_ref)

    if raw.is_absolute():
        resolved = ensure_within_project_root(raw, project_root, "handoff path")
        if resolved.suffix == ".md":
            return resolve_handoff_dir(project_root, to_repo_relative(resolved, project_root))
        if resolved.suffix == ".json":
            return ensure_within_project_root(resolved.parent, project_root, "handoff directory")
        return resolved

    normalized = normalize_pattern(handoff_ref)
    if raw.suffix == ".md":
        entry_path = ensure_within_project_root(project_root / Path(*PurePosixPath(normalized).parts), project_root, "handoff entry")
        handoff_id = parse_handoff_id_from_entry(entry_path)
        handoff_dir = ensure_within_project_root(visible_handoff_dir(project_root, handoff_id), project_root, "handoff directory")
        if not handoff_dir.is_dir():
            raise FileNotFoundError(f"Handoff directory referenced by {entry_path} does not exist: {handoff_dir}")
        return handoff_dir

    if raw.suffix == ".json":
        manifest_path = ensure_within_project_root(project_root / Path(*PurePosixPath(normalized).parts), project_root, "handoff manifest")
        return ensure_within_project_root(manifest_path.parent, project_root, "handoff directory")

    if normalized.startswith("handoffs/") or normalized.startswith("handoffs\\"):
        return ensure_within_project_root(project_root / Path(*PurePosixPath(normalized).parts), project_root, "handoff directory")
    if normalized.startswith(".codex/") or normalized.startswith(".codex\\"):
        return ensure_within_project_root(project_root / Path(*PurePosixPath(normalized).parts), project_root, "handoff directory")

    visible_candidate = visible_handoffs_dir(project_root) / normalized
    if visible_candidate.exists():
        return ensure_within_project_root(visible_candidate, project_root, "handoff directory")

    legacy_candidate = project_root / ".codex" / "handoffs" / normalized
    if legacy_candidate.exists():
        return ensure_within_project_root(legacy_candidate, project_root, "handoff directory")

    fallback_candidate = ensure_within_project_root(project_root / raw, project_root, "handoff directory")
    return fallback_candidate


def validate_handoff_payload(
    project_root: Path,
    handoff_dir: Path,
    manifest: dict[str, Any],
    preview_payload: dict[str, Any],
) -> None:
    if "paths" not in manifest or "handoff_dir" not in manifest["paths"]:
        raise ValueError(f"Manifest is missing paths.handoff_dir: {handoff_dir / 'manifest.json'}")
    expected_dir = ensure_within_project_root(
        absolute_from_relative(project_root, manifest["paths"]["handoff_dir"]),
        project_root,
        "manifest handoff directory",
    )
    if expected_dir != handoff_dir.resolve():
        raise ValueError(
            "Manifest handoff_dir does not match the resolved handoff directory: "
            f"{expected_dir} != {handoff_dir.resolve()}"
        )
    if manifest["handoff_id"] != preview_payload["handoff_id"]:
        raise ValueError("preview.json handoff_id does not match manifest.json")


def load_handoff_payload(
    project_root: Path,
    handoff_ref: str,
) -> tuple[Path, Path, Path, dict[str, Any], dict[str, Any]]:
    handoff_dir = resolve_handoff_dir(project_root, handoff_ref)
    handoff_dir = ensure_within_project_root(handoff_dir, project_root, "handoff directory")
    manifest_path = handoff_dir / "manifest.json"
    preview_path = handoff_dir / "preview.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {handoff_dir}")
    if not preview_path.exists():
        raise FileNotFoundError(f"preview.json not found in {handoff_dir}")
    manifest = read_json(manifest_path)
    preview_payload = read_json(preview_path)
    validate_handoff_payload(project_root, handoff_dir, manifest, preview_payload)
    return handoff_dir, manifest_path, preview_path, manifest, preview_payload


def load_preview(project_root: Path, handoff_ref: str) -> dict[str, Any]:
    _, _, _, _, preview_payload = load_handoff_payload(project_root.resolve(), handoff_ref)
    return preview_payload


def render_preview(project_root: Path, handoff_ref: str) -> str:
    preview_payload = load_preview(project_root.resolve(), handoff_ref)
    return build_preview_text(preview_payload)


def confirm_handoff(project_root: Path, handoff_ref: str) -> dict[str, Any]:
    project_root = project_root.resolve()
    handoff_dir, manifest_path, preview_path, manifest, preview_payload = load_handoff_payload(project_root, handoff_ref)

    manifest["status"] = STATUS_CONFIRMED
    manifest["confirmed_at"] = iso_now()
    manifest["notes"]["summary"] = f"已确认交付主题“{manifest['topic']}”的 handoff 包。"
    preview_payload["status"] = STATUS_CONFIRMED

    write_json(manifest_path, manifest)
    write_json(preview_path, preview_payload)
    write_visible_entry(project_root, manifest, preview_payload)

    relative_handoff_dir = manifest["paths"]["handoff_dir"]
    absolute_handoff_dir = absolute_from_relative(project_root, relative_handoff_dir)
    artifacts = manifest["artifacts"]
    report = (
        "Handoff 正式交付报告\n"
        f"handoff_id: {manifest['handoff_id']}\n"
        f"handoff 目录相对路径: {relative_handoff_dir}\n"
        f"当前机器绝对路径: {absolute_handoff_dir}\n"
        f"brief.md 路径: {artifacts['brief_md']}\n"
        f"bundle.md 路径: {artifacts['bundle_md']}\n"
        f"manifest.json 路径: {artifacts['manifest_json']}\n"
        f"reply_template.md 路径: {artifacts['reply_template_md']}\n"
        f"notes.md 路径: {artifacts['notes_md']}\n\n"
        "推荐发送顺序:\n"
        "1. brief.md\n"
        "2. bundle.md\n"
        "3. reply_template.md\n"
    )
    return {
        "manifest": manifest,
        "preview": preview_payload,
        "report": report,
    }
