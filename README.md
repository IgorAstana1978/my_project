[![CI](https://github.com/IgorAstana1978/my_project/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/IgorAstana1978/my_project/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.14-blue)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)

# my_project

A small Python CLI calculator project with clean structure, automated checks, strict typing, full test coverage, and GitHub Actions CI.

## Features

- CLI calculator built with `argparse`
- subcommands and short aliases
- interactive mode
- command history and history reset
- function tests and CLI tests
- clean project structure for learning and practice

## Quality

- formatting with `black`
- linting with `ruff`
- type checking with `mypy`
- testing with `pytest`
- coverage with `pytest-cov`
- enforced **100% coverage**
- pre-commit hooks
- GitHub Actions on `push` and `pull_request`

## Usage

### Help

```bash
python -m src.main --help
```

### Batch Mode

```bash
python -m src.main batch <file>
```

Run operations from a file (one per line: `op a b`). Blank lines and lines starting with `#` are ignored. Stops on first invalid line with exit code 1.

**Example input file (`commands.txt`):**
```text
add 10 5
mul 3 7
# this is a comment
div 20 4
```

**Expected output:**
```text
add 10 5 = 15
mul 3 7 = 21
divide 20 4 = 5
```

### Interactive Mode

```bash
python -m src.main interactive
```

Commands: `add`, `sub`, `mul`, `div`, `pow`, `mod`, `history`, `history export <filepath>`, `clear`, `help`, `exit`

Invalid input (unknown command, invalid number, division by zero) prints an error and continues, not exit.
