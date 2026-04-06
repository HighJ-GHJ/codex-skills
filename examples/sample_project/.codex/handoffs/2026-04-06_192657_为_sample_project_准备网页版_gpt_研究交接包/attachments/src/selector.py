from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candidate:
    path: str
    priority: int
    reason: str


def rank_candidates(paths: list[str]) -> list[Candidate]:
    ranked: list[Candidate] = []
    for path in paths:
        if path.endswith(".md"):
            ranked.append(Candidate(path=path, priority=1, reason="Documentation explains project context."))
        elif path.endswith(".py"):
            ranked.append(Candidate(path=path, priority=2, reason="Code shows the current implementation shape."))
        elif path.endswith(".log"):
            ranked.append(Candidate(path=path, priority=3, reason="Log summary captures recent signals."))
        else:
            ranked.append(Candidate(path=path, priority=4, reason="Fallback context."))
    return sorted(ranked, key=lambda item: (item.priority, item.path))
