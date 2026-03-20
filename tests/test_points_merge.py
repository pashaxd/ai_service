from app.diffing.models import DiffHunk
from app.diffing.points import merge_hunks_into_points


def _mk_hunk(i: int, old_start: int, old_end: int, new_start: int, new_end: int) -> DiffHunk:
    return DiffHunk(
        id=f"h{i}",
        old_start=old_start,
        old_end=old_end,
        new_start=new_start,
        new_end=new_end,
        diff_lines=tuple(),
        old_lines=("OLD",),
        new_lines=("NEW",),
    )


def test_merge_hunks_into_points_merges_close_regions():
    h1 = _mk_hunk(1, old_start=10, old_end=12, new_start=20, new_end=22)
    # Close enough in both coordinates.
    h2 = _mk_hunk(2, old_start=14, old_end=15, new_start=24, new_end=25)
    points = merge_hunks_into_points([h1, h2], merge_max_distance_lines=6)
    assert len(points) == 1
    assert len(points[0].hunks) == 2


def test_merge_moved_points_on_separate_removal_addition():
    # Build two ChangePoints manually by using the public dataclass.
    from app.diffing.models import ChangePoint

    p_rem = ChangePoint(
        id="p0",
        hunks=tuple(),
        summary="removed",
        old_context="биометрический вид на жительство – документ, удостоверяющий личность",
        new_context="",
    )
    p_add = ChangePoint(
        id="p1",
        hunks=tuple(),
        summary="added",
        old_context="",
        new_context="биометрический вид на жительство – документ, удостоверяющий личность",
    )

    from app.diffing.points import _merge_moved_points

    merged = _merge_moved_points([p_rem, p_add], similarity_threshold=0.95, max_distance_between_points=3)
    assert len(merged) == 1
    assert merged[0].old_context
    assert merged[0].new_context

