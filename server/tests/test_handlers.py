"""Behavior/contract tests for handlers.py (hover, completion, bracket
highlight).

Like test_diagnostics.py, these drive the server through its LSP-facing
functions with plain SCL source and duck-typed params, and assert on the
Hover/CompletionItem/DocumentHighlight objects returned - not on parser
internals. They should keep passing across a parser rewrite (trie/word-tree)
or a port to another language, as long as hover/completion/highlight keep
behaving the same for the same input.
"""
from conftest import FakeDocument, load_fixture
from handlers import find_hover_token_with_segment, handle_completion, handle_highlight, handle_hover


class _Position:
    def __init__(self, line, character):
        self.line = line
        self.character = character


class _TextDocumentIdentifier:
    def __init__(self, uri):
        self.uri = uri


class _Params:
    """Duck-types whatever slice of HoverParams/CompletionParams/
    DocumentHighlightParams handlers.py actually reads, independent of the
    real lsprotocol classes' full constructor signatures."""

    def __init__(self, uri, line, character):
        self.text_document = _TextDocumentIdentifier(uri)
        self.position = _Position(line, character)


def _line_index(source: str, needle: str) -> int:
    for i, line in enumerate(source.splitlines()):
        if needle in line:
            return i
    raise AssertionError(f"{needle!r} not found in source")


# --- find_hover_token_with_segment -----------------------------------------

def test_find_hover_token_with_segment_simple_token():
    line = "iCounter := iCounter + 1;"
    token_info = find_hover_token_with_segment(line, 2)  # inside "iCounter"
    assert token_info == ("iCounter", 0)


def test_find_hover_token_with_segment_picks_dotted_segment():
    line = "Motor.Status.bRunning := TRUE;"
    char = line.index("bRunning") + 1
    token, segment_index = find_hover_token_with_segment(line, char)
    assert token == "Motor.Status.bRunning"
    assert segment_index == 2


def test_find_hover_token_with_segment_returns_none_outside_token():
    line = "iCounter := 1;"
    assert find_hover_token_with_segment(line, line.index(":=")) is None


def test_find_hover_token_with_segment_returns_none_past_end_of_line():
    line = "short"
    assert find_hover_token_with_segment(line, len(line) + 5) is None


# --- handle_hover ------------------------------------------------------------

def test_handle_hover_on_nested_struct_field_shows_type_and_comment(fake_ls):
    source = load_fixture("nested_struct.scl")
    doc = fake_ls.workspace.add(FakeDocument(source))
    line_idx = _line_index(source, "Motor.Status.bRunning := TRUE;")
    line_text = source.splitlines()[line_idx]
    char = line_text.index("bRunning") + 1

    hover = handle_hover(fake_ls, _Params(doc.uri, line_idx, char))

    assert hover is not None
    assert "Type: BOOL" in hover.contents.value
    assert "whether the motor is currently running" in hover.contents.value


def test_handle_hover_on_struct_shows_type_only(fake_ls):
    source = load_fixture("nested_struct.scl")
    doc = fake_ls.workspace.add(FakeDocument(source))
    line_idx = _line_index(source, "Motor.Status.bRunning := TRUE;")
    line_text = source.splitlines()[line_idx]
    char = line_text.index("Status") + 1

    hover = handle_hover(fake_ls, _Params(doc.uri, line_idx, char))

    assert hover is not None
    assert hover.contents.value == "Type: STRUCT"


def test_handle_hover_on_struct_field_with_default_shows_default(fake_ls):
    source = load_fixture("nested_struct.scl")
    doc = fake_ls.workspace.add(FakeDocument(source))
    line_idx = _line_index(source, "Motor.iSpeed := 200;")
    line_text = source.splitlines()[line_idx]
    char = line_text.index("iSpeed") + 1

    hover = handle_hover(fake_ls, _Params(doc.uri, line_idx, char))

    assert hover is not None
    assert "Type: INT" in hover.contents.value
    assert "Default: 100" in hover.contents.value
    assert "Comment: rated speed in RPM" in hover.contents.value


def test_handle_hover_on_unknown_token_returns_none(fake_ls):
    source = load_fixture("valid_program.scl")
    doc = fake_ls.workspace.add(FakeDocument(source))
    line_idx = _line_index(source, "IF bStart THEN")
    char = source.splitlines()[line_idx].index("bStart") + 1

    # bStart IS declared, so this should resolve - sanity check the
    # negative case using an offset that lands on nothing declared instead.
    hover = handle_hover(fake_ls, _Params(doc.uri, line_idx, char))
    assert hover is not None

    blank_doc = fake_ls.workspace.add(FakeDocument("BEGIN\nnothing_declared := 1;\nEND_FUNCTION_BLOCK\n", uri="file:///blank.scl"))
    hover_none = handle_hover(fake_ls, _Params(blank_doc.uri, 1, 2))
    assert hover_none is None


# --- handle_completion --------------------------------------------------------

def test_handle_completion_lists_all_struct_children_for_dotted_prefix(fake_ls):
    base = load_fixture("nested_struct.scl")
    source = base + "\nMotor.\n"
    doc = fake_ls.workspace.add(FakeDocument(source))
    line_idx = len(source.splitlines()) - 1

    items = handle_completion(fake_ls, _Params(doc.uri, line_idx, len("Motor.")))

    assert {item.label for item in items} == {"Status", "iSpeed"}


def test_handle_completion_filters_by_prefix_after_dot(fake_ls):
    base = load_fixture("nested_struct.scl")
    source = base + "\nMotor.i\n"
    doc = fake_ls.workspace.add(FakeDocument(source))
    line_idx = len(source.splitlines()) - 1

    items = handle_completion(fake_ls, _Params(doc.uri, line_idx, len("Motor.i")))

    assert [item.label for item in items] == ["iSpeed"]


def test_handle_completion_filters_top_level_variables_by_prefix(fake_ls):
    base = load_fixture("nested_struct.scl")
    source = base + "\nMo\n"
    doc = fake_ls.workspace.add(FakeDocument(source))
    line_idx = len(source.splitlines()) - 1

    items = handle_completion(fake_ls, _Params(doc.uri, line_idx, len("Mo")))

    assert [item.label for item in items] == ["Motor"]


# --- handle_highlight ----------------------------------------------------------

def test_handle_highlight_matches_outer_and_inner_parentheses(fake_ls):
    source = "IF (a AND (b OR c)) THEN\nx := 1;\nEND_IF;\n"
    doc = fake_ls.workspace.add(FakeDocument(source))
    line = source.splitlines()[0]

    outer_open = line.index("(")
    outer_close = line.rindex(")")
    inner_open = line.index("(", outer_open + 1)
    inner_close = line.index(")")

    result = handle_highlight(fake_ls, _Params(doc.uri, 0, outer_open))
    matched_chars = {(r.range.start.line, r.range.start.character) for r in result}
    assert matched_chars == {(0, outer_open), (0, outer_close)}

    result_inner = handle_highlight(fake_ls, _Params(doc.uri, 0, inner_close))
    matched_chars_inner = {(r.range.start.line, r.range.start.character) for r in result_inner}
    assert matched_chars_inner == {(0, inner_open), (0, inner_close)}


def test_handle_highlight_returns_nothing_for_non_bracket_character(fake_ls):
    source = "x := 1;\n"
    doc = fake_ls.workspace.add(FakeDocument(source))

    result = handle_highlight(fake_ls, _Params(doc.uri, 0, 0))  # 'x'
    assert result == []
