from app.diffing.git_like_diff import compute_git_like_hunks


def test_git_like_hunks_basic_replace():
    old_lines = ["line1", "line2", "line3"]
    new_lines = ["line1", "lineX", "line3"]
    hunks = compute_git_like_hunks(old_lines, new_lines, context_lines=1)
    assert len(hunks) >= 1
    payload_old = "\n".join(hunks[0].old_lines)
    payload_new = "\n".join(hunks[0].new_lines)
    assert "line2" in payload_old
    assert "lineX" in payload_new

