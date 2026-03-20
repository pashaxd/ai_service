from __future__ import annotations

import argparse
import json
import os
import sys

from app.agents.conclusion_agent import ConclusionAgent
from app.agents.research_agent import ResearchAgent
from app.agents.revision_check_agent import RevisionCheckAgent
from app.clients.polza_client import PolzaChatClient
from app.core.compare_service import CompareService
from app.core.settings import settings
from app.extractors.docx_pdf_extractor import DocxPdfExtractor


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare two DOCX/PDF revisions and output JSON diff analysis.")
    p.add_argument("--file-a", required=True, help="Path to old revision (.docx/.pdf)")
    p.add_argument("--file-b", required=True, help="Path to new revision (.docx/.pdf)")
    p.add_argument(
        "--out",
        default=None,
        help="Optional output file path (if not set, prints to stdout).",
    )
    p.add_argument(
        "--run-agents",
        action="store_true",
        default=False,
        help="If set, will call Polza LLM and do web search; requires POLZA_API_KEY.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    extractor = DocxPdfExtractor()

    polza_key = settings.POLZA_API_KEY or os.getenv("POLZA_API_KEY")
    if args.run_agents:
        if not polza_key:
            raise SystemExit("POLZA_API_KEY is required when --run-agents is set.")
        polza = PolzaChatClient(api_key=polza_key, base_url=settings.POLZA_BASE_URL)
        research_agent = ResearchAgent(polza=polza, settings=settings)
        conclusion_agent = ConclusionAgent(polza=polza, settings=settings)
        revision_check_agent = RevisionCheckAgent(polza=polza, settings=settings)
        compare_service = CompareService(
            extractor=extractor,
            research_agent=research_agent,
            conclusion_agent=conclusion_agent,
            settings=settings,
            include_debug=False,
            revision_check_agent=revision_check_agent,
        )
        out_json = _run(compare_service, args.file_a, args.file_b)
    else:
        # "Diff-only" mode: we still produce points, but agents are not executed.
        # Minimal mock agents for deterministic output without network calls.
        class _NoopResearch:
            def run(self, *, point):  # type: ignore[no-untyped-def]
                return {"point_id": point.id, "sources": []}

        class _NoopConclusion:
            def run(self, *, point, research):  # type: ignore[no-untyped-def]
                return {
                    "change_summary": point.summary,
                    "legal_interpretation": None,
                    "recommended_actions": [],
                    "confidence": 0,
                    "sources": [],
                }

        compare_service = CompareService(
            extractor=extractor,
            research_agent=_NoopResearch(),  # type: ignore[arg-type]
            conclusion_agent=_NoopConclusion(),  # type: ignore[arg-type]
            settings=settings,
            include_debug=False,
            revision_check_agent=None,
        )
        out_json = _run(compare_service, args.file_a, args.file_b)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out_json, f, ensure_ascii=False, indent=2)
        print(f"Saved: {args.out}")
    else:
        print(json.dumps(out_json, ensure_ascii=False, indent=2))


def _run(compare_service: CompareService, file_a: str, file_b: str) -> dict:
    # CompareService is async; we run it synchronously for CLI.
    import asyncio

    return asyncio.run(compare_service.compare_files(file_a_path=file_a, file_b_path=file_b))


if __name__ == "__main__":
    main()

