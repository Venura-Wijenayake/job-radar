from __future__ import annotations

from scoring.language_utils import detect_language


def test_detect_language_english_text():
    text = (
        "We are looking for a senior data analyst to join our team. "
        "The role is remote and the candidate must have experience "
        "with Python and SQL. This is a full-time position with great "
        "benefits and we are excited to hear from you."
    )
    assert detect_language(text) == "en"


def test_detect_language_portuguese_text():
    text = (
        "Estamos procurando um analista de dados sênior para se juntar "
        "à nossa equipe. A função é remota e o candidato deve ter "
        "experiência com Python e SQL. Esta é uma posição em tempo "
        "integral com ótimos benefícios. Buscamos uma pessoa motivada."
    )
    assert detect_language(text) == "other"


def test_detect_language_short_text_defaults_to_en():
    assert detect_language("Hello") == "en"
    assert detect_language("") == "en"


def test_detect_language_mixed_falls_in_middle():
    """Sentence with low but non-zero English stopword density should be 'mixed'
    or 'en' — never 'other'."""
    text = (
        "Senior Engineer Role Salary 80000 USD Remote Full Time Position "
        "Required Python SQL Pandas NumPy Experience Years Five Plus"
    )
    result = detect_language(text)
    assert result in {"en", "mixed"}
