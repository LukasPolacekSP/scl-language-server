"""Minimal stand-in for the real `lsprotocol.types` module.

This test suite prefers the real `pygls`/`lsprotocol` packages (see
requirements.txt) whenever they're importable - conftest.py only puts this
stubs/ directory on sys.path as a fallback, for offline environments or CI
runners that can't reach a package index. It mirrors the small slice of the
LSP type surface the server actually touches (same field names, same
DiagnosticSeverity/MarkupKind values as the LSP spec), so tests behave the
same whichever one is loaded. If you extend the server to use more of
lsprotocol.types, extend this stub to match, or just rely on the real
package being installed in your environment.
"""
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Optional


class DiagnosticSeverity(IntEnum):
    Error = 1
    Warning = 2
    Information = 3
    Hint = 4


class MarkupKind:
    PlainText = "plaintext"
    Markdown = "markdown"


class DocumentHighlightKind(IntEnum):
    Text = 1
    Read = 2
    Write = 3


@dataclass
class Position:
    line: int
    character: int


@dataclass
class Range:
    start: Position
    end: Position


@dataclass
class Diagnostic:
    range: Range
    message: str
    severity: Optional[DiagnosticSeverity] = None
    source: Optional[str] = None


@dataclass
class MarkupContent:
    kind: str
    value: str


@dataclass
class Hover:
    contents: Any


@dataclass
class CompletionItem:
    label: str


@dataclass
class DocumentHighlight:
    range: Range
    kind: Optional[DocumentHighlightKind] = None


@dataclass
class TextDocumentIdentifier:
    uri: str


@dataclass
class HoverParams:
    text_document: TextDocumentIdentifier
    position: Position


@dataclass
class CompletionParams:
    text_document: TextDocumentIdentifier
    position: Position


@dataclass
class DocumentHighlightParams:
    text_document: TextDocumentIdentifier
    position: Position


@dataclass
class DidOpenTextDocumentParams:
    text_document: Any


@dataclass
class DidChangeTextDocumentParams:
    text_document: Any


TEXT_DOCUMENT_COMPLETION = "textDocument/completion"
TEXT_DOCUMENT_HOVER = "textDocument/hover"
TEXT_DOCUMENT_DOCUMENT_HIGHLIGHT = "textDocument/documentHighlight"
TEXT_DOCUMENT_DID_OPEN = "textDocument/didOpen"
TEXT_DOCUMENT_DID_CHANGE = "textDocument/didChange"
