"""Minimal stand-in for `pygls.workspace`, used only when the real `pygls`
package isn't installed. See tests/stubs/lsprotocol/types.py for why this
exists and when it's used.
"""


class Document:
    """Placeholder used only as a type-annotation target in the server
    modules. Tests use their own FakeDocument (see tests/conftest.py),
    which duck-types the `.source` / `.lines` / `.uri` surface of the real
    pygls TextDocument instead of subclassing this."""
    pass
