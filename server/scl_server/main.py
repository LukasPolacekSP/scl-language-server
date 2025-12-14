from pygls.server import LanguageServer
from lsprotocol.types import (
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_HOVER,
    CompletionParams,
    HoverParams,
    Hover,
    TEXT_DOCUMENT_DOCUMENT_HIGHLIGHT, 
    DocumentHighlightParams, 
    DocumentHighlight,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_CHANGE,
    DidOpenTextDocumentParams, 
    DidChangeTextDocumentParams
)
from typing import Optional

from handlers import handle_hover, handle_completion, handle_highlight
from diagnostics import run_diagnostics

server = LanguageServer("scl-server", "v0.1.0")

@server.feature(TEXT_DOCUMENT_COMPLETION)
def completions(ls: LanguageServer, params: CompletionParams):
    return handle_completion(ls, params)

@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: LanguageServer, params: HoverParams) -> Optional[Hover]:
    return handle_hover(ls, params)

@server.feature(TEXT_DOCUMENT_DOCUMENT_HIGHLIGHT)
def highlight(ls: LanguageServer, params: DocumentHighlightParams) -> list[DocumentHighlight]:
    return handle_highlight(ls, params)

@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls, params: DidOpenTextDocumentParams):
    doc = ls.workspace.get_text_document(params.text_document.uri)
    run_diagnostics(ls, doc)

@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls, params: DidChangeTextDocumentParams):
    doc = ls.workspace.get_text_document(params.text_document.uri)
    ls.show_message_log(f"Document changed, running diagnostics on {len(doc.lines)} lines")
    run_diagnostics(ls, doc)

if __name__ == "__main__":
    server.start_io()
