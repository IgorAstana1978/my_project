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

## Development workflow

For daily work in VS Code on Windows:

```powershell
.\.venv\Scripts\Activate.ps1
python -m ruff check .
python -m black --check .
python -m mypy .
python -m pytest -q
python -m pre_commit run --all-files
```
You can also run the VS Code `quality` task to execute the main checks in sequence.
