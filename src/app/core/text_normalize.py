from __future__ import annotations

import re


_RE_WHITESPACE = re.compile(r"[ \t]+")
_RE_NEWLINES = re.compile(r"\r\n|\r|\n")


def normalize_text_for_diff(text: str) -> str:
    """
    Normalize extracted text to improve diff quality across DOCX/PDF extraction quirks.
    The goal is stable, line-based diffs.
    """
    text = text or ""
    text = _RE_NEWLINES.sub("\n", text)
    # Remove common boilerplate artifacts.
    text = text.replace("\u00a0", " ")
    # Collapse horizontal whitespace.
    text = _RE_WHITESPACE.sub(" ", text)
    # Trim each line.
    lines = [ln.strip() for ln in text.split("\n")]
    # Drop empty lines bursts.
    out: list[str] = []
    empty_run = 0
    for ln in lines:
        if ln == "":
            empty_run += 1
            # Keep at most one blank line for stable diffs.
            if empty_run <= 1:
                out.append("")
        else:
            empty_run = 0
            out.append(ln)
    # Avoid trailing empties.
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def text_to_lines(text: str) -> list[str]:
    text = normalize_text_for_diff(text)
    return text.split("\n") if text else []

