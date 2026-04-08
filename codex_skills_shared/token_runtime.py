"""中文说明：跨 skill 共用的 token runtime 契约。

这里承接精确 token 与保守估算两条路径的统一实现，避免每个 skill 复制
`tiktoken` 检测、fallback 原因记录和 strict-exact 失败语义。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

try:
    import tiktoken as DEFAULT_TIKTOKEN
except ImportError:  # pragma: no cover - exercised via fallback tests
    DEFAULT_TIKTOKEN = None


_UNSET = object()


class ExactTokenUnavailableError(RuntimeError):
    """中文说明：当 strict-exact 模式要求精确 token 但运行时无法提供时抛出。"""


@dataclass(frozen=True)
class TokenRuntime:
    """中文说明：统一承载本次运行的 token 计数契约。"""

    counter: "TokenCounter"
    exact_requested: bool
    exact_available: bool
    resolved_method: str
    fallback_reason: str


class TokenCounter:
    """中文说明：统一的 token 计数与切片器。

    具体使用 exact 还是 fallback，不在这里自行决定，而是由上层工厂函数统一
    构造，避免不同入口各自尝试 `tiktoken.get_encoding(...)`。
    """

    def __init__(self, encoding_name: str, fallback_method: str, encoding: object | None = None) -> None:
        self.encoding_name = encoding_name
        self.fallback_method = fallback_method
        self._encoding = encoding

    @property
    def method_name(self) -> str:
        if self._encoding is not None:
            return f"tiktoken:{self.encoding_name}"
        return f"estimated:{self.fallback_method}"

    @property
    def is_estimated(self) -> bool:
        return self._encoding is None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoding is not None:
            return len(self._encoding.encode(text))
        return self._estimate_tokens(text)

    def slice_head(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0 or not text:
            return ""
        if self._encoding is not None:
            return self._encoding.decode(self._encoding.encode(text)[:max_tokens])
        return self._slice_estimated(text, max_tokens, from_end=False)

    def slice_tail(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0 or not text:
            return ""
        if self._encoding is not None:
            return self._encoding.decode(self._encoding.encode(text)[-max_tokens:])
        return self._slice_estimated(text, max_tokens, from_end=True)

    def _estimate_tokens(self, text: str) -> int:
        quarter_tokens = sum(1 if char.isascii() else 4 for char in text)
        return math.ceil(quarter_tokens / 4)

    def _slice_estimated(self, text: str, max_tokens: int, *, from_end: bool) -> str:
        budget = max_tokens * 4
        units = 0
        chars: list[str] = []
        source = reversed(text) if from_end else text
        for char in source:
            weight = 1 if char.isascii() else 4
            if units + weight > budget:
                break
            chars.append(char)
            units += weight
        if from_end:
            chars.reverse()
        return "".join(chars)


def build_token_runtime(
    defaults: object,
    require_exact_tokens: bool = False,
    *,
    tiktoken_module: object | None = _UNSET,
) -> TokenRuntime:
    """中文说明：构造单一 token runtime 契约，并显式记录 fallback 原因。"""

    if tiktoken_module is _UNSET:
        tiktoken_module = DEFAULT_TIKTOKEN

    encoding = None
    fallback_reason = ""
    if tiktoken_module is None:
        fallback_reason = "tiktoken_not_installed"
    else:
        try:
            encoding = tiktoken_module.get_encoding(defaults.tokenizer_encoding)
        except Exception as exc:  # pragma: no cover - exact failure path depends on runtime/cache
            fallback_reason = f"get_encoding_failed:{exc.__class__.__name__}"

    exact_available = encoding is not None
    counter = TokenCounter(defaults.tokenizer_encoding, defaults.fallback_token_count_method, encoding=encoding)
    if require_exact_tokens and not exact_available:
        raise ExactTokenUnavailableError(
            f"Exact token counting required but unavailable: {fallback_reason or 'unknown_reason'}"
        )
    return TokenRuntime(
        counter=counter,
        exact_requested=require_exact_tokens,
        exact_available=exact_available,
        resolved_method=counter.method_name,
        fallback_reason=fallback_reason,
    )


def build_token_counter(
    defaults: object,
    require_exact_tokens: bool = False,
    *,
    tiktoken_module: object | None = _UNSET,
) -> TokenCounter:
    """中文说明：兼容旧接口，内部统一委托给 token runtime 工厂。"""

    return build_token_runtime(
        defaults,
        require_exact_tokens=require_exact_tokens,
        tiktoken_module=tiktoken_module,
    ).counter
