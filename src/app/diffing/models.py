from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiffHunk:
    id: str
    old_start: int  # 1-based
    old_end: int  # inclusive, 1-based
    new_start: int  # 1-based
    new_end: int  # inclusive, 1-based
    # Unified diff lines for readability/debugging.
    diff_lines: tuple[str, ...]
    # Extracted payload lines (without diff prefixes).
    old_lines: tuple[str, ...]
    new_lines: tuple[str, ...]


@dataclass(frozen=True)
class ChangePoint:
    id: str
    hunks: tuple[DiffHunk, ...]
    # Concise "what changed" label used as prompt seed for research/conclusion.
    summary: str
    old_context: str
    new_context: str

