"""Shared lexical helpers used by both the parser and diagnostics checks.

These operate on plain SCL source lines and know nothing about LSP types or
the parser's tree structures - they're the small bits of text handling that
were previously copy-pasted between parser_structured.py and diagnostics.py.
"""
import re


def strip_comment(line: str) -> str:
    """Return line with any trailing `//` comment (and everything after it)
    removed. Leading/trailing whitespace and line endings are left as-is."""
    return line.split("//")[0]


def extract_comment(line: str) -> str:
    """Return the text after `//` on line, or "" if there is none."""
    comment_index = line.find("//")
    if comment_index != -1:
        return line[comment_index + 2:].strip()
    return ""


def find_paren_close(code_lines: list[str], start: int) -> int | None:
    """Track paren depth starting at code_lines[start] and return the index
    of the line where the net open-paren count first drops to <= 0.

    Returns `start` itself if code_lines[start] has no net unclosed paren
    (nothing to scan for), or None if the parens never close before the end
    of code_lines. `code_lines` should have comments already stripped.
    """
    depth = code_lines[start].count("(") - code_lines[start].count(")")
    if depth <= 0:
        return start
    for k in range(start + 1, len(code_lines)):
        depth += code_lines[k].count("(") - code_lines[k].count(")")
        if depth <= 0:
            return k
    return None


# Regexes for STRUCT start/end that both the parser and the diagnostics'
# prefix-collision check need to recognize identically.
STRUCT_START_RE = re.compile(r"(?i)(\w+)\s*:\s*STRUCT\b")
STRUCT_END_RE = re.compile(r"(?i)END_STRUCT\s*;")


def is_begin(line: str) -> bool:
    """Return True if `line` is exactly the BEGIN keyword, once a trailing
    `//` comment and surrounding whitespace are stripped, case-insensitively.

    This is the one shared definition of "is this the BEGIN line" used by
    the parser and every diagnostics check, so `BEGIN // comment` is always
    recognized as BEGIN, and a declaration like `BeginTime : TIME;` is
    never mistaken for it (unlike a plain `.upper().startswith("BEGIN")`
    check, which matches both incorrectly).
    """
    return strip_comment(line).strip().upper() == "BEGIN"


def find_body_start(lines: list[str]) -> int:
    """Return the index of the first line after the BEGIN keyword line, or
    len(lines) if BEGIN is never found. Uses `is_begin` so it agrees with
    the parser's own declaration/body split."""
    for i, line in enumerate(lines):
        if is_begin(line):
            return i + 1
    return len(lines)
