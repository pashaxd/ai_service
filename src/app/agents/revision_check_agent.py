from __future__ import annotations

import json
import re
from typing import Any

from app.clients.polza_client import PolzaChatClient
from app.core.settings import Settings


def _try_parse_json(s: str) -> dict[str, Any] | None:
    try:
        return json.loads(s)
    except Exception:
        return None


def _extract_article_numbers(text: str, limit: int = 12) -> list[str]:
    nums: list[str] = []
    for m in re.finditer(r"\bСтатья\s+(\d+)\b", text, flags=re.IGNORECASE):
        nums.append(m.group(1))
        if len(nums) >= limit:
            break
    return nums


def _build_fingerprint(text: str) -> dict[str, Any]:
    t = text or ""
    head = t[:2500]
    # A few generic legal doc title markers.
    title_line = ""
    for ln in head.splitlines():
        ln2 = ln.strip()
        if not ln2:
            continue
        if re.search(r"\b(договор|соглашение|закон|кодекс|положение)\b", ln2, flags=re.IGNORECASE):
            title_line = ln2[:180]
            break
    return {
        "title_line": title_line,
        "first_1200": head[:1200],
        "article_numbers": _extract_article_numbers(t),
    }


class RevisionCheckAgent:
    """
    Checks if A and B are revisions of the same document (one updated version),
    or two unrelated documents.
    """

    def __init__(self, *, polza: PolzaChatClient, settings: Settings) -> None:
        self._polza = polza
        self._settings = settings

    async def run(self, *, text_a: str, text_b: str) -> dict[str, Any]:
        fp_a = _build_fingerprint(text_a)
        fp_b = _build_fingerprint(text_b)

        system = "Ты эксперт по идентификации редакций юридических документов."
        user = "\n".join(
            [
                "Определи, являются ли два текста редакциями ОДНОГО и того же юридического документа",
                "или это два разных документа (разные предмет/структура/статьи).",
                "",
                "TEXT_A fingerprint (JSON):",
                json.dumps(fp_a, ensure_ascii=False),
                "",
                "TEXT_B fingerprint (JSON):",
                json.dumps(fp_b, ensure_ascii=False),
                "",
                "Верни ТОЛЬКО JSON со схемой:",
                "{",
                '  "is_same_document": true|false,',
                '  "confidence": 1-5,',
                '  "reason": "почему так решил",',
                '  "common_signals": ["что совпадает"],',
                '  "differences": ["что различается"]',
                "}",
            ]
        )

        result = await self._polza.chat_completions(
            model=self._settings.LLM_MODEL_ANALYSIS,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.1,
            max_tokens=500,
        )

        parsed = _try_parse_json(result.content.strip())
        if not parsed:
            # Safe default: if we can't decide, treat as same to avoid blocking.
            return {
                "is_same_document": True,
                "confidence": 2,
                "reason": "не удалось распарсить ответ; принята безопасная стратегия = считаем редакциями",
                "common_signals": [],
                "differences": [],
            }

        parsed.setdefault("common_signals", [])
        parsed.setdefault("differences", [])
        parsed.setdefault("confidence", 2)
        parsed.setdefault("reason", "")
        return parsed

