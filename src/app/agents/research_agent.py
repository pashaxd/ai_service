from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.settings import Settings
from app.clients.polza_client import PolzaChatClient
from app.diffing.models import ChangePoint


def _try_parse_json(s: str) -> dict[str, Any] | None:
    import json

    try:
        return json.loads(s)
    except Exception:
        return None


def _extract_url_citations(annotations: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for ann in annotations or []:
        if ann.get("type") != "url_citation":
            continue
        url_c = ann.get("url_citation") or {}
        url = url_c.get("url")
        title = url_c.get("title") or ""
        content = url_c.get("content") or ""
        if url:
            # content may be absent for some search engines.
            out.append({"url": str(url), "title": str(title), "content": str(content)})
    # De-dupe by URL (stable order)
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for s in out:
        if s["url"] in seen:
            continue
        seen.add(s["url"])
        deduped.append(s)
    return deduped


def _is_allowed_url(url: str) -> bool:
    # User requirement: web-search should be about pravo.by.
    # Some engines can still return off-domain results; filter them out.
    u = (url or "").lower()
    return "pravo.by" in u


def _build_search_prompt(point: ChangePoint) -> str:
    # Hard-restrict to pravo.by via query.
    # Keeping it short improves search relevance.
    return f"site:pravo.by {point.summary}"


class ResearchAgent:
    def __init__(self, *, polza: PolzaChatClient, settings: Settings) -> None:
        self._polza = polza
        self._settings = settings

    async def run(self, *, point: ChangePoint) -> dict[str, Any]:
        search_prompt = _build_search_prompt(point)
        system = "Ты аналитик правовой информации. Используй источники с веб-поиска и давай факты с привязкой к изменениям."

        # PDF extraction can produce very noisy/long contexts; limit prompt size.
        old_ctx = (point.old_context or "").strip()
        new_ctx = (point.new_context or "").strip()
        if len(old_ctx) > 2500:
            old_ctx = old_ctx[:2500] + "…"
        if len(new_ctx) > 2500:
            new_ctx = new_ctx[:2500] + "…"

        user = "\n".join(
            [
                "Нужно проанализировать изменение в правовом/регуляторном контексте.",
                "Изменяемый фрагмент (old):",
                old_ctx or "(пусто)",
                "",
                "Изменяемый фрагмент (new):",
                new_ctx or "(пусто)",
                "",
                f"Кратко, что поменялось: {point.summary}",
                "Задачи:",
                "1) Найди на pravo.by документы/упоминания, которые относятся к этим изменениям.",
                "2) Выпиши 3-7 ключевых фактов по сути изменений и что именно подтверждают источники.",
                "3) В конце перечисли 3-5 ссылок (URL) на источники, которые реально подтверждают факты.",
                "",
                "Формат ответа: обычный текст (без JSON).",
            ]
        )

        result = await self._polza.chat_completions(
            model=self._settings.WEB_SEARCH_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            plugins=[
                {
                    "id": "web",
                    "max_results": self._settings.WEB_SEARCH_MAX_RESULTS,
                    "search_prompt": search_prompt,
                }
            ],
            temperature=0.2,
            max_tokens=1000,
        )

        citations = _extract_url_citations(result.annotations)

        # Keep only pravo.by sources.
        citations = [c for c in citations if _is_allowed_url(c.get("url", "")) or _is_allowed_url(str(c.get("url", "")))]

        # Keep only 2-3 sources for the UI to reduce tokens downstream.
        citations = citations[:3]

        # If we have no structured citations, return empty.
        if not citations:
            return {"point_id": point.id, "sources": []}

        # Return only url/title. Per-source analysis is done in ConclusionAgent
        # together with the final JSON (one call per point).
        sources = [{"url": s["url"], "title": s.get("title", "")} for s in citations]
        return {"point_id": point.id, "sources": sources}

