"""Behavioral tests for citations.extract_citations (Author-Year detection, ISO-date + stopword filtering).
Redistributed verbatim from the dissolved tests/predicates/test_helpers.py (idealization)."""


def test_extract_citations_finds_basic_author_year():
    """basic 'Author Year' shape detected."""
    from makoto.citations import extract_citations
    cites = extract_citations("As shown by Smith 2020, the result holds.")
    assert len(cites) == 1
    cite_str, line, snippet = cites[0]
    assert cite_str == "Smith 2020"
    assert line == 1


def test_extract_citations_finds_et_al():
    """'Author et al. Year' shape detected."""
    from makoto.citations import extract_citations
    cites = extract_citations("Per Jones et al. 2021, the bound is tight.")
    assert len(cites) == 1
    cite_str, _, _ = cites[0]
    assert cite_str == "Jones et al. 2021"


def test_extract_citations_returns_line_numbers():
    """multi-line input: line numbers correct."""
    from makoto.citations import extract_citations
    text = "Intro paragraph.\nLine two has Smith 2020 here.\nLine three plain."
    cites = extract_citations(text)
    assert len(cites) == 1
    _, line, _ = cites[0]
    assert line == 2


def test_extract_citations_empty_on_no_match():
    """no matches -> empty list."""
    from makoto.citations import extract_citations
    assert extract_citations("plain prose without citations") == []


def test_extract_citations_skips_iso_date():
    """a year directly followed by -DD is a DATE, not a citation (fixes the 1.6 dated-heading FP)."""
    from makoto.citations import extract_citations
    assert extract_citations("Consolidated 2026-05-29 from notes") == []
    assert extract_citations("Released 2025-01 in the changelog") == []
    # a real (non-date-suffixed) Author-Year cite STILL matches — TP preserved
    cites = extract_citations("As shown by Smith 2020, the result holds.")
    assert len(cites) == 1 and cites[0][0] == "Smith 2020"


def test_extract_citations_filters_stopword_authors():
    """1.0.5: 'Saved 2026' / 'The 2023' / 'From 2020' must NOT count as citations.

    Live audit log (May 2026) showed 40% FP rate on pattern 1.6 from this
    exact shape: capitalized English words preceding a 4-digit year.
    """
    from makoto.citations import extract_citations
    assert extract_citations("Saved 2026-05-26 family-contacts.md") == []
    assert extract_citations("The 2023 release was a major milestone.") == []
    assert extract_citations("From 2020 onward, the rate increased.") == []
    assert extract_citations("Updated 2025 schema with new fields.") == []
    # Author + stopword in same text: only the real one survives
    cites = extract_citations("The 2023 paper by Vaswani 2017 introduced the architecture.")
    assert len(cites) == 1
    assert cites[0][0] == "Vaswani 2017"


def test_extract_citations_still_finds_real_authors_after_stopword_filter():
    """real surnames still match after the stopword filter."""
    from makoto.citations import extract_citations
    assert len(extract_citations("Smith 2020")) == 1
    assert len(extract_citations("Jones et al. 2021")) == 1
    assert len(extract_citations("Hochreiter 1997")) == 1
    assert len(extract_citations("Smith-Jones 2020")) == 1
