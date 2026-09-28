# SCL Language Support (Siemens)

Language support for Siemens SCL (Structured Control Language), the ST-family
language used in Siemens TIA Portal for programming S7 PLCs. This extension
runs a bundled Python language server so you get diagnostics, hover info, and
completion for `.scl` files directly in VS Code — **no Python installation
required**.

<!-- TODO: add a screenshot or GIF of diagnostics/hover/completion in action here -->

## Features

- **Syntax highlighting** for SCL keywords, control-flow statements, data
  types, built-in functions, numeric/typed literals, strings, and comments
  (via a TextMate grammar, `syntaxes/scl.tmLanguage.json`).
- **Diagnostics**, computed from the declaration section and the code after
  `BEGIN`:
  - Missing semicolons on assignment statements and `END_IF` lines (with
    support for multiline statements/function calls and boolean-operator
    line continuations).
  - Undefined variables — identifiers used in assignments that were never
    declared in a `VAR`/`VAR_INPUT`/`VAR_OUTPUT`/`VAR_IN_OUT`/`VAR_TEMP`/
    `CONST` block (case-insensitive, matching SCL semantics). Function block
    call argument names, typed/based numeric literals (`T#5s`, `16#FF`,
    `INT#5`, ...), and string literals are correctly excluded.
  - `IF`/`END_IF` structure checks: a missing `THEN`, a missing `END_IF`, an
    `END_IF` missing its trailing semicolon, and empty `ELSE` blocks.
  - Variable name length/prefix collisions: identifiers longer than 24
    characters, and two identifiers in the same scope (global, or within the
    same `STRUCT`) that share their first 24 characters and would therefore
    collide in TIA Portal.
- **Hover** information for variables and struct fields, including their
  declared type, default value, and any trailing declaration comment.
  Hovering over a specific segment of a dotted path (`a.b.c`) shows info for
  just that segment.
- **Completion** for top-level variables and, after a `.`, for the fields of
  a struct-typed variable.
- **Bracket-match highlighting** for `()`, `[]`, and `{}`.

## Supported platforms

Prebuilt, platform-specific packages are published for:

- **Windows** (`win32-x64`)
- **macOS** (`darwin-arm64`, via CI)
- **Linux** (`linux-x64`, via CI)

Each package bundles a standalone server executable for its platform, so
end users never need a separate Python install.

## Known limitations

- The parser is **regex/line-based**, not a real tokenizer or grammar, so it
  can be tripped up by unusual formatting — particularly multiline function
  calls, structs, and statements that wrap across several lines.
- Analysis is focused on the **declaration section** (`VAR*`/`CONST`/
  `STRUCT` blocks) and simple statements after `BEGIN`. Deeper control-flow
  or data-flow analysis of the executable body is out of scope.
- Diagnostics are heuristic checks, not a full SCL/TIA Portal compiler —
  treat them as linting aids, not a substitute for compiling in TIA Portal.

## Development

Client (TypeScript, run from the repo root):

```bash
npm run compile        # type-check + lint + esbuild bundle to dist/extension.js
npm run watch          # esbuild + tsc in watch mode
npm run check-types    # tsc --noEmit
npm run lint           # eslint client/src
npm run package        # production build (minified, no sourcemaps)
npm test               # compiles tests + extension + lints, then runs vscode-test
```

Server (Python, run from `server/scl_server/`, this project uses
[`uv`](https://github.com/astral-sh/uv) for environment/dependency
management):

```bash
uv venv .venv
uv pip install -p .venv/bin/python -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest                        # run the whole server test suite
.venv/bin/pytest server/tests/test_diagnostics.py -k undefined_variable  # a single test
```

Building the standalone server binary with PyInstaller (from the repo root):

```bash
python -m PyInstaller scl_server.spec   # produces dist/SCLserver/
```

Packaging the `.vsix` for a specific platform (after building the matching
server binary above):

```bash
npx @vscode/vsce package --target win32-x64
```

See `CLAUDE.md` for the full architecture overview and the "Publishing"
section for how tagged releases are built and published by CI.

## Release notes

See [CHANGELOG.md](./CHANGELOG.md) for the full history of changes.
