from __future__ import annotations

from typing import Iterable

from difflib import SequenceMatcher

from .models import ChangePoint, DiffHunk


def _truncate(s: str, max_len: int) -> str:
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def build_change_summary(hunks: list[DiffHunk], *, max_len: int = 400) -> str:
    removed = []
    added = []
    for h in hunks:
        removed.extend(h.old_lines[:3])
        added.extend(h.new_lines[:3])
    removed_s = " / ".join(r for r in removed if r.strip())
    added_s = " / ".join(a for a in added if a.strip())
    parts: list[str] = []
    if removed_s:
        parts.append(f"Removed: {_truncate(removed_s, 160)}")
    if added_s:
        parts.append(f"Added: {_truncate(added_s, 160)}")
    s = "; ".join(parts) if parts else "Content changed"
    return _truncate(s, max_len)


def merge_hunks_into_points(
    hunks: list[DiffHunk],
    *,
    merge_max_distance_lines: int = 6,
) -> list[ChangePoint]:
    """
    Merge nearby hunks into "points" that will be processed by agents.

    Heuristic:
    - If current hunk is close to previous hunk in both old and new coordinates,
      they likely belong to the same change region.
    """
    if not hunks:
        return []

    points: list[ChangePoint] = []
    cur: list[DiffHunk] = [hunks[0]]

    def extract_article_id(h: DiffHunk) -> str | None:
        """
        Heuristic: detects "Статья <num>" in unified diff context.
        We use it to avoid merging changes from different articles into one point.
        """
        import re

        re_article = re.compile(r"^\s*Статья\s+(\d+)\b", re.IGNORECASE)
        for dl in h.diff_lines:
            # dl may start with diff prefix: " ", "+", "-"
            line = dl[1:] if dl[:1] in {" ", "+", "-"} else dl
            if not line:
                continue
            m = re_article.match(line.strip())
            if m:
                return m.group(1)
        return None

    def old_gap(prev: DiffHunk, nxt: DiffHunk) -> int:
        return max(0, (nxt.old_start - prev.old_end - 1))

    def new_gap(prev: DiffHunk, nxt: DiffHunk) -> int:
        return max(0, (nxt.new_start - prev.new_end - 1))

    for h in hunks[1:]:
        prev = cur[-1]
        prev_article = extract_article_id(prev)
        next_article = extract_article_id(h)
        same_article = (
            prev_article is None
            or next_article is None
            or (prev_article == next_article)
        )

        if (
            same_article
            and old_gap(prev, h) <= merge_max_distance_lines
            and new_gap(prev, h) <= merge_max_distance_lines
        ):
            cur.append(h)
            continue

        points.append(_make_point(cur, idx=len(points)))
        cur = [h]

    points.append(_make_point(cur, idx=len(points)))
    return _merge_moved_points(points)


def _normalize_for_similarity(s: str) -> str:
    s = s or ""
    s = " ".join(s.replace("\n", " ").split())
    return s.lower()


def _similarity(a: str, b: str) -> float:
    a_n = _normalize_for_similarity(a)
    b_n = _normalize_for_similarity(b)
    if not a_n or not b_n:
        return 0.0
    # Compare only prefix to reduce noise/length.
    a_n = a_n[:500]
    b_n = b_n[:500]
    return SequenceMatcher(None, a_n, b_n).ratio()


def _merge_moved_points(
    points: list[ChangePoint],
    *,
    similarity_threshold: float = 0.88,
    max_distance_between_points: int = 3,
) -> list[ChangePoint]:
    """
    If a point is removed and another is added right after it with very similar text,
    treat it as the same "moved" change (structural move) instead of two separate points.
    """
    if not points:
        return points

    # Identify "removal" vs "addition" points by presence of old/new contexts.
    kinds: list[str] = []
    for p in points:
        old_empty = not (p.old_context or "").strip()
        new_empty = not (p.new_context or "").strip()
        if old_empty and not new_empty:
            kinds.append("addition")
        elif new_empty and not old_empty:
            kinds.append("removal")
        else:
            kinds.append("other")

    used = [False] * len(points)
    out: list[ChangePoint] = []
    move_idx = 0

    for i, p in enumerate(points):
        if used[i]:
            continue
        if kinds[i] != "removal":
            out.append(p)
            used[i] = True
            continue

        best_j: int | None = None
        best_sim = 0.0
        for j in range(i + 1, min(len(points), i + 1 + max_distance_between_points + 1)):
            if used[j]:
                continue
            if kinds[j] != "addition":
                continue
            sim = _similarity(p.old_context or "", points[j].new_context or "")
            if sim > best_sim:
                best_sim = sim
                best_j = j

        if best_j is not None and best_sim >= similarity_threshold:
            q = points[best_j]
            used[i] = True
            used[best_j] = True
            combined_hunks = tuple(list(p.hunks) + list(q.hunks))
            # Make new point have both old/new contexts (for "structural" classification).
            new_point = ChangePoint(
                id=f"move_{move_idx}",
                hunks=combined_hunks,
                summary=f"Moved: {(_normalize_for_similarity(q.new_context or '')[:120] or 'content changed')}",
                old_context=p.old_context,
                new_context=q.new_context,
            )
            move_idx += 1
            out.append(new_point)
        else:
            out.append(p)
            used[i] = True

    return out


def _make_point(hunks: list[DiffHunk], *, idx: int) -> ChangePoint:
    # Build prompt-friendly contexts.
    old_context = "\n".join([ln for h in hunks for ln in h.old_lines[:20] if ln.strip()]).strip()
    new_context = "\n".join([ln for h in hunks for ln in h.new_lines[:20] if ln.strip()]).strip()
    summary = build_change_summary(hunks)
    point_id = f"point_{idx}"
    return ChangePoint(
        id=point_id,
        hunks=tuple(hunks),
        summary=summary,
        old_context=old_context,
        new_context=new_context,
    )

