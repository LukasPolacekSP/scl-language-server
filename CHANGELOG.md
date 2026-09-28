# Change Log

All notable changes to the "scl-language-support" extension will be documented in this file.

Check [Keep a Changelog](http://keepachangelog.com/) for recommendations on how to structure this file.

## [0.1.0] - 2026-09-28

### Added

- `language-configuration.json` (comments, brackets, auto-closing/surrounding pairs, indentation rules, folding markers, and a `#`/dotted-name-aware `wordPattern`) - previously referenced by `package.json` but missing from the repo
- Platform-specific packaging: `.github/workflows/release.yml` now builds and publishes per-platform VSIXs (`win32-x64`, `darwin-arm64`, `linux-x64`) on `v*` tags, and `.github/workflows/ci.yml` runs the server test suite and client build on every push/PR to `main`
- `npm run vsce:package` script for quick local VSIX packaging
- A `images/icon.png` extension icon and a matching `galleryBanner` color in `package.json`
- A "Publishing" section in `CLAUDE.md` describing the release/tagging process and required secrets

### Changed

- Rewrote `README.md` as a proper Marketplace listing (features, supported platforms, known limitations, development/build instructions, release notes pointer)
- `.vscodeignore` now excludes everything by default and re-includes only the runtime-needed files (`package.json`, `README.md`, `CHANGELOG.md`, `LICENSE`, `language-configuration.json`, `dist/extension.js`, `dist/SCLserver/**`, `syntaxes/**`, `images/icon.png`), so `.venv/`, `server/`, `client/src/`, PyInstaller's `build/`, and tests are no longer packaged into the VSIX
- `package.json`: fixed `repository.url` to point at the actual git remote, added `bugs.url`/`homepage`, a proper `displayName`/`description`, a `keywords` array, and removed the invalid `contributes.capabilities` block
- `client/src/extension.ts` now verifies the server binary exists before launching (showing a clear error message instead of failing silently) and, on non-Windows platforms, attempts to restore the executable bit (`chmodSync`) if VSIX extraction dropped it

### Fixed

- `FOR i := 0 TO 10 DO` and other control-flow headers (`WHILE ... DO`, `CASE ... OF`, `ELSIF ... THEN`, ...) no longer produce a false "Missing semicolon" diagnostic just because they contain a `:=`
- Declaration lines (inside `VAR`/`CONST` blocks) are no longer run through the undefined-variable/semicolon checks meant for code after `BEGIN` - e.g. `x : INT := zz;` no longer reports `zz` as undefined
- An identifier starting with `Begin` (e.g. `BeginTime : TIME;`) is no longer mistaken for the `BEGIN` keyword by the parser, and `BEGIN // comment` now correctly starts the code section for diagnostics (both now share one `is_begin()` helper in `scl_text.py`)
- `check_if_blocks` no longer matches keywords as substrings of identifiers (e.g. `IFace`, `bTHENx`) - it now uses word-boundary regexes on comment-stripped code, restricted to lines after `BEGIN`
- Fixed a typo ("statment" -> "statement") in the "END_IF missing" diagnostic message
- Control structures written as `IF (...)`, `WHILE (...)`, `NOT(...)`, `ELSIF (...)`, `CASE (...)` are no longer misregistered by the parser as function block calls
- Function block call argument names (e.g. `IN`, `PT` in `myFB(IN := x, PT := T#5s)`) are no longer registered as bare global variable names - that previously hid genuinely undefined uses of the same name elsewhere in the document; only the argument *values* are now checked for being undefined
- `hover` and `completion` no longer raise `IndexError` when the cursor is on the blank line past the end of the document
- Typed/hex/based literals (`16#FF`, `2#1010`, `8#17`, `INT#5`, `DINT#-3`, `T#5s`, `TIME#1h`, `REAL#1.5`, `W#16#FF`), float exponent literals (`1.0E3`), and quoted strings (`'...'`, `"..."`) are no longer misreported as undefined variables
- Plain (untyped) `CONST` values, e.g. `MAX_LEN := 10;`, are now recognized by the parser (previously only the typed form `NAME := TYPE#value;` was)
- Variable lookups are now case-insensitive, matching SCL semantics - a variable declared `Counter` and used as `counter` is no longer flagged as undefined, and hover/completion resolve differently-cased references too
- Undefined-variable diagnostics now point at the correct column (a word-boundary match) instead of the first substring occurrence - e.g. `iRes` is no longer underlined inside `iResult`
- The VS Code client now launches `server` (not `server.exe`) on non-Windows platforms
- `requirements.txt` was UTF-16LE with CRLF line endings and didn't pin a `pygls` version; converted to UTF-8/LF and now pins `pygls>=1.3,<2`

### Changed

- Refactored `parser_structured.py`, `diagnostics.py`, and `handlers.py` into smaller, single-purpose functions/methods (e.g. `_register`, `_lines_inside_calls`, `_undefined_variable_diagnostics`, `_missing_semicolon_diagnostic`, `_find_matching_bracket`), and extracted the lexical helpers duplicated between the parser and diagnostics (`strip_comment`, `extract_comment`, `find_paren_close`, the `STRUCT`/`END_STRUCT` regexes) into a new shared `scl_text.py` module
- The parser now caches the last-parsed source text and skips re-parsing entirely when the document hasn't changed
- The parser's declaration-section and body-section parsing are now two separate passes (`_parse_declarations` / `_parse_body`) instead of one loop toggling between modes
- Removed dead code (`VariableNode.to_dict()`, an unused `defaultdict` import, duplicated forward/backward bracket-matching logic in `handle_highlight`, a noisy per-keystroke `show_message_log` call, and duplicated declared-vars bookkeeping in `check_assignments` that overlapped with the parser's own `is_var_defined` check)
- `handlers.py` now uses `pygls`'s `get_text_document` instead of the older `get_document`
- `main.py`'s `did_open`/`did_change` handlers now share one `_lint()` helper instead of duplicating the diagnostics call
- `scl_server.spec` now lists `scl_text` as a `hiddenimport` (needed since it's a new module) and excludes unused stdlib modules (`tkinter`, `unittest`, `sqlite3`, ...) from the PyInstaller build to shrink it; UPX compression is now disabled

## [0.0.3] - 2025-12-14

### Fixed

- Fixed syntax error in parser_structured.py (incomplete if statement)
- Fixed semicolon checking for multiline parentheses and function calls
- Fixed function arguments being marked as undefined variables
- Fixed struct field validation - now properly reports errors for non-existent struct fields
- Fixed shared parser instance issue - diagnostics and handlers now use the same parser singleton
- Removed duplicate `is_empty_else_block` function

### Added

- Support for time notation literals (50s, 6ms, 2h, 30m, 1d) - no longer marked as undefined
- Support for function return variables (function.var) - excluded from undefined checks
- Improved multiline function call argument detection and parsing

### Improved

- Semicolon diagnostics now properly skip lines inside function call parentheses
- Parser now correctly handles multiline function calls with arguments
- Function block arguments are properly tracked and recognized
- Consolidated parser singleton into parser_structured module (removed redundant file)
- Removed build artifacts to reduce repository size

## [0.0.2]

- Initial release