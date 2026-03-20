from __future__ import annotations

import re

from app.diffing.models import ChangePoint


def classify_change_kind(point: ChangePoint) -> str:
    """
    Returns UI-friendly change kind:
    - semantic
    - structural
    - addition
    - removal
    """
    old_empty = not (point.old_context or "").strip()
    new_empty = not (point.new_context or "").strip()
    if old_empty and not new_empty:
        return "addition"
    if new_empty and not old_empty:
        return "removal"

    # If old/new are almost the same but moved in structure,
    # classify as structural move.
    def _norm(s: str) -> str:
        return " ".join((s or "").replace("\n", " ").split()).lower()

    old_n = _norm(point.old_context or "")
    new_n = _norm(point.new_context or "")
    if old_n and new_n:
        from difflib import SequenceMatcher

        old_n2 = old_n[:700]
        new_n2 = new_n[:700]
        if SequenceMatcher(None, old_n2, new_n2).ratio() >= 0.88:
            return "structural"

    text = new_n + "\n" + old_n
    # Structural hints in typical legal texts.
    if re.search(r"\b(раздел|пункт|глава|приложение|перенесен|перенес|исключен)\b", text, re.I):
        return "structural"
    return "semantic"


def _negation_toggle(old: str, new: str) -> bool:
    old_has_not = bool(re.search(r"\bне\b", old, re.I))
    new_has_not = bool(re.search(r"\bне\b", new, re.I))
    return old_has_not != new_has_not


def classify_risk_color(point: ChangePoint) -> str:
    """
    Heuristic mapping for UI.
    - green: likely safe / minor wording changes
    - yellow: requires manual check
    - red: potential conflict (e.g., negation/exception toggles)
    """
    old = point.old_context or ""
    new = point.new_context or ""

    old_empty = not old.strip()
    new_empty = not new.strip()
    if old_empty and not new_empty:
        return "green"
    if new_empty and not old_empty:
        return "yellow"

    # Red is reserved for clearer "conflict"/"restriction flip" patterns.
    # Many legal rewrites contain "не" as part of the style, so we avoid marking everything as red.
    # RED should represent meaningful contradiction / conflict (flip of allowed/forbidden).
    # We treat as red only when negation/exception patterns flip together with
    # an obligation/prohibition modality.
    modality_kw = r"(обязан|должен|подлежит|вправе|запрещ|не допуска|не может|не вправе)"
    neg_flip = _negation_toggle(old, new)
    if neg_flip:
        old_has_mod = bool(re.search(modality_kw, old, re.I))
        new_has_mod = bool(re.search(modality_kw, new, re.I))
        if (old_has_mod and new_has_mod) or (old_has_mod or new_has_mod):
            # If both sides mention modality and negation changed => potential contradiction.
            return "red"

    # Explicit conflict indicators.
    if re.search(r"\b(не предусмотрено|не предусмотрены|не допускается|запрещено|запрещается)\b", new, re.I):
        return "red"

    # "Без каких-либо исключений" is stricter but not necessarily contradiction.
    if re.search(r"\bбез каких-либо исключений\b", new, re.I):
        return "yellow"

    # "Structural-ish" changes are often less dangerous than semantic, but still check.
    kind = classify_change_kind(point)
    if kind == "structural":
        return "yellow"
    # Semantic change without obvious conflicts => safer.
    return "green"


def extract_article_number(text: str) -> str | None:
    """
    Extracts the first "Статья <num>" occurrence.
    """
    if not text:
        return None
    m = re.search(r"\bСтатья\s+(\d+)\b", text, flags=re.IGNORECASE)
    return m.group(1) if m else None


def extract_mode(text: str) -> str:
    """
    Best-effort modality extraction for contradiction tracking.
    Returns:
      - "obl" (obligation / must)
      - "pro" (prohibition / cannot / forbidden)
      - "unknown" (no signal)
    """
    if not text:
        return "unknown"
    t = text.lower()

    pro_kw = [
        "запрещ",
        "не допуска",
        "не вправ",
        "не может",
        "нельзя",
        "не имеет права",
        "запрещается",
        "противореч",  # sometimes used as conflict signal
    ]
    obl_kw = [
        "обязан",
        "должен",
        "подлежит",
        "необходимо",
        "требуется",
        "вправе",  # could be permissive, not obligation; still treat as non-prohibitive signal
    ]

    if any(k in t for k in pro_kw):
        return "pro"
    if any(k in t for k in obl_kw):
        return "obl"
    return "unknown"

