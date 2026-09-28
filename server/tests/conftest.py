"""Pytest configuration for the SCL language server test suite.

The server modules (server/scl_server/*.py) are flat, non-package modules
imported by bare name (e.g. `import parser_structured`), matching how
PyInstaller loads them (see ../../scl_server.spec, whose `pathex` points at
the same directory). We add that directory to sys.path so the same import
style works under pytest.

This suite prefers the real `pygls`/`lsprotocol` packages (see
requirements.txt) whenever they're importable. If they aren't (e.g. no
network access to a package index), it falls back to the light-weight
stand-ins in tests/stubs/, which mirror just the slice of the pygls/
lsprotocol API this server touches. Either way, the tests exercise the
same server code through the same fakes defined below.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent
SERVER_SRC = TESTS_DIR.parent / "scl_server"
STUBS_DIR = TESTS_DIR / "stubs"
FIXTURES_DIR = TESTS_DIR / "fixtures"

if importlib.util.find_spec("pygls") is None or importlib.util.find_spec("lsprotocol") is None:
    sys.path.insert(0, str(STUBS_DIR))

sys.path.insert(0, str(SERVER_SRC))

import parser_structured  # noqa: E402  (must follow the sys.path setup above)


@pytest.fixture(autouse=True)
def reset_parser_singleton():
    """The server keeps ONE global parser instance (see get_parser() in
    parser_structured.py) shared by every document the handlers touch.
    Reset it around each test so tests don't leak state into each other.

    Note this is also true at runtime, not just in tests: today, two SCL
    files open in the editor at once share the same parser instance, so
    whichever one was parsed last "wins" for hover/completion/diagnostics
    on the other. See the upgrade notes shared alongside this test suite.
    """
    parser_structured._parser_instance = None
    yield
    parser_structured._parser_instance = None


class FakeWorkspace:
    """Duck-types the slice of pygls.workspace.Workspace the server calls."""

    def __init__(self):
        self._docs = {}

    def add(self, doc):
        self._docs[doc.uri] = doc
        return doc

    def get_document(self, uri):
        return self._docs[uri]

    def get_text_document(self, uri):
        return self._docs[uri]


class FakeLanguageServer:
    """Duck-types the slice of pygls.server.LanguageServer that handlers.py
    and diagnostics.py call, and records what they did so tests can assert
    on it instead of needing a real LSP client/transport."""

    def __init__(self):
        self.workspace = FakeWorkspace()
        self.published_diagnostics = []
        self.logs = []

    def show_message_log(self, message, *args, **kwargs):
        self.logs.append(message)

    def publish_diagnostics(self, uri, diagnostics):
        self.published_diagnostics.append((uri, diagnostics))


class FakeDocument:
    """Duck-types the slice of pygls.workspace.TextDocument the server
    reads: `.source`, `.lines` (splitlines keeping line endings, matching
    pygls' own TextDocument.lines), and `.uri`."""

    def __init__(self, source: str, uri: str = "file:///test.scl"):
        self.source = source
        self.uri = uri

    @property
    def lines(self):
        return self.source.splitlines(keepends=True)


@pytest.fixture
def fake_ls():
    return FakeLanguageServer()


def load_fixture(name: str) -> str:
    """Read a raw .scl sample from tests/fixtures/.

    These fixtures are plain SCL source text with no Python in them, on
    purpose: test_diagnostics.py's expectations (defined in Python, next to
    each fixture name) are the only Python-specific part. If this project is
    ever rewritten in another language, the .scl files themselves carry over
    unchanged as the input corpus for an equivalent test suite there.
    """
    return (FIXTURES_DIR / name).read_text()
