from __future__ import annotations

import os
import tempfile
import asyncio
from typing import Any

from app.agents.conclusion_agent import ConclusionAgent
from app.agents.research_agent import ResearchAgent
from app.agents.revision_check_agent import RevisionCheckAgent
from app.core.settings import Settings
from app.diffing.git_like_diff import compute_git_like_hunks
from app.diffing.models import ChangePoint
from app.diffing.points import build_change_summary, merge_hunks_into_points
from app.extractors.base import DocumentExtractor
from app.core.text_normalize import text_to_lines, normalize_text_for_diff
from app.core.risk_heuristics import classify_change_kind, classify_risk_color
from app.core.risk_heuristics import extract_article_number, extract_mode


class CompareService:
    def __init__(
        self,
        *,
        extractor: DocumentExtractor,
        research_agent: ResearchAgent,
        conclusion_agent: ConclusionAgent,
        settings: Settings,
        include_debug: bool = False,
        max_parallel_points: int | None = None,
        revision_check_agent: RevisionCheckAgent | None = None,
    ) -> None:
        self._extractor = extractor
        self._research_agent = research_agent
        self._conclusion_agent = conclusion_agent
        self._settings = settings
        self._include_debug = include_debug
        self._max_parallel_points = max_parallel_points or getattr(settings, "MAX_PARALLEL_POINTS", 3)
        self._revision_check_agent = revision_check_agent

    async def compare_files(self, *, file_a_path: str, file_b_path: str) -> dict[str, Any]:
        a = await self._extractor.extract_text(file_a_path)
        b = await self._extractor.extract_text(file_b_path)

        # Pre-check: ensure documents are revisions of the same document.
        # Done before any web-search per-point.
        if self._revision_check_agent is not None:
            check = await self._revision_check_agent.run(text_a=a.text, text_b=b.text)
            if not check.get("is_same_document"):
                return {
                    "error": {
                        "code": "different_documents",
                        "message": "Файлы не выглядят как редакции одного и того же документа.",
                        "details": check,
                    },
                }

        a_text_norm = normalize_text_for_diff(a.text)
        b_text_norm = normalize_text_for_diff(b.text)

        a_lines = a_text_norm.split("\n") if a_text_norm else []
        b_lines = b_text_norm.split("\n") if b_text_norm else []

        hunks = compute_git_like_hunks(
            a_lines,
            b_lines,
            context_lines=self._settings.DIFF_UNIFIED_CONTEXT_LINES,
        )

        points = merge_hunks_into_points(
            hunks,
            merge_max_distance_lines=self._settings.POINT_MERGE_MAX_DISTANCE_LINES,
        )

        import inspect

        async def maybe_await(val: Any) -> Any:
            if inspect.isawaitable(val):
                return await val
            return val

        # Precompute UI with contradiction tracking in document order.
        # This ensures "red" marks contradictions with previously detected changes.
        mode_by_article: dict[str, str] = {}
        ui_by_index: list[dict[str, Any]] = []
        for p in points:
            change_type = classify_change_kind(p)
            local_risk_color = classify_risk_color(p)
            local_risk_label = (
                "безопасно"
                if local_risk_color == "green"
                else "требует проверки"
                if local_risk_color == "yellow"
                else "потенциальное противоречие"
            )
            article_id = extract_article_number((p.summary or "") + "\n" + (p.new_context or ""))
            curr_mode = extract_mode(p.new_context or "")

            risk_color = local_risk_color
            # Only override to red when the new change flips the modality
            # against what we've already seen for the same article.
            if article_id and curr_mode in {"obl", "pro"}:
                prev_mode = mode_by_article.get(article_id)
                if prev_mode and prev_mode != curr_mode:
                    risk_color = "red"
                    local_risk_label = "потенциальное противоречие"

            # Update state after we applied contradiction logic.
            if article_id and curr_mode in {"obl", "pro"}:
                mode_by_article[article_id] = curr_mode

            risk_label = (
                "безопасно"
                if risk_color == "green"
                else "требует проверки"
                if risk_color == "yellow"
                else "потенциальное противоречие"
            )
            ui_by_index.append(
                {
                    "change_type": change_type,
                    "risk_color": risk_color,
                    "risk_label": risk_label,
                    "risk_reason": "классифицировано эвристикой по тексту diff (с учетом противоречий между пунктами).",
                }
            )

        sem = asyncio.Semaphore(self._max_parallel_points)

        async def process_point(idx: int, point: ChangePoint) -> tuple[int, dict[str, Any]]:
            async with sem:
                ui = ui_by_index[idx]
                max_chars = getattr(self._settings, "MAX_POINT_CONTEXT_CHARS", 4000)

                def _cap(s: str | None) -> str:
                    s = (s or "").strip()
                    if len(s) <= max_chars:
                        return s
                    return s[: max_chars - 1] + "…"

                item: dict[str, Any] = {"point": point.id, "ui": ui}
                # Old/new logical block for the UI timeline
                item["old_block"] = _cap(point.old_context)
                item["new_block"] = _cap(point.new_context)
                try:
                    research = await maybe_await(self._research_agent.run(point=point))
                    conclusion = await maybe_await(self._conclusion_agent.run(point=point, research=research))
                    if isinstance(conclusion, dict):
                        conclusion = dict(conclusion)
                        conclusion.pop("ui", None)
                        item.update(conclusion)
                except Exception as e:
                    item["error"] = {"message": str(e)}
                if self._include_debug:
                    hunks_debug: list[dict[str, Any]] = []
                    for h in point.hunks:
                        hunks_debug.append(
                            {
                                "id": h.id,
                                "old_range": [h.old_start, h.old_end],
                                "new_range": [h.new_start, h.new_end],
                                "diff_unified": "\n".join(h.diff_lines[:200]),
                            }
                        )

                    item["debug"] = {
                        "summary": point.summary,
                        "old_context": point.old_context,
                        "new_context": point.new_context,
                        "hunks": hunks_debug,
                    }

                return idx, item

        tasks = [process_point(i, p) for i, p in enumerate(points)]
        results = await asyncio.gather(*tasks)
        results.sort(key=lambda x: x[0])
        analyses = [item for _, item in results]

        return {
            "file_a": {"path": file_a_path},
            "file_b": {"path": file_b_path},
            "stats": {
                "old_lines": len(a_lines),
                "new_lines": len(b_lines),
                "hunks": len(hunks),
                "points": len(points),
            },
            "points": analyses,
        }

