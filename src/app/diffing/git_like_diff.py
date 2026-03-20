from __future__ import annotations

import re
from difflib import unified_diff
from typing import Iterable

from .models import DiffHunk


_HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


def _parse_count(val: str | None) -> int:
    return int(val) if val is not None else 1


def compute_git_like_hunks(
    old_lines: list[str],
    new_lines: list[str],
    *,
    context_lines: int = 3,
) -> list[DiffHunk]:
    """
    Compute git-like unified diff hunks for two sequences of lines.

    We rely on `difflib.unified_diff`, then parse it into structured hunks.
    """
    diff_iter = unified_diff(
        old_lines,
        new_lines,
        fromfile="a",
        tofile="b",
        n=context_lines,
        lineterm="",
    )

    hunks: list[DiffHunk] = []
    current: list[str] | None = None
    old_start = old_end = new_start = new_end = 0
    old_payload: list[str] = []
    new_payload: list[str] = []
    diff_lines: list[str] = []

    def flush():
        nonlocal current, old_start, old_end, new_start, new_end, old_payload, new_payload, diff_lines
        if current is None:
            return
        hunk_id = f"hunk_{len(hunks)}"
        hunks.append(
            DiffHunk(
                id=hunk_id,
                old_start=old_start,
                old_end=old_end,
                new_start=new_start,
                new_end=new_end,
                diff_lines=tuple(diff_lines),
                old_lines=tuple(old_payload),
                new_lines=tuple(new_payload),
            )
        )
        current = None
        old_start = old_end = new_start = new_end = 0
        old_payload = []
        new_payload = []
        diff_lines = []

    for line in diff_iter:
        # headers (---, +++, @@ ...)
        if line.startswith("@@ "):
            flush()
            m = _HUNK_HEADER_RE.match(line)
            if not m:
                # Unexpected format; skip.
                continue
            current = [line]
            old_start = int(m.group("old_start"))
            old_count = _parse_count(m.group("old_count"))
            new_start = int(m.group("new_start"))
            new_count = _parse_count(m.group("new_count"))
            old_end = old_start + old_count - 1
            new_end = new_start + new_count - 1
            diff_lines.append(line)
            continue

        if line.startswith("---") or line.startswith("+++"):
            continue

        if current is None:
            continue

        current.append(line)
        diff_lines.append(line)
        if not line:
            continue
        prefix = line[0]
        payload = line[1:]
        if prefix == "-":
            old_payload.append(payload)
        elif prefix == "+":
            new_payload.append(payload)

    flush()
    return hunks

