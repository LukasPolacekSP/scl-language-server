"""Smoke test that main.py wires up every LSP feature it's supposed to.

Intercepts the LanguageServer.feature(...) decorator itself rather than
inspecting any particular server implementation's internal storage, so it
passes whether pygls or the offline stub (tests/stubs/pygls) is active.
This is a cheap guard against a future refactor accidentally dropping a
handler registration.
"""
import sys

import pygls.server


def test_main_registers_all_lsp_features(monkeypatch):
    registered = []
    original_feature = pygls.server.LanguageServer.feature

    def spy_feature(self, feature_name, *args, **kwargs):
        registered.append(feature_name)
        return original_feature(self, feature_name, *args, **kwargs)

    monkeypatch.setattr(pygls.server.LanguageServer, "feature", spy_feature)
    sys.modules.pop("main", None)

    import main  # noqa: F401

    assert set(registered) == {
        "textDocument/completion",
        "textDocument/hover",
        "textDocument/documentHighlight",
        "textDocument/didOpen",
        "textDocument/didChange",
    }
