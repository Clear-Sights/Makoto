from makoto.checks.spec import find_relative_citations, relative_path_gate


def test_fires_on_bare_relative_directory_path():
    hits = find_relative_citations("see substrate/hollowTest.py for the detector")
    assert hits == [("substrate/hollowTest.py", 4)]


def test_fires_on_bare_file_line_citation():
    hits = find_relative_citations("the bug is in audit.py:93")
    assert hits == [("audit.py:93", 14)]


def test_silent_on_absolute_path():
    assert find_relative_citations("see /home/user/makoto-dev/substrate/hollowTest.py") == []


def test_silent_on_url():
    assert find_relative_citations("docs at https://example.com/guide.html for more") == []


def test_silent_inside_fenced_code_block():
    text = "before\n```\nopen(\"config.json\")\n```\nafter"
    assert find_relative_citations(text) == []


def test_silent_on_version_number():
    assert find_relative_citations("bumped to version 1.4.1 today") == []


def test_silent_on_dotted_code_identifier():
    assert find_relative_citations("see Finding.source_event_id for the field") == []


def test_silent_on_bare_word_slash_word():
    assert find_relative_citations("either add it and/or remove the old one") == []


def test_dedupes_repeated_citation():
    hits = find_relative_citations("edit substrate/hollowTest.py then re-check substrate/hollowTest.py again")
    assert len(hits) == 1


def test_gate_fires_finding_advisory_never_error():
    f = relative_path_gate("see substrate/hollowTest.py:146")
    assert f is not None
    assert f.level == "advisory"
    assert "substrate/hollowTest.py:146" in f.message


def test_gate_silent_on_no_citations():
    assert relative_path_gate("just a normal sentence with no paths") is None


def test_gate_silent_on_empty_text():
    assert relative_path_gate("") is None
    assert relative_path_gate(None) is None
