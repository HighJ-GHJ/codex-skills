from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HandoffState:
    status: str
    recommended_send_order: tuple[str, ...]


def build_preview_state() -> HandoffState:
    return HandoffState(
        status="preview",
        recommended_send_order=("brief.md", "bundle.md", "reply_template.md"),
    )


def confirm_state(state: HandoffState) -> HandoffState:
    return HandoffState(
        status="confirmed",
        recommended_send_order=state.recommended_send_order,
    )
