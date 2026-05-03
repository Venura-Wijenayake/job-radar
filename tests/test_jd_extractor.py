from __future__ import annotations

from db.models import Item
from scoring.jd_extractor import (
    STOPWORDS,
    _capitalized_phrase_tokens,
    extract_keywords,
)


def _item(body: str, title: str = "Test") -> Item:
    """Build an unsaved Item for the extractor (it doesn't touch the DB)."""
    return Item(
        source_id=1,
        external_id="x",
        title=title,
        body=body,
        url="http://t",
        content_hash="h",
    )


def test_capitalized_phrase_tokens_finds_two_word_titles():
    text = "We use Power BI and Apache Airflow on Google Cloud Platform."
    out = _capitalized_phrase_tokens(text)
    assert {"power", "bi", "apache", "airflow"}.issubset(out)
    assert {"google", "cloud", "platform"}.issubset(out)


def test_capitalized_phrase_tokens_ignores_single_words():
    text = "Apple is great. So is Google."
    out = _capitalized_phrase_tokens(text)
    assert "apple" not in out
    assert "google" not in out


def test_extract_keywords_taxonomy_terms_get_importance_2():
    body = (
        "We use Python, Python, Python, and SQL daily. "
        "Strong pandas and numpy experience required."
    )
    out = extract_keywords(_item(body))
    by_term = {kw["term"]: kw for kw in out}
    assert by_term["python"]["importance"] == 2.0
    assert by_term["sql"]["importance"] == 2.0
    assert by_term["pandas"]["importance"] == 2.0


def test_extract_keywords_filters_stopwords():
    body = "the the the the with for and or to is " * 10 + " python python"
    out = extract_keywords(_item(body))
    terms = {kw["term"] for kw in out}
    assert STOPWORDS.isdisjoint(terms)
    assert "python" in terms


def test_extract_keywords_capitalized_phrase_tokens_get_importance_15():
    # "Foobar Studio" is not in taxonomy and not a stopword → cap-phrase boost
    body = (
        "Join the Foobar Studio team. Foobar Studio builds amazing things. "
        "Foobar Studio is hiring."
    )
    out = extract_keywords(_item(body))
    by_term = {kw["term"]: kw for kw in out}
    assert by_term["foobar"]["importance"] == 1.5
    assert by_term["studio"]["importance"] == 1.5


def test_extract_keywords_returns_top_n_sorted_by_score():
    body = "alpha alpha alpha beta beta gamma " * 5
    out = extract_keywords(_item(body), top_n=3)
    assert len(out) == 3
    terms_in_order = [kw["term"] for kw in out]
    assert terms_in_order[0] == "alpha"
    assert terms_in_order[1] == "beta"


def test_extract_keywords_empty_body():
    out = extract_keywords(_item(""))
    assert out == []


def test_extract_keywords_strips_html_before_tokenizing():
    body = "<p>We use <strong>python</strong> and <em>SQL</em>.</p>"
    out = extract_keywords(_item(body))
    terms = {kw["term"] for kw in out}
    assert "python" in terms
    assert "sql" in terms
    assert "strong" not in terms
    assert "em" not in terms
