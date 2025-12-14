# Change Log

All notable changes to the "scl-language-support" extension will be documented in this file.

Check [Keep a Changelog](http://keepachangelog.com/) for recommendations on how to structure this file.

## [0.0.3] - 2025-12-14

### Fixed
- Fixed syntax error in parser_structured.py (incomplete if statement)
- Fixed semicolon checking for multiline parentheses and function calls
- Fixed function arguments being marked as undefined variables
- Fixed struct field validation - now properly reports errors for non-existent struct fields
- Fixed shared parser instance issue - diagnostics and handlers now use the same parser singleton

### Added
- Support for time notation literals (50s, 6ms, 2h, 30m, 1d) - no longer marked as undefined
- Support for function return variables (function.var) - excluded from undefined checks
- Parser singleton module to ensure consistent parser state across all modules
- Improved multiline function call argument detection and parsing

### Improved
- Semicolon diagnostics now properly skip lines inside function call parentheses
- Parser now correctly handles multiline function calls with arguments
- Function block arguments are properly tracked and recognized

## [0.0.2]

- Initial release