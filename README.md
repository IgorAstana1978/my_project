[![CI](https://github.com/IgorAstana1978/my_project/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/IgorAstana1978/my_project/actions/workflows/ci.yml)

# my_project

Учебный Python-проект с настроенным рабочим процессом в VS Code.

## Что уже настроено

- Python 3.14
- виртуальное окружение `.venv`
- запуск проекта через F5
- автопроверки через `Ctrl + Shift + B`
- `ruff` для линтинга
- `black` для форматирования
- `mypy` для проверки типов
- `pytest` для тестов
- `pre-commit` для автоматических проверок перед коммитом
- Git и GitHub
- GitHub Copilot в VS Code

## Структура проекта

```text
my_project/
├── .venv/
├── .vscode/
├── src/
│   ├── __init__.py
│   └── main.py
├── tests/
│   └── test_main.py
├── .gitignore
├── .pre-commit-config.yaml
├── pyproject.toml
├── pytest.ini
└── README.md
