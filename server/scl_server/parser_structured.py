import re
from syntax_keywords import DECLARATION_KEYWORDS, DATA_TYPE_KEYWORDS, END_DECLARATION_KEYWORDS, SCL_KEYWORDS
from scl_text import strip_comment, extract_comment, find_paren_close, is_begin, STRUCT_START_RE, STRUCT_END_RE

BLOCK_TO_VAR_TYPE = {
    "VAR_INPUT": "input",
    "VAR_OUTPUT": "output",
    "VAR_IN_OUT": "inout",
    "VAR": "static",
    "VAR_TEMP": "temporary",
    "CONST": "constant",
}

CONST_DECL_RE = re.compile(r"(?i)(\w+)\s*:=\s*([\w]+)#([^;]+)\s*;")
PLAIN_CONST_DECL_RE = re.compile(r"(?i)(\w+)\s*:=\s*([^;]+)\s*;")
VAR_DECL_RE = re.compile(r"(?i)(\w+)\s*:\s*([\w.]+)(?:\s*:=\s*([^;]+))?\s*;")
CALL_START_RE = re.compile(r"(?i)(\w+)\s*\(\s*")

# Singleton parser instance
_parser_instance = None

def get_parser():
    """Get or create the singleton parser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = StructuredSCLParser()
    return _parser_instance

def update_parser(doc):
    """Update parser with new document content."""
    parser = get_parser()
    parser.parse(doc.source)

class VariableNode:
    def __init__(self, name, var_type, data_type, parent=None, default=None, comment=None, block_type=None):
        self.name = name
        self.var_type = var_type  # input, output, inout, static, temp, normal
        self.data_type = data_type  # INT, BOOL, STRUCT, etc.
        self.parent = parent  # parent VariableNode or None
        self.children = {}  # name -> VariableNode
        self.default = default
        self.comment = comment
        self.block_type = block_type  # VAR_INPUT, VAR_OUTPUT, etc.

    def add_child(self, child):
        self.children[child.name] = child

class StructuredSCLParser:
    def __init__(self):
        self.variables = {}  # name -> VariableNode
        self.all_nodes = {}  # all VariableNodes by full path
        self._last_source = None
        self._all_nodes_ci = None  # lowercased-key cache, built lazily; see get_node_ci

    def parse(self, text: str):
        if text == self._last_source:
            return
        self._last_source = text

        self.variables = {}
        self.all_nodes = {}
        self._all_nodes_ci = None
        lines = text.splitlines()
        code_lines = [strip_comment(line) for line in lines]
        parent_stack = []

        body_start = self._parse_declarations(lines, parent_stack)
        self._parse_body(lines, code_lines, body_start, parent_stack)

    def get_node_ci(self, path: str) -> "VariableNode | None":
        """Case-insensitive lookup into all_nodes (SCL identifiers are
        case-insensitive). The lowercased index is built once per parse and
        cached here rather than changing all_nodes' own (case-preserving)
        keys."""
        if self._all_nodes_ci is None:
            self._all_nodes_ci = {key.lower(): node for key, node in self.all_nodes.items()}
        return self._all_nodes_ci.get(path.lower())

    def _parse_declarations(self, lines: list[str], parent_stack: list) -> int:
        """Parse the VAR/VAR_INPUT/.../CONST declaration section.

        Returns the index of the first line after BEGIN, or len(lines) if
        BEGIN was never found (in which case there is no body to parse).
        """
        block_type = None
        current_parent = None
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            upper = stripped.upper()
            if is_begin(lines[i]):
                return i + 1

            block_type = self._handle_block_start_end(upper, block_type)
            if block_type is None:
                i += 1
                continue

            if self._handle_structure_start(stripped, block_type, parent_stack, current_parent):
                current_parent = self._get_parent_node(parent_stack)
                i += 1
                continue

            if self._handle_structure_end(stripped, parent_stack):
                current_parent = self._get_parent_node(parent_stack)
                i += 1
                continue

            if self._handle_constant_definition(stripped, block_type, parent_stack, current_parent):
                i += 1
                continue

            if self._handle_variable_declaration(stripped, block_type, parent_stack, current_parent):
                i += 1
                continue

            i += 1
        return len(lines)

    def _parse_body(self, lines: list[str], code_lines: list[str], start: int, parent_stack: list):
        """Parse the executable section (after BEGIN), registering function
        block call arguments so they aren't flagged as undefined variables."""
        i = start
        while i < len(lines):
            consumed_lines = self._handle_function_block_call(lines, code_lines, i, parent_stack)
            i += consumed_lines if consumed_lines > 0 else 1

    def _handle_block_start_end(self, upper: str, block_type: str) -> str:
        if upper in DECLARATION_KEYWORDS:
            return upper
        if upper in END_DECLARATION_KEYWORDS:
            return None
        return block_type

    def _register(self, node: VariableNode, parent_stack: list, current_parent: VariableNode):
        """Attach node to its parent (or the top-level variables), and index
        it in all_nodes under its full dotted path."""
        if current_parent:
            current_parent.add_child(node)
        else:
            self.variables[node.name] = node
        self.all_nodes[self._full_path(parent_stack, node.name)] = node

    def _handle_structure_start(self, line: str, block_type: str, parent_stack: list, current_parent: VariableNode) -> bool:
        match = STRUCT_START_RE.match(line)
        if match:
            name = match.group(1)
            node = VariableNode(
                name=name,
                var_type=self._block_to_vartype(block_type),
                data_type="STRUCT",
                parent=current_parent,
                comment=extract_comment(line),
                block_type=block_type
            )
            self._register(node, parent_stack, current_parent)
            parent_stack.append(name)
            return True
        return False

    def _handle_structure_end(self, line: str, parent_stack: list) -> bool:
        if STRUCT_END_RE.match(line):
            if parent_stack:
                parent_stack.pop()
            return True
        return False

    def _handle_constant_definition(self, line: str, block_type: str, parent_stack: list, current_parent: VariableNode) -> bool:
        if block_type != "CONST":
            return False

        match = CONST_DECL_RE.match(line)
        if match:
            name, data_type, value = match.groups()
            node = VariableNode(
                name=name,
                var_type="constant",
                data_type=data_type,
                parent=current_parent,
                default=value.strip(),
                comment=extract_comment(line),
                block_type=block_type
            )
            self._register(node, parent_stack, current_parent)
            return True

        # Plain (untyped) constants, e.g. `MAX_LEN := 10;`, as opposed to
        # the typed form `MAX_SPEED := INT#100;` matched above.
        match = PLAIN_CONST_DECL_RE.match(line)
        if match:
            name, value = match.groups()
            node = VariableNode(
                name=name,
                var_type="constant",
                data_type=None,
                parent=current_parent,
                default=value.strip(),
                comment=extract_comment(line),
                block_type=block_type
            )
            self._register(node, parent_stack, current_parent)
            return True

        return False

    def _handle_variable_declaration(self, line: str, block_type: str, parent_stack: list, current_parent: VariableNode) -> bool:
        match = VAR_DECL_RE.match(line)
        if match:
            name, data_type, default = match.groups()
            node = VariableNode(
                name=name,
                var_type=self._block_to_vartype(block_type),
                data_type=data_type,
                parent=current_parent,
                default=default.strip() if default else None,
                comment=extract_comment(line),
                block_type=block_type
            )
            self._register(node, parent_stack, current_parent)
            return True
        return False

    def _handle_function_block_call(self, lines: list, code_lines: list, start_idx: int, parent_stack: list):
        """
        Handle function block calls that may span multiple lines.
        Returns the number of lines consumed (0 if not a function call).
        """
        line = lines[start_idx].strip()
        match = CALL_START_RE.match(line)
        if not match:
            return 0

        func_name = match.group(1)
        if func_name.upper() in SCL_KEYWORDS:
            # Ignore type conversions like INT(), BOOL(), etc., and control
            # structures like IF(...), WHILE(...), NOT(...), ELSIF(...),
            # CASE(...) - none of these are function block calls.
            return 0

        # Create function block node
        node = VariableNode(
            name=func_name,
            var_type="function_block_call",
            data_type=None,
            parent=None,
            comment=extract_comment(line),
            block_type=None
        )
        self.all_nodes[self._full_path(parent_stack, func_name)] = node

        # Collect all lines until closing parenthesis
        close = find_paren_close(code_lines, start_idx)
        end_idx = close if close is not None else len(lines) - 1
        full_call = " ".join(code_lines[k].strip() for k in range(start_idx, end_idx + 1))
        lines_consumed = end_idx - start_idx + 1

        # Extract all arguments from the complete function call
        # Match patterns like: argName := value or argName:=value
        arg_matches = re.findall(r"(\w+)\s*:=", full_call)
        for arg in arg_matches:
            # Don't add as argument if it's already a known variable
            if arg.upper() in DATA_TYPE_KEYWORDS or arg.upper() in ['TRUE', 'FALSE']:
                continue
            arg_node = VariableNode(
                name=arg,
                var_type="fb_argument",
                data_type=None,
                parent=node
            )
            node.add_child(arg_node)
            self.all_nodes[self._full_path(parent_stack, f"{func_name}.{arg}")] = arg_node

        return lines_consumed

    def _block_to_vartype(self, block_type):
        return BLOCK_TO_VAR_TYPE.get(block_type, "normal")

    def _full_path(self, parent_stack, name):
        return ".".join(parent_stack + [name]) if parent_stack else name

    def _get_parent_node(self, parent_stack):
        if not parent_stack:
            return None
        path = ".".join(parent_stack)
        return self.all_nodes.get(path)
