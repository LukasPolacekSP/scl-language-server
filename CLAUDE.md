# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A VS Code extension (`scl-language-support`) that provides language support for Siemens SCL (Structured Control Language, used in Siemens TIA Portal/PLC programming). It has two halves:

- **Client** (`client/src/extension.ts`): a thin TypeScript VS Code extension that bundles with esbuild and launches the language server as a subprocess via `vscode-languageclient`.
- **Server** (`server/scl_server/`): a Python LSP server built on `pygls`/`lsprotocol`, packaged into a standalone executable with PyInstaller so the extension doesn't require the user to have Python installed.

The client always launches the server from `dist/SCLserver/server.exe` (see `client/src/extension.ts`) — there is no "run server from source" dev mode wired up. To test server changes against the extension, you must rebuild the PyInstaller binary first (see below).

## Common commands

Client (TypeScript, run from repo root):
```bash
npm run compile        # type-check + lint + esbuild bundle to dist/extension.js
npm run watch          # esbuild + tsc in watch mode (two parallel watchers)
npm run check-types    # tsc --noEmit
npm run lint           # eslint client/src
npm run package        # production build (minified, no sourcemaps)
npm test               # compiles tests + extension + lints, then runs vscode-test
```

There is currently no test suite under `client/src` (`.vscode-test.mjs` points at `out/test/**/*.test.js`, which doesn't exist yet), so `npm test` will currently find no tests to run.

Server (Python, run from `server/scl_server/`, needs `pip install -r requirements.txt`):
```bash
python main.py                          # run the LSP server directly over stdio (for manual/debug use)
python -m PyInstaller ../../scl_server.spec   # build the standalone server.exe used by the extension
```

The PyInstaller spec (`scl_server.spec`) builds from `server/scl_server/main.py` and explicitly lists the server's own modules (`parser_structured`, `handlers`, `diagnostics`, `syntax_keywords`, `scl_text`) as `hiddenimports` — if you add a new server module, add it there too or PyInstaller will silently omit it from the frozen build.

Packaging the extension for distribution:
```bash
python -m PyInstaller scl_server.spec   # from repo root, produces dist/SCLserver/
vsce package                            # produces the .vsix
```

Server unit tests (pytest, `server/tests/`), from the repo root:
```bash
uv venv .venv
uv pip install -p .venv/bin/python -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest                        # run the whole suite
.venv/bin/pytest server/tests/test_diagnostics.py -k undefined_variable  # a single test
```
This project uses `uv` for all Python environment/dependency management — prefer it over bare `pip`/`venv`.

If `pygls`/`lsprotocol` aren't installed (e.g. no network access to a package index), the tests fall back to light-weight stand-ins in `server/tests/stubs/` that mirror just the slice of those libraries' API the server touches — see `server/tests/conftest.py`.

`server/tests/test_diagnostics.py` and `server/tests/test_handlers.py` are **behavior/contract tests**: they feed whole `.scl` files (in `server/tests/fixtures/`) through `run_diagnostics`/`handle_hover`/`handle_completion` and assert on the LSP-shaped output, without touching the parser's internal data structures. They're written to survive the planned parser rewrite (regex/dict-based → trie/word-tree) and even a port to a different implementation language — the `.scl` fixtures are the portable part. `server/tests/test_parser_structured.py`, by contrast, asserts directly on `VariableNode`/`all_nodes` and is expected to need rewriting alongside the parser itself.

## Architecture

### Server: parser + diagnostics + handlers

The server keeps a single module-level singleton parser (`parser_structured.get_parser()` / `update_parser(doc)`), rebuilt from the full document text on every `didOpen`/`didChange`. All LSP features (`diagnostics.py`, `handlers.py`) call `get_parser()` to read the same parsed state — there is one source of truth for "what variables/structs exist," not per-feature re-parsing.

`StructuredSCLParser` (`parser_structured.py`) does a **line-oriented, regex-based** parse (not a real grammar/AST) of the SCL declaration section, building a tree of `VariableNode`s:
- Walks `VAR`/`VAR_INPUT`/`VAR_OUTPUT`/`VAR_IN_OUT`/`VAR_TEMP`/`CONST` blocks (declarative part) until `BEGIN` is reached.
- Tracks nested `STRUCT ... END_STRUCT` blocks via a `parent_stack`, so struct fields get dotted full paths (e.g. `MyStruct.Field`) in `all_nodes`, while `variables` holds only top-level declarations.
- `all_nodes` is the flat lookup used for hover/completion/undefined-variable checks; `variables` is used for top-level completion and the "declared vars" set in diagnostics.
- After `BEGIN`, it only handles function block calls (`_handle_function_block_call`), registering call arguments as `fb_argument` children so they aren't flagged as undefined variables downstream.

Because parsing is regex/line-based rather than a proper tokenizer, most bugs in this codebase are edge cases in multiline handling (function calls spanning lines, structs, semicolon-at-end-of-continuation checks) — when fixing a parser bug, check `CHANGELOG.md` first, several past fixes were exactly this class of issue.

`diagnostics.py` runs three independent checks per document (`check_assignments`, `check_if_blocks`, `check_variable_prefix_collisions`) and concatenates their results before publishing. Each check re-scans `doc.lines` itself (they don't share intermediate state beyond the parser singleton), so a new diagnostic rule should generally be added as its own `check_*` function rather than threaded into an existing one.

`handlers.py` implements hover, completion, and bracket-match document-highlight. Hover/completion resolve dotted paths (`a.b.c`) by walking `all_nodes`/`children` segment by segment — `find_hover_token_with_segment` maps a cursor column back to which dot-segment of a token it's inside, so hovering over `a` vs `b` in `a.b.c` shows different info.

### Syntax highlighting

`syntaxes/scl.tmLanguage.json` is a separate TextMate grammar registered via `package.json`'s `contributes.grammars`, independent of the LSP server — it drives static highlighting while the server drives diagnostics/hover/completion.

### Keyword tables

`syntax_keywords.py` centralizes all SCL keyword sets (control flow, data types, declaration keywords, etc.) into a unified `SCL_KEYWORDS` set. Both the parser and diagnostics import from here — add new keywords in one place.

### Shared lexical helpers

`scl_text.py` centralizes small text-handling helpers used by both `parser_structured.py` and `diagnostics.py`: `strip_comment`/`extract_comment` for `//` comments, `find_paren_close` for tracking multiline paren depth (the one implementation shared by the parser's function-block-call handling and diagnostics' unclosed-call/missing-semicolon checks), and the `STRUCT_START_RE`/`STRUCT_END_RE` regexes both modules match `STRUCT`/`END_STRUCT` lines against.

## Publishing

Releases are built and published entirely by `.github/workflows/release.yml`. To cut a release:

1. Bump `version` in `package.json` and add a matching section to `CHANGELOG.md`.
2. Push a tag matching `vX.Y.Z` (e.g. `git tag v0.0.4 && git push origin v0.0.4`), or trigger the workflow manually via `workflow_dispatch`.
3. CI then, per platform (`windows-latest` → `win32-x64`, `macos-latest` → `darwin-arm64`, `ubuntu-latest` → `linux-x64`): runs the server test suite, builds the server binary with PyInstaller (`pyinstaller scl_server.spec` from the repo root), and packages a platform-specific VSIX with `vsce package --target <target>`.
4. On a tag push (not `workflow_dispatch`), a `publish` job downloads all three VSIXs and attaches them to a GitHub Release and publishes them to the Visual Studio Marketplace and Open VSX when the matching secrets are set.

Optional repository secrets (each publish step is skipped when its secret is unset):
- `VSCE_PAT` — a Visual Studio Marketplace Personal Access Token for the `Slickus` publisher. Creating one requires an Azure DevOps organization linked to an Azure subscription, so it is currently **not set**: the Marketplace release is done by hand — download the VSIX from the GitHub Release and upload it at https://marketplace.visualstudio.com/manage (extension ⋯ menu → Update).
- `OVSX_PAT` — an Open VSX access token.

To package a VSIX manually for a single platform (e.g. to test locally), build the matching server binary first, then:
```bash
python -m PyInstaller scl_server.spec   # from repo root; produces dist/SCLserver/
npx @vscode/vsce package --target win32-x64   # or darwin-arm64 / linux-x64 / etc.
```

`npm run vsce:package` runs a plain `vsce package` (no `--target`) against whatever is currently in `dist/SCLserver/`, useful for a quick local sanity check of the current platform's build.
