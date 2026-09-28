"""Behavior/contract tests for diagnostics.py.

These tests drive the server the same way the editor does: feed a whole
.scl document through run_diagnostics() and assert on the Diagnostic list
it publishes. They deliberately don't touch the parser's internal data
structures (VariableNode, all_nodes, ...), so they should keep passing
across a rewrite of the parser's internals (e.g. to a trie/word-tree) or
even a port to a different implementation language - only the .scl input
fixtures and the expected diagnostics below would need to carry over.
"""
from lsprotocol.types import DiagnosticSeverity

from conftest import FakeDocument, FakeLanguageServer, load_fixture
from diagnostics import run_diagnostics


def run(source: str):
    """Parse `source` as if it were a freshly opened/changed document and
    return the list of Diagnostics the server would publish for it."""
    ls = FakeLanguageServer()
    doc = FakeDocument(source)
    run_diagnostics(ls, doc)
    assert len(ls.published_diagnostics) == 1
    uri, diagnostics = ls.published_diagnostics[0]
    assert uri == doc.uri
    return diagnostics


def messages(diagnostics):
    return [d.message for d in diagnostics]


def test_valid_program_has_no_diagnostics():
    diagnostics = run(load_fixture("valid_program.scl"))
    assert diagnostics == []


def test_undefined_variable_is_flagged():
    diagnostics = run(load_fixture("undefined_variable.scl"))
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert "iResult" in d.message
    assert "is not defined" in d.message
    assert d.severity == DiagnosticSeverity.Warning
    assert d.range.start.line == 5  # 0-indexed: "iResult := iValue + 1;"


def test_missing_semicolon_is_flagged():
    diagnostics = run(load_fixture("missing_semicolon.scl"))
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert "Missing semicolon" in d.message
    assert d.severity == DiagnosticSeverity.Error
    assert d.range.start.line == 5  # "iValue := 5" (no trailing ';')


def test_if_without_then_is_flagged():
    diagnostics = run(load_fixture("missing_then.scl"))
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert "Missing THEN" in d.message
    assert d.severity == DiagnosticSeverity.Error


def test_if_without_end_if_is_flagged():
    diagnostics = run(load_fixture("missing_end_if.scl"))
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert "END_IF missing" in d.message
    assert d.severity == DiagnosticSeverity.Error


def test_empty_else_block_is_not_currently_flagged():
    # KNOWN BUG (see upgrade notes shared alongside this test suite):
    # is_empty_else_block() in diagnostics.py checks `if ";" in line: return
    # False` on each line *before* checking whether that line is END_IF. The
    # terminating "END_IF;" line always contains a ';', so that check fires
    # first and the function returns False (not empty) even for a
    # genuinely empty ELSE branch immediately followed by END_IF;. This
    # test locks in that current (buggy) behavior; it is not the intended
    # design (an empty ELSE is meant to be flagged) - fixing the check
    # order is on the upgrade list, not done here.
    diagnostics = run(load_fixture("empty_else.scl"))
    assert diagnostics == []


def test_struct_field_name_collision_and_length_are_flagged():
    diagnostics = run(load_fixture("struct_prefix_collision.scl"))
    msgs = messages(diagnostics)

    long_name_warnings = [m for m in msgs if "longer than 24 characters" in m]
    collision_warnings = [m for m in msgs if "same first 24 characters" in m]

    # Both struct fields are >24 chars long, and they collide on their
    # first 24 characters ("LongMeasurementSensorVal...").
    assert len(long_name_warnings) == 2
    assert len(collision_warnings) == 1
    assert "LongMeasurementSensorValueBanana" in collision_warnings[0]
    assert "LongMeasurementSensorValueApple" in collision_warnings[0]


def test_time_literal_is_not_flagged_as_undefined():
    # Regression test for the CHANGELOG 0.0.3 fix: T#<n><unit> time
    # constants must not be reported as undefined variables.
    diagnostics = run(load_fixture("time_literal.scl"))
    assert diagnostics == []


def test_multiline_function_block_call_arguments_are_not_flagged_as_undefined():
    # Regression test for the CHANGELOG 0.0.3 fix: named arguments in a
    # function block call spanning multiple lines must not be reported as
    # undefined variables.
    diagnostics = run(load_fixture("function_block_call_multiline.scl"))
    undefined_messages = [d.message for d in diagnostics if "is not defined" in d.message]
    assert undefined_messages == []


def test_multiline_function_block_call_currently_raises_spurious_missing_semicolons():
    # KNOWN BUG (see upgrade notes shared alongside this test suite):
    # check_assignments() only recognizes a multiline function call when
    # "(" and ":=" appear on the SAME line (the `"(" in code and ":=" in
    # code` guard in diagnostics.py). A call whose opening "(" is alone on
    # its own line - the fixture's style, and a common one - isn't
    # recognized, so each `arg := value,` line underneath it gets treated
    # as its own top-level assignment statement missing a trailing ';'.
    # This test locks in that current (buggy) behavior; fixing the guard
    # to also handle this multi-line-open style is on the upgrade list,
    # not done here.
    diagnostics = run(load_fixture("function_block_call_multiline.scl"))
    semicolon_lines = sorted(
        d.range.start.line for d in diagnostics if "Missing semicolon" in d.message
    )
    assert semicolon_lines == [7, 8]  # "Start := bStart," / "Speed := iSpeed"


def test_nested_struct_field_assignment_is_not_flagged():
    diagnostics = run(load_fixture("nested_struct.scl"))
    assert diagnostics == []


def test_for_loop_header_is_not_flagged_as_missing_semicolon():
    # Regression test for bug 1: `FOR i := 0 TO 10 BY 2 DO` is a
    # control-flow header, not an assignment statement, even though it
    # contains a ':='. It must not be flagged as missing a semicolon, and
    # the FOR/TO/BY/DO keywords must not be flagged as undefined either.
    diagnostics = run(load_fixture("for_loop_header.scl"))
    assert diagnostics == []


def test_declaration_line_default_value_is_not_checked_as_code():
    # Regression test for bug 2: a declaration like `x : INT := zz;`
    # inside a VAR block was being run through the same undefined-variable
    # check as body code, because check_assignments' first pass leaked its
    # in_code_block state into the second pass. Declarations must not be
    # checked at all.
    diagnostics = run(load_fixture("declaration_default_not_checked.scl"))
    assert diagnostics == []


def test_identifier_starting_with_begin_is_not_mistaken_for_begin_keyword():
    # Regression test for bug 3: `BeginTime : TIME;` was ending the
    # declaration section early in the parser (startswith("BEGIN") on the
    # upper-cased line), so BeginTime was never registered as a variable.
    diagnostics = run(load_fixture("begin_prefixed_identifier.scl"))
    assert diagnostics == []


def test_begin_with_trailing_comment_still_starts_the_code_section():
    # Regression test for bug 3: diagnostics required the line to be
    # exactly "BEGIN" (after upper-casing), so `BEGIN // start of code`
    # never flipped on code checking, and undefined variables in the body
    # went completely unchecked.
    diagnostics = run(load_fixture("begin_with_trailing_comment.scl"))
    assert len(diagnostics) == 1
    assert "'y'" in diagnostics[0].message
    assert "is not defined" in diagnostics[0].message


def test_if_like_identifiers_are_not_mistaken_for_if_then_keywords():
    # Regression test for bug 4: check_if_blocks used substring checks
    # (upper.startswith("IF"), "THEN" in upper), which matched identifiers
    # like IFace and bTHENx. Must use word-boundary matching instead.
    diagnostics = run(load_fixture("if_like_identifiers.scl"))
    assert diagnostics == []


def test_named_call_arguments_are_not_flagged_as_undefined():
    # Regression test for bug 6: `myFB(IN := x, PT := T#5s);` - only the
    # argument VALUE (x) should be checked; the argument NAMES (IN, PT)
    # are not variables and must not be flagged.
    diagnostics = run(load_fixture("named_call_arguments.scl"))
    assert diagnostics == []


def test_call_argument_name_reused_elsewhere_is_still_flagged_as_undefined():
    # Regression test for bug 6: the old fix registered call-argument names
    # (like IN) under a bare key in all_nodes, which hid genuinely
    # undefined uses of that same name elsewhere in the document. `IN` is
    # only a parameter name here, not a declared variable, so using it as
    # a real value on another line must still be flagged.
    diagnostics = run(load_fixture("call_argument_name_reused.scl"))
    undefined_messages = [d.message for d in diagnostics if "is not defined" in d.message]
    assert len(undefined_messages) == 1
    assert "'IN'" in undefined_messages[0]


def test_typed_and_string_literals_are_not_flagged_as_undefined():
    # Regression test for bug 8: hex/typed literals (16#FF, DINT#-3,
    # TIME#1h, REAL#1.5, W#16#FF, 8#17), float exponents (1.0E3), and
    # quoted strings must all be recognized as literals, not identifiers.
    diagnostics = run(load_fixture("typed_and_string_literals.scl"))
    assert diagnostics == []


def test_plain_const_value_is_recognized_as_defined():
    # Regression test for bug 8: the parser's CONST handling only
    # recognized the typed form (`NAME := TYPE#value;`); a plain constant
    # like `MAX_LEN := 10;` was never registered, so using it was flagged
    # as undefined.
    diagnostics = run(load_fixture("plain_const_value.scl"))
    assert diagnostics == []


def test_case_different_variable_use_is_not_flagged_as_undefined():
    # Regression test for bug 8: SCL identifiers are case-insensitive, so
    # a variable declared `Counter` and used as `counter` must not be
    # flagged as undefined.
    diagnostics = run(load_fixture("case_insensitive_variable.scl"))
    assert diagnostics == []


def test_undefined_variable_diagnostic_column_is_whole_word_not_substring():
    # Regression test for bug 9: the diagnostic column came from
    # line.find(var), which lands on the first substring match - 'iRes'
    # was reported inside 'iResult' rather than at the real standalone
    # 'iRes' token later on the line.
    source = load_fixture("word_boundary_column.scl")
    diagnostics = run(source)
    ires_diag = next(d for d in diagnostics if "'iRes'" in d.message)
    line = source.splitlines()[5]  # "iResult := iValue + iRes;"
    expected_col = line.rindex("iRes")
    assert ires_diag.range.start.character == expected_col
    assert ires_diag.range.end.character == expected_col + len("iRes")
