# Day 13 Batch Backlog

## Immediate Safe Task

- Goal: Fix the README batch example so it matches actual output: `multiply 3 7 = 21`.
- Files likely to change: `README.md`
- Risk level: low
- Checks to run: manually compare the README example with current batch output format.

## Later Refactor Task

- Goal: Extract a shared helper for executing one operation and formatting the result line, then use it from both interactive and batch flows.
- Files likely to change: CLI/calculator source files that currently handle interactive and batch operation execution.
- Risk level: medium
- Checks to run: existing CLI and batch tests, plus a quick manual interactive calculation.

## Documentation Task

- Goal: Document batch behavior when an error occurs after earlier successful lines, including that earlier stdout output may already be printed before the command exits with code 1.
- Files likely to change: `README.md`
- Risk level: low
- Checks to run: manually review the batch section for clarity and consistency with existing tests.

## Test Coverage Task

- Goal: Add focused coverage for batch help and top-level CLI help listing the `batch` command.
- Files likely to change: CLI test files.
- Risk level: low
- Checks to run: targeted CLI help tests, then the full existing test suite.

## Deferred Ideas

- Narrow `run_batch` error handling so unexpected programming errors are not hidden as normal batch input errors.
- Decide whether inline comments are supported, then document or test that behavior.
- Consider streaming batch files line by line instead of loading the whole file with `readlines()`.
- Add tests around the exact partial-output behavior if that behavior becomes part of the public contract.

## Recommended Order Of Work

1. Fix the README output example.
2. Document partial-output behavior for batch errors.
3. Add CLI help coverage for `batch`.
4. Refactor shared operation execution and result formatting.
5. Narrow batch error handling while the refactor is fresh.
6. Revisit streaming and inline-comment behavior only if batch files become larger or usage expectations change.
