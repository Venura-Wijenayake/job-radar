from __future__ import annotations

from scoring.text_utils import (
    clean_html,
    find_term_in_text,
    find_terms,
    normalize_unicode,
    tokenize,
)


# ----- clean_html -----


def test_clean_html_strips_tags():
    assert clean_html("<p>Hello <strong>world</strong>!</p>") == "Hello world!"


def test_clean_html_drops_script_and_style_content():
    out = clean_html(
        "<p>Visible.</p><script>alert('hi')</script><style>p{color:red}</style>"
    )
    assert "alert" not in out
    assert "color" not in out
    assert "Visible." in out


def test_clean_html_preserves_paragraph_breaks():
    out = clean_html("<p>First paragraph.</p><p>Second paragraph.</p>")
    assert out == "First paragraph.\n\nSecond paragraph."


def test_clean_html_collapses_whitespace():
    out = clean_html("<p>Lots    of   \t spaces.</p>")
    assert out == "Lots of spaces."


def test_clean_html_handles_br():
    out = clean_html("<p>Line one<br>Line two</p>")
    assert "Line one\nLine two" in out


def test_clean_html_handles_empty_or_none():
    assert clean_html("") == ""
    assert clean_html(None) == ""


# ----- normalize_unicode -----


def test_normalize_unicode_replaces_ufffd():
    assert normalize_unicode("hello � world") == "hello — world"


def test_normalize_unicode_smart_quotes_to_straight():
    text = "“hello” ‘world’"
    assert normalize_unicode(text) == '"hello" \'world\''


def test_normalize_unicode_strips_zero_width():
    text = "in​visible"
    assert normalize_unicode(text) == "invisible"


def test_normalize_unicode_nfkc_normalizes_compatible_chars():
    # NFKC turns full-width digits into ASCII digits
    assert normalize_unicode("１２３") == "123"


def test_normalize_unicode_handles_empty():
    assert normalize_unicode("") == ""


# ----- tokenize -----


def test_tokenize_lowercases():
    assert tokenize("Python SQL") == ["python", "sql"]


def test_tokenize_preserves_special_chars():
    out = tokenize("C++ and C# and a/b testing")
    assert "c++" in out
    assert "c#" in out
    assert "a/b" in out


def test_tokenize_preserves_hyphens():
    assert "scikit-learn" in tokenize("uses scikit-learn for ml")


def test_tokenize_drops_short_tokens_except_allowlist():
    out = tokenize("I work in R with c and use Go and js")
    assert "r" in out
    assert "c" in out
    assert "go" in out
    assert "js" in out
    assert "i" not in out


def test_tokenize_filters_punctuation():
    out = tokenize("Hello, world! It's great.")
    assert "hello" in out
    assert "world" in out
    assert "great" in out


# ----- find_term_in_text -----


def test_find_term_in_text_returns_offsets():
    text = "Python is great. I love python."
    offsets = find_term_in_text("python", text)
    assert len(offsets) == 2
    assert text[offsets[0] : offsets[0] + 6].lower() == "python"


def test_find_term_in_text_word_boundary():
    assert find_term_in_text("python", "I am pythonic.") == []
    assert find_term_in_text("java", "javascript developer") == []


def test_find_term_in_text_case_insensitive():
    text = "PYTHON, Python, python"
    assert len(find_term_in_text("python", text)) == 3


def test_find_term_in_text_special_chars():
    text = "Strong in C++ and C# and a/b testing."
    assert len(find_term_in_text("c++", text)) == 1
    assert len(find_term_in_text("c#", text)) == 1
    assert len(find_term_in_text("a/b testing", text)) == 1


def test_find_term_in_text_empty_when_absent():
    assert find_term_in_text("rust", "Python and SQL only.") == []


def test_find_terms_returns_subset():
    matched = find_terms("Python and SQL", ["python", "sql", "java"])
    assert set(matched) == {"python", "sql"}
