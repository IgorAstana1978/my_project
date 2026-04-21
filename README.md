[![CI](https://github.com/IgorAstana1978/my_project/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/IgorAstana1978/my_project/actions/workflows/ci.yml)

# my_project

Учебный Python-проект с аккуратно настроенным workflow в VS Code, тестами, покрытием и удобным CLI-калькулятором.

## Что есть в проекте

- CLI-калькулятор на `argparse`
- подкоманды и алиасы
- интерактивный режим
- история операций в интерактивном режиме
- очистка истории
- тесты для функций и CLI
- `ruff`, `black`, `mypy`, `pytest`
- `pre-commit`
- GitHub Actions
- CI badge
- покрытие тестами **100%**

## Поддерживаемые операции

Основные команды:

- `add` — сложение
- `subtract` — вычитание
- `multiply` — умножение
- `divide` — деление
- `power` — степень
- `modulo` — остаток от деления

Короткие алиасы:

- `sum`
- `sub`
- `mul`
- `div`
- `pow`
- `mod`

## Примеры запуска

```bash
python -m src.main add 2 3
python -m src.main sub 10 4
python -m src.main mul 6 7
python -m src.main div 5 2
python -m src.main pow 2 8
python -m src.main mod 10 3
