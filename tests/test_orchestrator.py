import pytest

from app.core.compare_service import CompareService
from app.diffing.models import ChangePoint, DiffHunk
from app.agents.revision_check_agent import RevisionCheckAgent


class FakeExtractor:
    async def extract_text(self, file_path: str):
        if "a" in file_path:
            return type("X", (), {"text": "alpha\nbeta\ngamma"})()
        return type("X", (), {"text": "alpha\nBETA\ngamma\ndelta"})()


class FakeResearchAgent:
    def run(self, *, point: ChangePoint):
        return {
            "point_id": point.id,
            "sources": [
                {
                    "url": "https://example.com",
                    "title": "Example",
                    "what_the_source_says": "example snippet",
                    "how_related_to_change": "supports change",
                    "contradiction_signal": "yellow",
                }
            ],
        }


class FakeConclusionAgent:
    def run(self, *, point: ChangePoint, research: dict):
        return {
            "change_summary": point.summary,
            "legal_interpretation": "interp",
            "recommended_actions": ["do something"],
            "confidence": 3,
            "sources": research.get("sources") or [],
        }


@pytest.mark.asyncio
async def test_compare_service_end_to_end_points_shape():
    from app.core.settings import settings as real_settings

    # Make it deterministic and fast.
    real_settings.DIFF_UNIFIED_CONTEXT_LINES = 1
    real_settings.POINT_MERGE_MAX_DISTANCE_LINES = 6

    svc = CompareService(
        extractor=FakeExtractor(),
        research_agent=FakeResearchAgent(),  # type: ignore[arg-type]
        conclusion_agent=FakeConclusionAgent(),  # type: ignore[arg-type]
        settings=real_settings,
        revision_check_agent=None,
    )
    out = await svc.compare_files(file_a_path="/tmp/a.docx", file_b_path="/tmp/b.docx")
    assert "points" in out
    assert isinstance(out["points"], list)
    assert out["stats"]["points"] == len(out["points"])
    assert "ui" in out["points"][0]
    assert "change_summary" in out["points"][0]
    assert "sources" in out["points"][0]


@pytest.mark.asyncio
async def test_compare_service_returns_error_for_different_documents():
    from app.core.settings import settings as real_settings

    class FakeRevisionCheckAgent:
        async def run(self, *, text_a: str, text_b: str):
            return {"is_same_document": False, "confidence": 5, "reason": "different"}

    class CountingResearchAgent:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, *, point: ChangePoint):
            self.calls += 1
            return {"sources": []}

    counting_research = CountingResearchAgent()

    svc = CompareService(
        extractor=FakeExtractor(),
        research_agent=counting_research,  # type: ignore[arg-type]
        conclusion_agent=FakeConclusionAgent(),  # type: ignore[arg-type]
        settings=real_settings,
        revision_check_agent=FakeRevisionCheckAgent(),  # type: ignore[arg-type]
    )
    out = await svc.compare_files(file_a_path="/tmp/a.docx", file_b_path="/tmp/b.docx")
    assert "error" in out
    assert counting_research.calls == 0

