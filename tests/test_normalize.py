from app.core.text_normalize import normalize_text_for_diff, text_to_lines


def test_normalize_collapses_whitespace_and_newlines():
    raw = "A\u00a0 B  \n\n\nC"
    assert normalize_text_for_diff(raw) == "A B\n\nC"


def test_text_to_lines():
    raw = "A\nB\n\nC"
    assert text_to_lines(raw) == ["A", "B", "", "C"]

