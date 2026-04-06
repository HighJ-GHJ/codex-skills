from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from string import Template
from typing import Any, Iterable


SKILL_NAME = "prepare_web_gpt_handoff"
SKILL_VERSION = "0.1.0"
STATUS_PREVIEW = "preview"
STATUS_CONFIRMED = "confirmed"
STATUS_ARCHIVED = "archived"

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
REPO_ROOT = SCRIPT_DIR.parents[3]


@dataclass
class HandoffInputs:
    mode: str
    topic: str
    goal: str
    focus_points: list[str] = field(default_factory=list)
    must_include: list[str] = field(default_factory=list)
    must_exclude: list[str] = field(default_factory=list)
    max_files: int = 8
    max_bundle_chars: int = 14000
    background: str = ""
    known_routes: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    avoid_directions: list[str] = field(default_factory=list)
    output_requirements: list[str] = field(default_factory=list)
    mentioned_paths: list[str] = field(default_factory=list)

    def normalized(self) -> "HandoffInputs":
        return HandoffInputs(
            mode=self.mode.strip(),
            topic=self.topic.strip(),
            goal=self.goal.strip(),
            focus_points=dedupe_strings(self.focus_points),
            must_include=dedupe_strings(self.must_include),
            must_exclude=dedupe_strings(self.must_exclude),
            max_files=max(1, self.max_files),
            max_bundle_chars=max(1200, self.max_bundle_chars),
            background=self.background.strip(),
            known_routes=dedupe_strings(self.known_routes),
            blockers=dedupe_strings(self.blockers),
            questions=dedupe_strings(self.questions),
            avoid_directions=dedupe_strings(self.avoid_directions),
            output_requirements=dedupe_strings(self.output_requirements),
            mentioned_paths=dedupe_strings(self.mentioned_paths),
        )


@dataclass
class SelectedFile:
    path: str
    absolute_path: Path
    type: str
    status: str
    included_in_bundle: bool
    reason: str
    char_count_original: int
    char_count_included: int
    truncated: bool
    truncation_method: str
    priority: int
    attachment_path: str = ""
    excerpt: str = ""
    content: str = ""

    def to_manifest(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("absolute_path")
        data.pop("excerpt")
        data.pop("content")
        return data


def skill_root() -> Path:
    return SKILL_ROOT


def default_project_root() -> Path:
    return REPO_ROOT


def defaults_path() -> Path:
    return SKILL_ROOT / "config" / "defaults.yaml"


def manifest_schema_path() -> Path:
    return SKILL_ROOT / "schemas" / "manifest.schema.json"


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


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    if value.isdigit():
        return int(value)
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return value


def load_defaults(path: Path | None = None) -> dict[str, Any]:
    source = path or defaults_path()
    data: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        if stripped.startswith("- "):
            if current_list_key is None:
                raise ValueError(f"List item without a key in {source}")
            data.setdefault(current_list_key, []).append(parse_scalar(stripped[2:]))
            continue
        current_list_key = None
        key, _, remainder = line.partition(":")
        key = key.strip()
        remainder = remainder.strip()
        if remainder:
            data[key] = parse_scalar(remainder)
        else:
            data[key] = []
            current_list_key = key
    return data


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


def clip_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def bulletize(items: Iterable[str], fallback: str) -> str:
    cleaned = [item.strip() for item in items if item.strip()]
    if not cleaned:
        return f"- {fallback}"
    return "\n".join(f"- {clip_text(item, 240)}" for item in cleaned)


def guess_language(path: str) -> str:
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
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def should_exclude(relative_path: str, defaults: dict[str, Any]) -> bool:
    parts = PurePosixPath(relative_path).parts
    excluded_dirs = set(defaults.get("excluded_dirs", []))
    excluded_suffixes = set(defaults.get("excluded_suffixes", []))
    excluded_names = set(defaults.get("excluded_names", []))

    if Path(relative_path).name in excluded_names:
        return True
    if Path(relative_path).suffix.lower() in excluded_suffixes:
        return True
    for part in parts[:-1]:
        if part in excluded_dirs:
            return True
    for excluded_dir in excluded_dirs:
        normalized_dir = normalize_pattern(excluded_dir)
        if normalized_dir and (
            relative_path == normalized_dir or relative_path.startswith(normalized_dir + "/")
        ):
            return True
    return False


def scan_project_files(project_root: Path, defaults: dict[str, Any]) -> tuple[dict[str, Path], int]:
    candidates: dict[str, Path] = {}
    excluded_count = 0
    for path in sorted(project_root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = to_repo_relative(path, project_root)
        if should_exclude(relative_path, defaults):
            excluded_count += 1
            continue
        if not is_probably_text(path):
            excluded_count += 1
            continue
        candidates[relative_path] = path
    return candidates, excluded_count


def detect_mentioned_paths(texts: Iterable[str], candidates: dict[str, Path]) -> list[str]:
    hits: list[str] = []
    available = set(candidates)
    basenames: dict[str, list[str]] = {}
    for relative_path in candidates:
        basenames.setdefault(Path(relative_path).name, []).append(relative_path)
    pattern = re.compile(r"[A-Za-z0-9_./\\-]+\.[A-Za-z0-9_]+")
    for text in texts:
        for token in pattern.findall(text):
            normalized = normalize_pattern(token)
            if normalized in available and normalized not in hits:
                hits.append(normalized)
                continue
            basename = Path(normalized).name
            for candidate in basenames.get(basename, []):
                if candidate not in hits:
                    hits.append(candidate)
    return hits


def resolve_pattern(pattern: str, project_root: Path, candidates: dict[str, Path]) -> list[str]:
    normalized = normalize_pattern(pattern)
    if not normalized:
        return []
    absolute_candidate = Path(normalized)
    if absolute_candidate.is_absolute():
        try:
            normalized = to_repo_relative(absolute_candidate, project_root)
        except ValueError:
            return []
    if any(token in normalized for token in ["*", "?", "["]):
        return sorted(relative for relative in candidates if fnmatch(relative, normalized))
    concrete = absolute_from_relative(project_root, normalized)
    if concrete.exists():
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


def score_candidate(relative_path: str, file_type: str, mentioned_paths: set[str]) -> tuple[int, str, int]:
    name = Path(relative_path).name
    parts = PurePosixPath(relative_path).parts
    if relative_path in mentioned_paths:
        return 900, "Explicitly mentioned in the current discussion.", 2
    if name in {"README.md", "AGENTS.md"}:
        return 850, "High-value project context document.", 3
    if parts and parts[0] == "docs":
        return 800, "Project documentation that frames the problem.", 3
    if file_type == "documentation":
        return 760, "Documentation that supports the current strategy discussion.", 3
    if parts and parts[0] == "src":
        return 720, "Core implementation file relevant to the topic.", 3
    if file_type == "code":
        return 680, "Code excerpt likely needed for technical grounding.", 3
    if file_type == "config":
        return 620, "Configuration that may constrain the recommended route.", 3
    if file_type == "log":
        return 520, "Log summary that captures runtime signals without shipping raw logs.", 3
    return 300, "Fallback context file selected as minimal support material.", 3


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def build_excerpt(text: str, limit: int) -> tuple[str, bool, str]:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized, False, "full_text"
    if limit <= 200:
        return normalized[:limit].rstrip() + "\n...[truncated]", True, "head_chars"
    head = int(limit * 0.7)
    tail = max(limit - head - 32, 60)
    excerpt = normalized[:head].rstrip() + "\n\n...[truncated for bundle preview]...\n\n" + normalized[-tail:].lstrip()
    return excerpt, True, f"head_tail_chars:{head}+{tail}"


def make_handoff_dir(project_root: Path, topic: str) -> tuple[str, Path]:
    base_id = f"{timestamp_for_id()}_{slugify(topic)}"
    handoff_dir = project_root / ".codex" / "handoffs" / base_id
    counter = 1
    while handoff_dir.exists():
        handoff_dir = project_root / ".codex" / "handoffs" / f"{base_id}_{counter:02d}"
        counter += 1
    handoff_dir.mkdir(parents=True, exist_ok=False)
    (handoff_dir / "attachments").mkdir(parents=True, exist_ok=True)
    return handoff_dir.name, handoff_dir


def build_brief_context(inputs: HandoffInputs, selected_files: list[SelectedFile], defaults: dict[str, Any]) -> dict[str, str]:
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
        f"本次 handoff 选入了 {len(selected_files)} 个文件作为最小必要阅读层，并保留了 attachments/ 作为备查层。",
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
        "哪些文件最值得作为主阅读层，哪些应该只留在 attachments/？",
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


def build_brief(inputs: HandoffInputs, selected_files: list[SelectedFile], defaults: dict[str, Any]) -> str:
    content = render_template("brief.template.md", build_brief_context(inputs, selected_files, defaults))
    return content.strip() + "\n"


def group_files(selected_files: list[SelectedFile]) -> dict[str, list[SelectedFile]]:
    grouped = {"documentation": [], "code": [], "config_log": [], "other": []}
    for item in selected_files:
        if item.type == "documentation":
            grouped["documentation"].append(item)
        elif item.type == "code":
            grouped["code"].append(item)
        elif item.type in {"config", "log"}:
            grouped["config_log"].append(item)
        else:
            grouped["other"].append(item)
    return grouped


def render_file_block(item: SelectedFile) -> str:
    lines = [
        f"### {item.path}",
        f"- 文件路径: `{item.path}`",
        f"- 选入原因: {item.reason}",
        f"- 原始字符数: {item.char_count_original}",
        f"- 选入字符数: {item.char_count_included}",
        f"- 截断说明: {item.truncation_method}",
        "",
    ]
    if item.included_in_bundle:
        language = guess_language(item.path)
        lines.extend([f"```{language}", item.excerpt, "```", ""])
    else:
        lines.append("- 该文件已复制到 `attachments/`，但未进入 bundle 主阅读层。")
        lines.append("")
    return "\n".join(lines)


def build_bundle(inputs: HandoffInputs, selected_files: list[SelectedFile], defaults: dict[str, Any]) -> str:
    grouped = group_files(selected_files)
    file_budget_total = max(600, inputs.max_bundle_chars - 900)
    per_file_budget = max(
        120,
        min(
            int(defaults.get("per_file_char_limit", 2800)),
            file_budget_total // max(len(selected_files), 1) - 180,
        ),
    )

    for item in selected_files:
        excerpt, truncated, method = build_excerpt(item.content, per_file_budget)
        item.excerpt = excerpt
        item.included_in_bundle = True
        item.char_count_included = len(excerpt)
        item.truncated = truncated
        item.truncation_method = method

    sections = [
        "# Handoff Bundle",
        "",
        "## 1. 项目背景",
        f"本次 handoff 聚焦于“{inputs.topic}”，模式为 `{inputs.mode}`。主阅读层坚持 minimal_sufficient_context 原则，优先保留能帮助网页版 GPT 快速进入问题空间的材料。",
        "",
        "## 2. 当前问题定义",
        clip_text(
            "；".join(inputs.focus_points) or "当前需要继续澄清问题边界、关键约束、候选路线与研究方法。",
            500,
        ),
        "",
        "## 3. 关键文档摘录",
    ]

    if grouped["documentation"]:
        sections.extend(render_file_block(item) for item in grouped["documentation"])
    else:
        sections.extend(["本次没有选入文档类主阅读材料。", ""])

    sections.append("## 4. 关键代码摘录")
    if grouped["code"]:
        sections.extend(render_file_block(item) for item in grouped["code"])
    else:
        sections.extend(["本次没有选入代码类主阅读材料。", ""])

    sections.append("## 5. 配置/日志摘要")
    if grouped["config_log"]:
        sections.extend(render_file_block(item) for item in grouped["config_log"])
    else:
        sections.extend(["本次没有选入配置或日志材料。", ""])

    sections.append("## 6. 已有想法与疑问")
    sections.append(bulletize(inputs.focus_points or inputs.questions, "需要继续补充更可靠的策略判断与研究依据。"))
    sections.append("")
    if grouped["other"]:
        sections.append("### 其他备查材料")
        sections.extend(render_file_block(item) for item in grouped["other"])

    bundle = "\n".join(sections).strip() + "\n"
    if len(bundle) <= inputs.max_bundle_chars:
        return bundle

    # If the rendered bundle is still too large, keep shortening excerpts in a stable way.
    shrink_target = max(80, int(per_file_budget * 0.7))
    for item in selected_files:
        excerpt, truncated, method = build_excerpt(item.content, shrink_target)
        item.excerpt = excerpt
        item.included_in_bundle = True
        item.char_count_included = len(excerpt)
        item.truncated = truncated
        item.truncation_method = method
    sections = [
        "# Handoff Bundle",
        "",
        "## 1. 项目背景",
        f"本次 handoff 聚焦于“{inputs.topic}”，模式为 `{inputs.mode}`。主阅读层坚持 minimal_sufficient_context 原则，优先保留最能支撑策略讨论的摘要材料。",
        "",
        "## 2. 当前问题定义",
        clip_text(
            "；".join(inputs.focus_points) or "当前需要继续澄清问题边界、关键约束、候选路线与研究方法。",
            360,
        ),
        "",
        "## 3. 关键文档摘录",
    ]
    if grouped["documentation"]:
        sections.extend(render_file_block(item) for item in grouped["documentation"])
    else:
        sections.extend(["本次没有选入文档类主阅读材料。", ""])
    sections.append("## 4. 关键代码摘录")
    if grouped["code"]:
        sections.extend(render_file_block(item) for item in grouped["code"])
    else:
        sections.extend(["本次没有选入代码类主阅读材料。", ""])
    sections.append("## 5. 配置/日志摘要")
    if grouped["config_log"]:
        sections.extend(render_file_block(item) for item in grouped["config_log"])
    else:
        sections.extend(["本次没有选入配置或日志材料。", ""])
    sections.append("## 6. 已有想法与疑问")
    sections.append(bulletize(inputs.focus_points or inputs.questions, "需要继续补充更可靠的策略判断与研究依据。"))
    sections.append("")
    return "\n".join(sections).strip() + "\n"


def build_notes(
    handoff_id: str,
    inputs: HandoffInputs,
    selected_files: list[SelectedFile],
    warnings: list[str],
) -> str:
    truncated = [item for item in selected_files if item.truncated]
    scope_decisions = bulletize(
        [
            f"主阅读层选入 {len(selected_files)} 个文件，优先保留显式指定、讨论提及和高价值上下文材料。",
            "attachments/ 中保留了选中文件的完整副本，便于后续人工补查。",
        ],
        "本次 handoff 没有额外的范围决策说明。",
    )
    truncation_notes = bulletize(
        [
            f"{item.path}: {item.truncation_method}"
            for item in truncated
        ],
        "当前主阅读层文件都未发生截断。",
    )
    excluded_notes = bulletize(
        warnings or [
            "默认排除了 data/、outputs/、依赖锁文件、大型二进制和全量日志原文。",
        ],
        "没有额外的排除说明。",
    )
    confirmation_checklist = bulletize(
        [
            "确认 brief.md 是否准确表达了策略讨论目标，而不是实现任务。",
            "确认 bundle.md 中的主阅读材料是否足够且不过量。",
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
                "scope_decisions": scope_decisions,
                "truncation_notes": truncation_notes,
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


def summarize_brief(brief_text: str, defaults: dict[str, Any]) -> str:
    limit = int(defaults.get("brief_summary_chars", 320))
    summary = re.sub(r"#+\s*", "", brief_text)
    return clip_text(summary, limit)


def select_files(
    project_root: Path,
    inputs: HandoffInputs,
    defaults: dict[str, Any],
) -> tuple[list[SelectedFile], dict[str, int], list[str]]:
    candidates, excluded_count = scan_project_files(project_root, defaults)
    warnings: list[str] = []
    mentioned = dedupe_strings(
        inputs.mentioned_paths
        + detect_mentioned_paths(
            [inputs.background, *inputs.focus_points, *inputs.questions, *inputs.known_routes, *inputs.blockers],
            candidates,
        )
    )
    exclude_matches: set[str] = set()
    for pattern in inputs.must_exclude:
        matches = resolve_pattern(pattern, project_root, candidates)
        if not matches:
            warnings.append(f"must_exclude 未匹配到任何文件：{pattern}")
        exclude_matches.update(matches)

    selected_paths: list[str] = []
    for pattern in inputs.must_include:
        matches = resolve_pattern(pattern, project_root, candidates)
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
            if relative_path not in exclude_matches and relative_path not in selected_paths and relative_path not in mentioned_matches:
                mentioned_matches.append(relative_path)

    scored_candidates: list[tuple[int, str, int, str]] = []
    for relative_path in candidates:
        if relative_path in exclude_matches or relative_path in selected_paths or relative_path in mentioned_matches:
            continue
        file_type = file_type_for_path(relative_path)
        score, reason, priority = score_candidate(relative_path, file_type, set(mentioned_matches))
        scored_candidates.append((score, relative_path, priority, reason))
    scored_candidates.sort(key=lambda item: (-item[0], item[1]))

    remaining_budget = max(inputs.max_files - len(selected_paths), 0)
    chosen_mentioned = mentioned_matches[:remaining_budget]
    remaining_after_mentioned = max(remaining_budget - len(chosen_mentioned), 0)
    auto_paths = [relative_path for _, relative_path, _, _ in scored_candidates[:remaining_after_mentioned]]
    chosen_paths = selected_paths + chosen_mentioned + auto_paths

    selections: list[SelectedFile] = []
    for relative_path in chosen_paths:
        absolute_path = candidates[relative_path]
        content = read_text_file(absolute_path)
        file_type = file_type_for_path(relative_path)
        if relative_path in selected_paths:
            reason = "User explicitly requested this file."
            priority = 1
        elif relative_path in mentioned_matches:
            reason = "The current discussion explicitly mentions this file."
            priority = 2
        else:
            _, reason, priority = score_candidate(relative_path, file_type, set(mentioned_matches))
        selections.append(
            SelectedFile(
                path=relative_path,
                absolute_path=absolute_path,
                type=file_type,
                status="selected",
                included_in_bundle=False,
                reason=reason,
                char_count_original=len(content),
                char_count_included=0,
                truncated=False,
                truncation_method="not_rendered",
                priority=priority,
                content=content,
            )
        )

    summary = {
        "total_candidate_files": len(candidates),
        "excluded_files": excluded_count + len(exclude_matches),
    }
    return selections, summary, warnings


def copy_attachments(project_root: Path, handoff_dir: Path, selected_files: list[SelectedFile]) -> None:
    attachments_root = handoff_dir / "attachments"
    for item in selected_files:
        attachment_target = attachments_root / Path(*PurePosixPath(item.path).parts)
        attachment_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item.absolute_path, attachment_target)
        item.attachment_path = to_repo_relative(attachment_target, project_root)


def create_preview_payload(
    handoff_id: str,
    manifest: dict[str, Any],
    brief_text: str,
    selected_files: list[SelectedFile],
    defaults: dict[str, Any],
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
        "brief_summary": summarize_brief(brief_text, defaults),
        "file_list_summary": [
            {
                "path": item.path,
                "type": item.type,
                "reason": item.reason,
                "truncated": item.truncated,
            }
            for item in selected_files
        ],
        "next_actions": manifest["notes"]["next_actions"],
    }


def build_preview_text(preview_payload: dict[str, Any]) -> str:
    file_lines = preview_payload.get("file_list_summary", [])
    files_text = "\n".join(
        f"- {item['path']} [{item['type']}] {'已截断' if item['truncated'] else '完整'}"
        for item in file_lines
    ) or "- 本次未选入文件"
    next_actions = "\n".join(
        f"{index}. {action}" for index, action in enumerate(preview_payload.get("next_actions", []), start=1)
    ) or "1. 需要时确认交付。"
    return (
        "Handoff 预览\n"
        f"mode: {preview_payload['mode']}\n"
        f"topic: {preview_payload['topic']}\n"
        f"handoff_id: {preview_payload['handoff_id']}\n"
        f"选入文件数: {preview_payload['selected_file_count']}\n"
        f"截断文件数: {preview_payload['truncated_file_count']}\n"
        f"排除文件数: {preview_payload['excluded_file_count']}\n\n"
        "brief 摘要:\n"
        f"{preview_payload['brief_summary']}\n\n"
        "文件清单摘要:\n"
        f"{files_text}\n\n"
        "下一步可选动作:\n"
        f"{next_actions}\n"
    )


def prepare_handoff(project_root: Path, inputs: HandoffInputs) -> dict[str, Any]:
    project_root = project_root.resolve()
    defaults = load_defaults()
    normalized_inputs = inputs.normalized()
    handoff_id, handoff_dir = make_handoff_dir(project_root, normalized_inputs.topic)
    selected_files, summary_seed, warnings = select_files(project_root, normalized_inputs, defaults)
    copy_attachments(project_root, handoff_dir, selected_files)

    brief_text = build_brief(normalized_inputs, selected_files, defaults)
    bundle_text = build_bundle(normalized_inputs, selected_files, defaults)
    notes_text = build_notes(handoff_id, normalized_inputs, selected_files, warnings)
    reply_template_text = build_reply_template(handoff_id, normalized_inputs)

    artifacts = {
        "brief_md": to_repo_relative(handoff_dir / "brief.md", project_root),
        "bundle_md": to_repo_relative(handoff_dir / "bundle.md", project_root),
        "manifest_json": to_repo_relative(handoff_dir / "manifest.json", project_root),
        "reply_template_md": to_repo_relative(handoff_dir / "reply_template.md", project_root),
        "notes_md": to_repo_relative(handoff_dir / "notes.md", project_root),
        "preview_json": to_repo_relative(handoff_dir / "preview.json", project_root),
    }

    selection_summary = {
        "total_candidate_files": summary_seed["total_candidate_files"],
        "selected_files": len(selected_files),
        "truncated_files": sum(1 for item in selected_files if item.truncated),
        "excluded_files": summary_seed["excluded_files"],
        "total_bundle_chars": len(bundle_text),
        "max_files_requested": normalized_inputs.max_files,
        "max_bundle_chars_requested": normalized_inputs.max_bundle_chars,
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
            "max_bundle_chars": normalized_inputs.max_bundle_chars,
            "background": normalized_inputs.background,
            "known_routes": normalized_inputs.known_routes,
            "blockers": normalized_inputs.blockers,
            "questions": normalized_inputs.questions,
            "avoid_directions": normalized_inputs.avoid_directions,
            "output_requirements": normalized_inputs.output_requirements,
            "mentioned_paths": normalized_inputs.mentioned_paths,
        },
        "selection_summary": selection_summary,
        "files": [item.to_manifest() for item in selected_files],
        "artifacts": artifacts,
        "notes": {
            "summary": f"已为主题“{normalized_inputs.topic}”生成 preview 状态的 handoff 包。",
            "warnings": warnings,
            "next_actions": list(defaults.get("default_next_actions", [])),
            "recommended_send_order": ["brief.md", "bundle.md", "reply_template.md"],
        },
    }

    preview_payload = create_preview_payload(handoff_id, manifest, brief_text, selected_files, defaults)

    write_text(handoff_dir / "brief.md", brief_text)
    write_text(handoff_dir / "bundle.md", bundle_text)
    write_text(handoff_dir / "reply_template.md", reply_template_text)
    write_text(handoff_dir / "notes.md", notes_text)
    write_json(handoff_dir / "manifest.json", manifest)
    write_json(handoff_dir / "preview.json", preview_payload)

    return {
        "handoff_id": handoff_id,
        "handoff_dir": handoff_dir,
        "manifest": manifest,
        "preview": preview_payload,
        "preview_text": build_preview_text(preview_payload),
    }


def resolve_handoff_dir(project_root: Path, handoff_ref: str) -> Path:
    raw = Path(handoff_ref)
    if raw.is_absolute():
        return raw
    if raw.suffix in {".json", ".md"}:
        candidate = (project_root / raw).resolve()
        return candidate.parent
    if handoff_ref.startswith(".codex/") or handoff_ref.startswith(".codex\\"):
        return (project_root / Path(*PurePosixPath(normalize_pattern(handoff_ref)).parts)).resolve()
    candidate = project_root / ".codex" / "handoffs" / handoff_ref
    if candidate.exists():
        return candidate.resolve()
    return (project_root / raw).resolve()


def load_preview(project_root: Path, handoff_ref: str) -> dict[str, Any]:
    handoff_dir = resolve_handoff_dir(project_root, handoff_ref)
    preview_path = handoff_dir / "preview.json"
    if not preview_path.exists():
        raise FileNotFoundError(f"preview.json not found in {handoff_dir}")
    return read_json(preview_path)


def render_preview(project_root: Path, handoff_ref: str) -> str:
    preview_payload = load_preview(project_root, handoff_ref)
    return build_preview_text(preview_payload)


def confirm_handoff(project_root: Path, handoff_ref: str) -> dict[str, Any]:
    handoff_dir = resolve_handoff_dir(project_root, handoff_ref)
    manifest_path = handoff_dir / "manifest.json"
    preview_path = handoff_dir / "preview.json"
    manifest = read_json(manifest_path)
    preview_payload = read_json(preview_path)

    manifest["status"] = STATUS_CONFIRMED
    manifest["confirmed_at"] = iso_now()
    manifest["notes"]["summary"] = f"已确认交付主题“{manifest['topic']}”的 handoff 包。"
    preview_payload["status"] = STATUS_CONFIRMED

    write_json(manifest_path, manifest)
    write_json(preview_path, preview_payload)

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
