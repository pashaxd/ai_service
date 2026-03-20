from __future__ import annotations

import os
from typing import Any

from app.core.settings import Settings

from .base import DocumentExtractor, ExtractedDocument


class TikaExtractor(DocumentExtractor):
    """
    Extracts plain text from DOCX/PDF using Apache Tika.

    Notes:
    - Requires Java / Tika runtime in the environment.
    - For production, you may want to run an external tika-server and configure `tika_server_url`
      (tika-python supports this via env vars).
    """

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    async def extract_text(self, file_path: str) -> ExtractedDocument:
        # tika is sync; we keep async signature for a uniform pipeline.
        # Important: some tika-python configuration values are read at import time,
        # so we configure env vars BEFORE importing parser.
        if self._settings.TIKA_SERVER_JAR:
            os.environ["TIKA_SERVER_JAR"] = self._settings.TIKA_SERVER_JAR
        if self._settings.TIKA_PATH:
            os.environ["TIKA_PATH"] = self._settings.TIKA_PATH
        if self._settings.TIKA_SERVER_ENDPOINT:
            os.environ["TIKA_SERVER_ENDPOINT"] = self._settings.TIKA_SERVER_ENDPOINT
        if self._settings.TIKA_CLIENT_ONLY:
            os.environ["TIKA_CLIENT_ONLY"] = "True"

        # Late import to apply env configuration.
        from tika import parser  # type: ignore

        parsed: dict[str, Any] = parser.from_file(file_path)
        text = (parsed.get("content") or "").strip()
        # Tika sometimes includes page separators as form feed.
        meta = {}
        if "\f" in text:
            meta["has_form_feed_pages"] = "true"
        return ExtractedDocument(text=text, meta=meta)

