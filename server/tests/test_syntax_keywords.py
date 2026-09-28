"""Sanity checks for the shared keyword tables in syntax_keywords.py.

Both the parser and diagnostics modules import from here, so a typo or a
missed union here silently breaks undefined-variable detection or block
parsing everywhere at once - these tests exist to catch that class of
mistake cheaply.
"""
import syntax_keywords as kw


def test_scl_keywords_is_the_union_of_every_category():
    expected = (
        kw.CONTROL_FLOW_KEYWORDS
        | kw.BOOLEAN_LOGIC_KEYWORDS
        | kw.BOOLEAN_LOGIC_OPERATORS
        | kw.DATA_TYPE_KEYWORDS
        | kw.DECLARATION_KEYWORDS
        | kw.END_DECLARATION_KEYWORDS
        | kw.BLOCK_PROGRAM_KEYWORDS
        | kw.MISC_KEYWORDS
    )
    assert kw.SCL_KEYWORDS == expected


def test_every_declaration_keyword_has_a_matching_end_keyword_or_is_end_var():
    # VAR/VAR_INPUT/VAR_OUTPUT/VAR_IN_OUT/VAR_TEMP/VAR_GLOBAL/... all close
    # with END_VAR; CONST closes with END_CONST. Both are covered.
    assert "END_VAR" in kw.END_DECLARATION_KEYWORDS
    assert "END_CONST" in kw.END_DECLARATION_KEYWORDS


def test_common_data_types_are_present():
    for expected_type in ("BOOL", "INT", "REAL", "STRING", "TIME"):
        assert expected_type in kw.DATA_TYPE_KEYWORDS


def test_keyword_categories_do_not_overlap():
    # "OF" is intentionally shared: CONTROL_FLOW_KEYWORDS uses it for
    # CASE ... OF, BLOCK_PROGRAM_KEYWORDS uses it for ARRAY ... OF.
    known_shared_keywords = {"OF"}

    categories = [
        kw.CONTROL_FLOW_KEYWORDS,
        kw.BOOLEAN_LOGIC_KEYWORDS,
        kw.BOOLEAN_LOGIC_OPERATORS,
        kw.DATA_TYPE_KEYWORDS,
        kw.DECLARATION_KEYWORDS,
        kw.END_DECLARATION_KEYWORDS,
        kw.BLOCK_PROGRAM_KEYWORDS,
    ]
    seen = set()
    for category in categories:
        overlap = (seen & category) - known_shared_keywords
        assert not overlap, f"Keyword(s) {overlap} appear in more than one category"
        seen |= category
