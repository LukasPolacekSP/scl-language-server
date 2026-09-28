"""Minimal stand-in for `pygls.server`, used only when the real `pygls`
package isn't installed. See tests/stubs/lsprotocol/types.py for why this
exists and when it's used.
"""


class LanguageServer:
    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version
        self._features = {}

    def feature(self, feature_name, *args, **kwargs):
        def decorator(fn):
            self._features[feature_name] = fn
            return fn
        return decorator

    def show_message_log(self, message, *args, **kwargs):
        pass

    def publish_diagnostics(self, uri, diagnostics):
        pass

    def start_io(self):
        pass
