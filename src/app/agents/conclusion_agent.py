from __future__ import annotations

import json
from typing import Any

from app.clients.polza_client import PolzaChatClient
from app.core.settings import Settings
from app.diffing.models import ChangePoint


def _try_parse_json(s: str) -> dict[str, Any] | None:
    try:
        return json.loads(s)
    except Exception:
        return None


class ConclusionAgent:
    def __init__(self, *, polza: PolzaChatClient, settings: Settings) -> None:
        self._polza = polza
        self._settings = settings

    async def run(
        self,
        *,
        point: ChangePoint,
        research: dict[str, Any],
    ) -> dict[str, Any]:
        system = "Ты юридический аналитик. Делай выводы строго по предоставленным источникам."
        sources = research.get("sources") or []

        old_ctx = (point.old_context or "").strip()
        new_ctx = (point.new_context or "").strip()
        if len(old_ctx) > 2500:
            old_ctx = old_ctx[:2500] + "…"
        if len(new_ctx) > 2500:
            new_ctx = new_ctx[:2500] + "…"

        user = "\n".join(
            [
                "У тебя есть изменение в документе и результаты веб-исследования.",
                "",
                "Изменение (summary):",
                point.summary,
                "",
                "Контекст old/new:",
                f"old:\n{old_ctx or '(пусто)'}",
                "",
                f"new:\n{new_ctx or '(пусто)'}",
                "",
                "Источники (sources, 2-3 шт, только url/title). По каждому источнику сделай анализ:",
                json.dumps(sources, ensure_ascii=False),
                "",
                "Сгенерируй итог ТОЛЬКО в JSON без Markdown:",
                "{",
                '  "change_summary": "кратко что изменилось",',
                '  "legal_interpretation": "как это влияет/что означает",',
                '  "recommended_actions": ["что делать"],',
                '  "confidence": 1-5,',
                '  "sources": [{"url":"...","title":"...","what_the_source_says":"...","how_related_to_change":"...","contradiction_signal":"green|yellow|red"}]',
                "}",
            ]
        )

        result = await self._polza.chat_completions(
            model=self._settings.LLM_MODEL_ANALYSIS,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=900,
        )

        parsed = _try_parse_json(result.content.strip())
        if parsed is None:
            return {
                "change_summary": point.summary,
                "legal_interpretation": result.content,
                "recommended_actions": [],
                "confidence": 2,
                "sources": sources,
            }

        parsed.setdefault("recommended_actions", [])
        parsed.setdefault("confidence", 2)
        parsed.setdefault("sources", sources)

        # Enforce stable sources contract:
        # - URL/title must stay exactly as provided by ResearchAgent (no invention).
        # - model can only fill analysis fields.
        sources_in = (sources or [])[:3]
        model_sources = (parsed.get("sources") or [])[:3]

        normalized_sources: list[dict[str, Any]] = []
        for idx, src_in in enumerate(sources_in):
            src_in = src_in if isinstance(src_in, dict) else {}
            model_src = model_sources[idx] if idx < len(model_sources) else {}
            model_src = model_src if isinstance(model_src, dict) else {}
            normalized_sources.append(
                {
                    "url": str(src_in.get("url") or ""),
                    "title": str(src_in.get("title") or ""),
                    "what_the_source_says": str(model_src.get("what_the_source_says") or ""),
                    "how_related_to_change": str(model_src.get("how_related_to_change") or ""),
                    "contradiction_signal": str(model_src.get("contradiction_signal") or "yellow"),
                }
            )

        parsed["sources"] = normalized_sources
        return parsed

