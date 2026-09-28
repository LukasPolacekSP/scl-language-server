import re
from lsprotocol.types import Diagnostic, DiagnosticSeverity, Range, Position
from pygls.workspace import Document
from pygls.server import LanguageServer
from parser_structured import get_parser, update_parser
from syntax_keywords import SCL_KEYWORDS, BOOLEAN_LOGIC_OPERATORS
from scl_text import strip_comment, find_paren_close, find_body_start, is_begin, STRUCT_START_RE, STRUCT_END_RE

MAX_IDENTIFIER_LENGTH = 24
DIAGNOSTIC_SOURCE = "scl-ls"

VAR_DECL_PATTERN = re.compile(r"(?i)^\s*([\w.]+)\s*:\s*[\w.]+\s*(?::=)?")
CONST_DECL_PATTERN = re.compile(r"(?i)^\s*([\w.]+)\s*:=\s*([\w]+)#([^;]+)\s*;")

# A control-flow header line (`FOR i := 0 TO 10 DO`, `WHILE x < 10 DO`,
# `CASE x OF`, `ELSIF y THEN`, ...) is not an assignment statement and must
# not be required to end with a semicolon, even when it contains a `:=`
# (as a FOR loop's initializer does).
CONTROL_HEADER_END_RE = re.compile(r"(?i)\b(THEN|DO|OF)\s*$")

# A function/FB call statement, e.g. `myFB(IN := x, PT := T#5s);` - used to
# tell call-argument *names* (IN, PT, ...) apart from the *values* passed to
# them, so only the values are checked for being undefined variables.
CALL_START_RE = re.compile(r"(?i)^\s*([\w.]+)\s*\(")


def run_diagnostics(ls: LanguageServer, doc: Document):
    update_parser(doc)
    diagnostics = []

    lines = doc.lines
    code_lines = [strip_comment(line) for line in lines]
    diagnostics += check_assignments(lines, code_lines)
    diagnostics += check_if_blocks(lines, code_lines)
    diagnostics += check_variable_prefix_collisions(lines, code_lines)

    ls.publish_diagnostics(doc.uri, diagnostics)


def _diagnostic(line: int, start: int, end: int, message: str, severity: DiagnosticSeverity) -> Diagnostic:
    return Diagnostic(
        range=Range(start=Position(line=line, character=start), end=Position(line=line, character=end)),
        message=message,
        severity=severity,
        source=DIAGNOSTIC_SOURCE
    )


def is_literal(value: str) -> bool:
    # Exclude time constants starting with T# and SCL keywords
    return (
        re.match(r"^\d+(\.\d+)?$", value)
        or value.upper() in SCL_KEYWORDS
        or value.upper().startswith("T#")
        or re.match(r"^\d+(\.\d+)?(ms|s|m|h|d)$", value, re.IGNORECASE)
    )


def is_var_defined(varname: str) -> bool:
    # SCL identifiers are case-insensitive, so look up via the parser's
    # cached case-insensitive index rather than all_nodes directly.
    parser = get_parser()
    return parser.get_node_ci(varname) is not None


# String literals ('...' or "..."), stripped first so their contents (which
# may contain anything, including things that look like keywords or
# numbers) are never mistaken for identifiers.
_STRING_LITERAL_RE = re.compile(r"'[^']*'|\"[^\"]*\"")

# Typed/based literals: T#5s, TIME#1h, INT#5, DINT#-3, REAL#1.5, 16#FF,
# 2#1010, 8#17, W#16#FF, ... - a base/type token, '#', a value (optionally
# with a second '#value' for based literals like W#16#FF).
_TYPED_LITERAL_RE = re.compile(
    r"(?i)\b\w+#[+-]?\w+(?:\.\d+)?(?:#[+-]?\w+(?:\.\d+)?)?\b"
)

# Plain numbers, including float exponents like 1.0E3.
_NUMBER_RE = re.compile(r"\b\d+(\.\d+)?([eE][+-]?\d+)?\b")


def extract_variables(text: str) -> list[str]:
    """Return the identifier-like tokens in `text` that might be variable
    references. String contents, typed/based numeric literals, and plain
    numbers (including float exponents) are dropped first so they're never
    mistaken for undefined variables."""
    text = _STRING_LITERAL_RE.sub("", text)
    text = _TYPED_LITERAL_RE.sub("", text)
    text = _NUMBER_RE.sub("", text)
    return re.findall(r"[\w.]+", text)


def _find_token_span(line: str, name: str) -> tuple[int, int]:
    """Locate the column span of the whole-word occurrence of `name` in
    `line`, so a short name (e.g. 'iRes') isn't reported at the position of
    a longer identifier that merely contains it as a substring (e.g.
    'iResult'). Falls back to a plain substring search if no whole-word
    occurrence can be found."""
    match = re.search(r"(?<![\w.])" + re.escape(name) + r"(?![\w])", line)
    if match:
        return match.start(), match.end()
    idx = line.find(name)
    if idx == -1:
        return 0, len(name)
    return idx, idx + len(name)


def check_variable_length_and_prefix(var: str, i: int, line: str, prefix_map: dict, scope: tuple) -> list[Diagnostic]:
    """Return diagnostics for variable name length and prefix collisions in the given scope."""
    diagnostics = []
    start, end = _find_token_span(line, var)
    if len(var) > MAX_IDENTIFIER_LENGTH:
        diagnostics.append(_diagnostic(
            i, start, end,
            f"Variable '{var}' is longer than {MAX_IDENTIFIER_LENGTH} characters.",
            DiagnosticSeverity.Information
        ))
    prefix = var[:MAX_IDENTIFIER_LENGTH]
    if scope not in prefix_map:
        prefix_map[scope] = {}
    if prefix in prefix_map[scope]:
        prev_i, prev_var = prefix_map[scope][prefix]
        diagnostics.append(_diagnostic(
            i, start, end,
            f"Variable '{var}' has the same first {MAX_IDENTIFIER_LENGTH} characters as '{prev_var}' (line {prev_i+1}) in the same scope.",
            DiagnosticSeverity.Error
        ))
    else:
        prefix_map[scope][prefix] = (i, var)
    return diagnostics


def check_variable_prefix_collisions(lines: list[str], code_lines: list[str]) -> list[Diagnostic]:
    """
    Return diagnostics if two variables have the same first 24 characters or are too long.
    The check is done per scope: global for top-level, or per structure for nested variables.
    """
    diagnostics = []
    prefix_map = {}
    struct_stack = []
    for i, line in enumerate(lines):
        code = code_lines[i].strip()
        # Check for structure start
        struct_start = STRUCT_START_RE.match(code)
        if struct_start:
            struct_stack.append(struct_start.group(1))
            continue
        # Check for structure end
        if STRUCT_END_RE.match(code):
            if struct_stack:
                struct_stack.pop()
            continue
        # Check for variable declaration
        match = VAR_DECL_PATTERN.match(code)
        if match:
            var_name = match.group(1).strip()
            scope = tuple(struct_stack)
            diagnostics += check_variable_length_and_prefix(var_name, i, line, prefix_map, scope)
            continue
        # Check for constant definition
        const_match = CONST_DECL_PATTERN.match(code)
        if const_match:
            const_name = const_match.group(1).strip()
            scope = tuple(struct_stack)
            diagnostics += check_variable_length_and_prefix(const_name, i, line, prefix_map, scope)
        if is_begin(line):
            break
    return diagnostics


def _lines_inside_calls(lines: list[str], code_lines: list[str], body_start: int) -> set[int]:
    """Find every line that falls inside a multiline function call's
    parentheses (so check_assignments can skip them entirely)."""
    lines_in_function_calls = set()
    for i in range(body_start, len(lines)):
        code = code_lines[i].rstrip()
        if "(" not in code or ":=" not in code:
            continue
        close = find_paren_close(code_lines, i)
        if close == i:
            continue
        end = close if close is not None else len(lines) - 1
        for k in range(i + 1, end + 1):
            lines_in_function_calls.add(k)
    return lines_in_function_calls


def _call_argument_lhs_names(lines: list[str], code_lines: list[str], body_start: int) -> dict[int, set[str]]:
    """Map line index -> the set of call-argument *names* (IN, PT, ...)
    that appear on that line inside a function/FB call's parentheses, e.g.
    `myFB(IN := x, PT := T#5s);` or a call whose args span multiple lines.
    check_assignments uses this to skip checking parameter names as if they
    were variables, while still checking the argument values."""
    result: dict[int, set[str]] = {}
    for i in range(body_start, len(lines)):
        call_match = CALL_START_RE.match(code_lines[i])
        if not call_match:
            continue
        func_name = call_match.group(1)
        if func_name.upper() in SCL_KEYWORDS:
            continue  # not a call: IF (...), WHILE (...), CASE (...), ...

        close = find_paren_close(code_lines, i)
        end = close if close is not None else len(lines) - 1
        for k in range(i, end + 1):
            names = set(re.findall(r"(\w+)\s*:=", code_lines[k]))
            if names:
                result.setdefault(k, set()).update(names)
    return result


def _undefined_variable_diagnostics(
    i: int, raw_line: str, lhs: str, rhs: str, skip_names: frozenset[str] = frozenset()
) -> list[Diagnostic]:
    diagnostics = []
    parser = get_parser()
    for var in extract_variables(lhs) + extract_variables(rhs):
        if var in skip_names:
            continue

        # Skip if it's a function argument (check if parent is a function block call)
        var_node = parser.get_node_ci(var)
        if var_node and var_node.var_type == "fb_argument":
            continue

        # Skip function return variables (e.g., "function.var")
        if "." in var:
            base_var = var.split(".")[0]
            base_node = parser.get_node_ci(base_var)
            if base_node and base_node.var_type == "function_block_call":
                continue

        if not is_literal(var) and not is_var_defined(var):
            start, end = _find_token_span(raw_line, var)
            diagnostics.append(_diagnostic(
                i, start, end,
                f"Variable '{var}' is not defined.",
                DiagnosticSeverity.Warning
            ))
    return diagnostics


def _missing_semicolon_diagnostic(i: int, lines: list[str], code_lines: list[str], code: str) -> list[Diagnostic]:
    # Check for missing semicolon, but allow line continuation with logical operators.
    # For assignments with parentheses, require semicolon only after the closing parenthesis.
    if code.endswith(";"):
        return []

    open_parens = code.count("(") - code.count(")")
    if open_parens > 0:
        # Scan ahead to find the line that closes the parentheses
        close = find_paren_close(code_lines, i)
        if close is not None:
            closing_line = code_lines[close].rstrip()
            if not closing_line.endswith(";"):
                return [_diagnostic(
                    close, len(closing_line), len(closing_line) + 1,
                    "Missing semicolon ';'", DiagnosticSeverity.Error
                )]
        # If never closed, do not report a semicolon error here
        return []

    # Otherwise, check for logical operator continuation
    for k in range(i + 1, len(lines)):
        next_line = code_lines[k]
        if not next_line.strip():
            continue  # skip empty/comment lines
        tokens = next_line.lstrip().split()
        if tokens and tokens[0].upper() in BOOLEAN_LOGIC_OPERATORS:
            return []
        if len(tokens) > 1 and tokens[1].upper() in BOOLEAN_LOGIC_OPERATORS:
            return []
        break  # only check the first non-empty line after current

    return [_diagnostic(i, len(code), len(code) + 1, "Missing semicolon ';'", DiagnosticSeverity.Error)]


def check_assignments(lines: list[str], code_lines: list[str]) -> list[Diagnostic]:
    diagnostics = []
    body_start = find_body_start(lines)
    lines_in_function_calls = _lines_inside_calls(lines, code_lines, body_start)
    call_arg_names = _call_argument_lhs_names(lines, code_lines, body_start)

    for i in range(body_start, len(lines)):
        line = lines[i]

        # Skip lines that are inside function call parentheses
        if i in lines_in_function_calls:
            continue

        code = code_lines[i].rstrip()
        match = re.search(r"([\w.]+)\s*:=\s*(.+)", code)
        if not match:
            continue

        lhs, rhs = match.groups()
        skip_names = call_arg_names.get(i, frozenset())
        diagnostics += _undefined_variable_diagnostics(i, line, lhs, rhs, skip_names)

        # Control-flow header lines (FOR ... DO, WHILE ... DO, CASE ... OF,
        # ELSIF ... THEN, ...) aren't assignment statements even when they
        # contain a ':=' (a FOR loop's initializer), so they don't need a
        # trailing semicolon.
        if not CONTROL_HEADER_END_RE.search(code):
            diagnostics += _missing_semicolon_diagnostic(i, lines, code_lines, code)

    return diagnostics


_IF_START_RE = re.compile(r"(?i)^\s*IF\b")
_ELSE_START_RE = re.compile(r"(?i)^\s*ELSE\b")
_THEN_RE = re.compile(r"(?i)\bTHEN\b")
_END_IF_RE = re.compile(r"(?i)\bEND_IF\b")


def check_if_blocks(lines: list[str], code_lines: list[str]) -> list[Diagnostic]:
    diagnostics = []
    if_stack = []
    body_start = find_body_start(lines)

    for i in range(body_start, len(lines)):
        line = lines[i]
        code = code_lines[i]
        stripped_code = code.strip()

        if _IF_START_RE.match(code):
            if_stack.append({'if': i, 'then': None})

        if _THEN_RE.search(code) and if_stack:
            if_stack[-1]['then'] = i

        if _ELSE_START_RE.match(code):
            if is_empty_else_block(code_lines, i):
                diagnostics.append(_diagnostic(
                    i, 0, len(line), "Missing semicolon ';'", DiagnosticSeverity.Warning
                ))

        if _END_IF_RE.search(code) and if_stack:
            block = if_stack.pop()
            if block['then'] is None:
                diagnostics.append(_diagnostic(
                    block['if'], 0, len(lines[block['if']]),
                    "Missing THEN after IF statement.", DiagnosticSeverity.Error
                ))
            if not stripped_code.endswith(";"):
                diagnostics.append(_diagnostic(
                    i, len(stripped_code), len(stripped_code) + 1,
                    "Missing semicolon ';'", DiagnosticSeverity.Error
                ))

    for block in if_stack:
        diagnostics.append(_diagnostic(
            block['if'], 0, len(lines[block['if']]),
            "END_IF missing after IF statement.", DiagnosticSeverity.Error
        ))

    return diagnostics


def is_empty_else_block(code_lines: list[str], start_index: int) -> bool:
    """Check if ELSE block is empty (contains no statements before END_IF)."""
    for j in range(start_index + 1, len(code_lines)):
        line = code_lines[j].strip()
        if not line:
            continue
        if ";" in line:
            return False
        if line.upper().startswith("END_IF"):
            return True
    return False
