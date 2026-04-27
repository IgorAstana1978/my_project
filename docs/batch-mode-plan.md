# Batch Mode Plan

## Goal
Add a `batch` subcommand that reads operations from a file and executes them sequentially, reusing existing execution logic without duplicating code.

## Command
```bash
python -m src.main batch <file>
```

## Input File Format
Each line contains one operation in the format:
```
<operation> <a> <b>
```

Example (`operations.txt`):
```
add 2 3
mul 4 5
div 10 2
```

- `<operation>`: any valid operation name or alias (add, sub, mul, div, pow, mod, sum, sub, etc.)
- `<a>` and `<b>`: numeric arguments (integers or floats)
- Lines starting with `#` are treated as comments and ignored
- Empty lines are skipped

## Expected Behavior
1. Parse the file path argument
2. Read the file line by line
3. For each valid line:
   - Parse operation name → resolve via `ALIASES_TO_NAME`
   - Parse operands → use `parse_number()`
   - Execute → call function from `FUNCS_BY_NAME`
   - Format result → use `format_result()`
   - Print output in the same format as CLI subcommands
4. Exit with code 0 on success
5. **Stop on first error** — exit immediately with non-zero code

## Error Handling
- **File not found**: print error and exit with code 1
- **Invalid operation**: print error for that line, exit with code 1
- **Invalid number**: print error for that line, exit with code 1
- **Division by zero**: print error for that line, exit with code 1
- **Malformed line**: print error for that line, exit with code 1

## Reused Code Paths
The following existing components will be reused:

| Component | Location | Purpose |
|-----------|----------|---------|
| `OPERATION_SPECS` | `src/main.py:14-21` | Defines all operations with aliases |
| `ALIASES_TO_NAME` | `src/main.py:50` | Resolves operation/alias to canonical name |
| `FUNCS_BY_NAME` | `src/main.py:50` | Maps canonical name to callable function |
| `resolve_operation()` | `src/main.py:56-64` | Parses operation string → (name, func) |
| `parse_number()` | `src/main.py:34-39` | Parses string → float with error message |
| `format_result()` | `src/main.py:26-30` | Formats float output (int if whole) |
| `calculator.py` functions | `src/calculator.py:1-30` | Actual math operations |

No changes needed to `src/calculator.py` — all math functions already exist.

## Tests
New tests to add in `tests/test_batch.py` (not implemented yet):

- `test_batch_file_not_found()` — file does not exist
- `test_batch_empty_file()` — file with no valid operations
- `test_batch_single_operation()` — one line
- `test_batch_multiple_operations()` — multiple lines
- `test_batch_with_aliases()` — using short aliases (sum, sub, etc.)
- `test_batch_invalid_operation()` — unknown operation
- `test_batch_invalid_number()` — non-numeric operand
- `test_batch_division_by_zero()` — division by zero error
- `test_batch_comment_lines()` — lines starting with #
- `test_batch_empty_lines()` — blank lines
- `test_batch_malformed_line()` — wrong number of arguments

## Documentation Updates
- Update `README.md` — add `batch` command to usage examples
- Update `CHANGELOG.md` — add entry under "Added" in Unreleased

## Definition of Done
- [ ] `batch` subcommand implemented in `src/main.py`
- [ ] Reuses existing operation registry, aliases, parsing, formatting
- [ ] No changes to `src/calculator.py`
- [ ] Tests added in `tests/test_batch.py`
- [ ] Tests pass (100% coverage maintained)
- [ ] `ruff`, `black`, `mypy` pass
- [ ] README.md updated
- [ ] CHANGELOG.md updated

## Risks
- **File encoding**: assume UTF-8; may need to handle other encodings
- **Large files**: no streaming — entire file is read; could be a concern for very large files
