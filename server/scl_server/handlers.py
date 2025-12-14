import re
from lsprotocol.types import (
    CompletionItem,
    CompletionParams,
    Hover,
    HoverParams,
    MarkupContent,
    MarkupKind,
    DocumentHighlightParams,
    DocumentHighlight,
    DocumentHighlightKind,
    Range,
    Position,
    Diagnostic, 
    DiagnosticSeverity
)
from pygls.server import LanguageServer
from pygls.workspace import Document

from parser_structured import get_parser, update_parser

def find_hover_token_with_segment(line: str, char: int) -> tuple[str, int] | None:
    if char > len(line):
        return None
    start = char
    end = char

    while start > 0 and (line[start - 1].isalnum() or line[start - 1] in '._'):
        start -= 1
    while end < len(line) and (line[end].isalnum() or line[end] in '._'):
        end += 1

    token = line[start:end]
    if not token:
        return None

    relative_pos = char - start
    segments = token.split(".")
    seg_index = 0
    offset = 0

    for i, seg in enumerate(segments):
        if offset <= relative_pos <= offset + len(seg):
            seg_index = i
            break
        offset += len(seg) + 1  # +1 for dot

    return token, seg_index

def handle_hover(ls: LanguageServer, params: HoverParams) -> Hover | None:
    doc = ls.workspace.get_document(params.text_document.uri)
    update_parser(doc)

    line = doc.lines[params.position.line]
    char = params.position.character

    token_info = find_hover_token_with_segment(line, char)
    if not token_info:
        return None

    full_token, segment_index = token_info
    path = full_token.split('.')
    target_path = path[:segment_index + 1]
    full_path_str = ".".join(target_path)

    parser = get_parser()
    node = parser.all_nodes.get(full_path_str)
    if not node:
        return None

    # Build comment chain
    comment_chain = []
    for i in range(len(target_path)):
        sub_path = ".".join(target_path[:i+1])
        n = parser.all_nodes.get(sub_path)
        if n and n.comment:
            comment_chain.append(n.comment)
    comment_str = ", ".join(comment_chain) if comment_chain else ""

    if node.data_type == "STRUCT":
        type_str = "Type: STRUCT"
        comment_out = f"\nComment:\n{comment_str}" if comment_str else ""
        result = f"{type_str}{comment_out}"
    else:
        type_str = f"Type: {node.data_type}"
        default_str = f"\nDefault: {node.default}" if node.default else ""
        comment_out = f"\nComment: {comment_str}" if comment_str else ""
        result = f"{type_str}{default_str}{comment_out}"

    return Hover(contents=MarkupContent(kind=MarkupKind.PlainText, value=result))

def handle_completion(ls: LanguageServer, params: CompletionParams) -> list[CompletionItem]:
    doc = ls.workspace.get_document(params.text_document.uri)
    update_parser(doc)

    line = doc.lines[params.position.line][:params.position.character]
    match = re.search(r'([\w.]+)$', line)
    if not match:
        return []

    full_path = match.group(1)
    path_parts = full_path.split('.')
    prefix = path_parts[-1]
    path = path_parts[:-1]
    parent_path_str = ".".join(path) if path else None

    parser = get_parser()
    if parent_path_str:
        parent_node = parser.all_nodes.get(parent_path_str)
        candidates = list(parent_node.children.keys()) if parent_node and parent_node.children else []
    else:
        candidates = list(parser.variables.keys())

    filtered = [c for c in candidates if c.startswith(prefix)]
    return [CompletionItem(label=s) for s in filtered]

def handle_highlight(ls: LanguageServer, params: DocumentHighlightParams) -> list[DocumentHighlight]:
    doc = ls.workspace.get_document(params.text_document.uri)
    lines = doc.lines
    pos = params.position

    if pos.line >= len(lines):
        return []

    line = lines[pos.line]
    if pos.character >= len(line):
        return []

    char = line[pos.character]
    pairs = {'(': ')', ')': '(', '{': '}', '}': '{', '[': ']', ']': '['}
    openers = '([{'
    closers = ')]}'

    def find_match(lines, line_idx, char_idx, open_br, close_br, forward=True):
        stack = 1
        if forward:
            for l in range(line_idx, len(lines)):
                line_text = lines[l]
                r = range(char_idx + 1, len(line_text)) if l == line_idx else range(len(line_text))
                for c in r:
                    if line_text[c] == open_br:
                        stack += 1
                    elif line_text[c] == close_br:
                        stack -= 1
                        if stack == 0:
                            return Position(line=l, character=c)
        else:
            for l in range(line_idx, -1, -1):
                line_text = lines[l]
                r = range(char_idx - 1, -1, -1) if l == line_idx else range(len(line_text) - 1, -1, -1)
                for c in r:
                    if line_text[c] == close_br:
                        stack += 1
                    elif line_text[c] == open_br:
                        stack -= 1
                        if stack == 0:
                            return Position(line=l, character=c)
        return None

    if char in openers:
        match = find_match(lines, pos.line, pos.character, char, pairs[char], forward=True)
    elif char in closers:
        match = find_match(lines, pos.line, pos.character, pairs[char], char, forward=False)
    else:
        return []

    if match:
        return [
            DocumentHighlight(
                range=Range(start=pos, end=Position(line=pos.line, character=pos.character + 1)),
                kind=DocumentHighlightKind.Text,
            ),
            DocumentHighlight(
                range=Range(start=match, end=Position(line=match.line, character=match.character + 1)),
                kind=DocumentHighlightKind.Text,
            ),
        ]
    return []

