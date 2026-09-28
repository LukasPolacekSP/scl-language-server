import re
from lsprotocol.types import Diagnostic, DiagnosticSeverity, Range, Position
from pygls.workspace import Document
from pygls.server import LanguageServer
from parser_structured import get_parser, update_parser
from syntax_keywords import SCL_KEYWORDS, BOOLEAN_LOGIC_OPERATORS
from scl_text import strip_comment, find_paren_close, STRUCT_START_RE, STRUCT_END_RE

MAX_IDENTIFIER_LENGTH = 24
DIAGNOSTIC_SOURCE = "scl-ls"

VAR_DECL_PATTERN = re.compile(r"(?i)^\s*([\w.]+)\s*:\s*[\w.]+\s*(?::=)?")
CONST_DECL_PATTERN = re.compile(r"(?i)^\s*([\w.]+)\s*:=\s*([\w]+)#([^;]+)\s*;")


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
    # Use parser.all_nodes for variable existence
    parser = get_parser()
    return varname in parser.all_nodes


def extract_variables(text: str) -> list[str]:
    # Remove T# time literals and numbers
    text = re.sub(r"\bT#\w+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+(\.\d+)?\b", "", text)
    # Extract variable-like tokens, skip time literals and numbers
    return re.findall(r"[\w.]+", text)


def check_variable_length_and_prefix(var: str, i: int, line: str, prefix_map: dict, scope: tuple) -> list[Diagnostic]:
    """Return diagnostics for variable name length and prefix collisions in the given scope."""
    diagnostics = []
    if len(var) > MAX_IDENTIFIER_LENGTH:
        diagnostics.append(_diagnostic(
            i, line.find(var), line.find(var) + len(var),
            f"Variable '{var}' is longer than {MAX_IDENTIFIER_LENGTH} characters.",
            DiagnosticSeverity.Information
        ))
    prefix = var[:MAX_IDENTIFIER_LENGTH]
    if scope not in prefix_map:
        prefix_map[scope] = {}
    if prefix in prefix_map[scope]:
        prev_i, prev_var = prefix_map[scope][prefix]
        diagnostics.append(_diagnostic(
            i, line.find(var), line.find(var) + len(var),
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
        if line.strip().startswith("BEGIN"):
            break
    return diagnostics


def _lines_inside_calls(lines: list[str], code_lines: list[str]) -> tuple[set[int], bool]:
    """Find every line that falls inside a multiline function call's
    parentheses (so check_assignments can skip them), and report the final
    in_code_block state so the caller's second pass can pick it up."""
    in_code_block = False
    lines_in_function_calls = set()
    for i in range(len(lines)):
        stripped = lines[i].strip().upper()
        if stripped == "BEGIN":
            in_code_block = True
            continue
        if not in_code_block:
            continue

        code = code_lines[i].rstrip()
        if "(" not in code or ":=" not in code:
            continue
        close = find_paren_close(code_lines, i)
        if close == i:
            continue
        end = close if close is not None else len(lines) - 1
        for k in range(i + 1, end + 1):
            lines_in_function_calls.add(k)
    return lines_in_function_calls, in_code_block


def _undefined_variable_diagnostics(i: int, raw_line: str, lhs: str, rhs: str) -> list[Diagnostic]:
    diagnostics = []
    parser = get_parser()
    for var in extract_variables(lhs) + extract_variables(rhs):
        # Skip if it's a function argument (check if parent is a function block call)
        var_node = parser.all_nodes.get(var)
        if var_node and var_node.var_type == "fb_argument":
            continue

        # Skip function return variables (e.g., "function.var")
        if "." in var:
            base_var = var.split(".")[0]
            base_node = parser.all_nodes.get(base_var)
            if base_node and base_node.var_type == "function_block_call":
                continue

        if not is_literal(var) and not is_var_defined(var):
            diagnostics.append(_diagnostic(
                i, raw_line.find(var), raw_line.find(var) + len(var),
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
    lines_in_function_calls, in_code_block = _lines_inside_calls(lines, code_lines)

    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == "BEGIN":
            in_code_block = True
            continue
        if not in_code_block:
            continue

        # Skip lines that are inside function call parentheses
        if i in lines_in_function_calls:
            continue

        code = code_lines[i].rstrip()
        match = re.search(r"([\w.]+)\s*:=\s*(.+)", code)
        if not match:
            continue

        lhs, rhs = match.groups()
        diagnostics += _undefined_variable_diagnostics(i, line, lhs, rhs)
        diagnostics += _missing_semicolon_diagnostic(i, lines, code_lines, code)

    return diagnostics


def check_if_blocks(lines: list[str], code_lines: list[str]) -> list[Diagnostic]:
    diagnostics = []
    if_stack = []

    for i, line in enumerate(lines):
        upper = line.strip().upper()
        stripped_code = code_lines[i].strip()

        if upper.startswith("IF"):
            if_stack.append({'if': i, 'then': None})

        if "THEN" in upper and if_stack:
            if_stack[-1]['then'] = i

        if upper.startswith("ELSE"):
            if is_empty_else_block(code_lines, i):
                diagnostics.append(_diagnostic(
                    i, 0, len(line), "Missing semicolon ';'", DiagnosticSeverity.Warning
                ))

        if "END_IF" in upper and if_stack:
            block = if_stack.pop()
            if block['then'] is None:
                diagnostics.append(_diagnostic(
                    block['if'], 0, len(lines[block['if']]),
                    "Missing THEN after IF statement.", DiagnosticSeverity.Error
                ))
            if not stripped_code.rstrip().endswith(";"):
                diagnostics.append(_diagnostic(
                    i, len(stripped_code), len(stripped_code) + 1,
                    "Missing semicolon ';'", DiagnosticSeverity.Error
                ))

    for block in if_stack:
        diagnostics.append(_diagnostic(
            block['if'], 0, len(lines[block['if']]),
            "END_IF missing after IF statment.", DiagnosticSeverity.Error
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
