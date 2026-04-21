# Contributing

## Local Setup

1. Clone the repository.
2. Create and activate virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -e .
```
4. Install pre-commit hooks:
```powershell
python -m pre_commit install
```

## Development

Use VS Code with the `.venv` virtual environment selected as the Python interpreter.

## Workflow

- Use one branch per task.
- Keep changes small and focused.
- Run quality checks before commit and push.

## Quality Checks

Run these commands to ensure code quality:

```powershell
python -m ruff check .
python -m black --check .
python -m mypy .
python -m pytest -q --cov=my_project --cov-report=term-missing
python -m pre_commit run --all-files
```

## Changes to CLI Behavior

When CLI behavior changes, update `README.md` and `CHANGELOG.md` accordingly.
