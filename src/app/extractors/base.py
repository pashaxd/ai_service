from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    # Optional metadata that can help diffing (e.g. pages).
    meta: dict[str, str] | None = None


class DocumentExtractor:
    async def extract_text(self, file_path: str) -> ExtractedDocument:  # pragma: no cover
        raise NotImplementedError

