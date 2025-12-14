import re
from collections import defaultdict
from syntax_keywords import DECLARATION_KEYWORDS, DATA_TYPE_KEYWORDS, END_DECLARATION_KEYWORDS

VAR_BLOCKS = {
    "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR", "VAR_TEMP", "CONST",
}

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

    def to_dict(self):
        return {
            "name": self.name,
            "var_type": self.var_type,
            "data_type": self.data_type,
            "parent": self.parent.name if self.parent else None,
            "children": list(self.children.keys()),
            "default": self.default,
            "comment": self.comment,
            "block_type": self.block_type,
        }

class StructuredSCLParser:
    def __init__(self):
        self.variables = {}  # name -> VariableNode
        self.all_nodes = {}  # all VariableNodes by full path

    def parse(self, text: str):
        self.variables = {}
        self.all_nodes = {}
        lines = text.splitlines()
        block_type = None
        parent_stack = []
        current_parent = None
        declarative_part = True
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            upper = stripped.upper()
            if declarative_part:
                if upper.startswith("BEGIN"):
                    declarative_part = False
                    fb_names = self._get_function_block_names()
                    i += 1
                    continue
                # Sekvence zpracování
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
            else:
                consumed_lines = self._handle_function_block_call(lines, i, parent_stack)
                if consumed_lines > 0:
                    i += consumed_lines
                    continue
            i += 1

    def _handle_block_start_end(self, upper: str, block_type: str) -> str:
        if upper in DECLARATION_KEYWORDS:
            return upper
        if upper in END_DECLARATION_KEYWORDS:
            return None
        return block_type

    def _handle_structure_start(self, line: str, block_type: str, parent_stack: list, current_parent: VariableNode) -> bool:
        match = re.match(r"(?i)(\w+)\s*:\s*STRUCT\b", line)
        if match:
            name = match.group(1)
            node = VariableNode(
                name=name,
                var_type=self._block_to_vartype(block_type),
                data_type="STRUCT",
                parent=current_parent,
                comment=self._extract_comment(line),
                block_type=block_type
            )
            if current_parent:
                current_parent.add_child(node)
            else:
                self.variables[name] = node
            self.all_nodes[self._full_path(parent_stack, name)] = node
            parent_stack.append(name)
            return True
        return False
    
    def _handle_structure_end(self, line: str, parent_stack: list) -> bool:
        if re.match(r"(?i)END_STRUCT\s*;", line):
            if parent_stack:
                parent_stack.pop()
            return True
        return False
    
    def _handle_constant_definition(self, line: str, block_type: str, parent_stack: list, current_parent: VariableNode) -> bool:
        match = re.match(r"(?i)(\w+)\s*:=\s*([\w]+)#([^;]+)\s*;", line)
        if match and block_type == "CONST":
            name, data_type, value = match.groups()
            node = VariableNode(
                name=name,
                var_type="constant",
                data_type=data_type,
                parent=current_parent,
                default=value.strip(),
                comment=self._extract_comment(line),
                block_type=block_type
            )
            if current_parent:
                current_parent.add_child(node)
            else:
                self.variables[name] = node
            self.all_nodes[self._full_path(parent_stack, name)] = node
            return True
        return False
    
    def _handle_variable_declaration(self, line: str, block_type: str, parent_stack: list, current_parent: VariableNode) -> bool:
        match = re.match(r"(?i)(\w+)\s*:\s*([\w.]+)(?:\s*:=\s*([^;]+))?\s*;", line)
        if match:
            name, data_type, default = match.groups()
            node = VariableNode(
                name=name,
                var_type=self._block_to_vartype(block_type),
                data_type=data_type,
                parent=current_parent,
                default=default.strip() if default else None,
                comment=self._extract_comment(line),
                block_type=block_type
            )
            if current_parent:
                current_parent.add_child(node)
            else:
                self.variables[name] = node
            self.all_nodes[self._full_path(parent_stack, name)] = node
            return True
        return False
    
    def _handle_function_block_call(self, lines: list, start_idx: int, parent_stack: list):
        """
        Handle function block calls that may span multiple lines.
        Returns the number of lines consumed (0 if not a function call).
        """
        line = lines[start_idx].strip()
        match = re.match(r"(?i)(\w+)\s*\(\s*", line)
        if not match:
            return 0
            
        func_name = match.group(1)
        if func_name.upper() in DATA_TYPE_KEYWORDS:
            return 0  # Ignore type conversions like INT(), BOOL(), etc.

        # Create function block node
        node = VariableNode(
            name=func_name,
            var_type="function_block_call",
            data_type=None,
            parent=None,
            comment=self._extract_comment(line),
            block_type=None
        )
        self.all_nodes[self._full_path(parent_stack, func_name)] = node

        # Collect all lines until closing parenthesis
        full_call = line
        open_parens = line.count("(") - line.count(")")
        lines_consumed = 1
        
        while open_parens > 0 and start_idx + lines_consumed < len(lines):
            next_line = lines[start_idx + lines_consumed].split("//")[0].strip()
            full_call += " " + next_line
            open_parens += next_line.count("(") - next_line.count(")")
            lines_consumed += 1

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
            # Also add the argument by itself so it can be recognized
            self.all_nodes[arg] = arg_node

        return lines_consumed

    def _get_function_block_names(self) -> dict[str, VariableNode]:
        return {
            name: node
            for name, node in self.variables.items()
            if node.data_type not in DATA_TYPE_KEYWORDS
        }



    def _block_to_vartype(self, block_type):
        if block_type == "VAR_INPUT":
            return "input"
        if block_type == "VAR_OUTPUT":
            return "output"
        if block_type == "VAR_IN_OUT":
            return "inout"
        if block_type == "VAR":
            return "static"
        if block_type == "VAR_TEMP":
            return "temporary"
        if block_type == "CONST":
            return "constant"
        return "normal"

    def _full_path(self, parent_stack, name):
        return ".".join(parent_stack + [name]) if parent_stack else name

    def _get_parent_node(self, parent_stack):
        if not parent_stack:
            return None
        path = ".".join(parent_stack)
        return self.all_nodes.get(path)

    def _extract_comment(self, line: str) -> str:
        comment_index = line.find("//")
        if comment_index != -1:
            return line[comment_index + 2:].strip()
        return ""

    def get_variable(self, name: str) -> dict | None:
        node = self.all_nodes.get(name)
        return node.to_dict() if node else None

    def get_all_variables(self):
        return {name: node.to_dict() for name, node in self.all_nodes.items()}

    def get_children(self, name: str):
        node = self.all_nodes.get(name)
        if node:
            return [child.to_dict() for child in node.children.values()]
        return []

    