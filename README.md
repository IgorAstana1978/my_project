[![CI](https://github.com/IgorAstana1978/my_project/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/IgorAstana1978/my_project/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.14-blue)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)

# my_project

`my_project` — Python-репозиторий детерминированных, fail-closed процессов для
извлечения проектных данных, подготовки технического состава, проверки цен и
создания локальных черновиков КП/счётов. Исходный CLI-калькулятор сохранён как
отдельный legacy-компонент.

Репозиторий не объявляет автоматически полученный результат production-ready:
существенные технические и коммерческие решения, real publication, создание
клиентского документа, отправка и downstream-действия остаются за отдельными
Human Approval.

## Основные контуры

- извлечение и строгая валидация данных из проектных источников;
- формирование и проверка technical composition и связанных successor-
  артефактов;
- immutable Human Decision, pricing и price-application contracts с точными
  path/SHA bindings, no-overwrite и закрытыми downstream-флагами;
- invoice/quote workflows: CSV/XLSX preflight, генерация и инспекция локальных
  DRAFT-документов, включая canonical copy-and-fill для Invoice 519;
- схемы, runbooks и тесты для воспроизводимой проверки каждого этапа;
- CLI-калькулятор с batch- и interactive-режимами.

Подробные правила автономной работы Codex и границы разрешений находятся в
`AGENTS.md`; конкретные контракты и команды — в `docs/`.

## Структура

- `scripts/` — builders, validators, publishers, checked launchers и document
  generators;
- `schemas/` — закрытые JSON Schema для case-scoped артефактов;
- `tests/` — unit, integration, contract и safety regressions;
- `docs/` — runbooks, design/acceptance notes и handoff-документы;
- `src/` — исходный CLI-калькулятор.

## Quality gates

Основные проверки: `pytest` с обязательным покрытием `100%`, Ruff,
Black `--check`, MyPy, `git diff --check`, pre-commit hooks и GitHub Actions.

На Windows канонический локальный runner:

```powershell
# Быстрые статические проверки без pytest
.\.venv\Scripts\python.exe .\scripts\run_codex_finish_checks.py --mode fast

# Полный gate: pytest, MyPy, Ruff, Black --check и git diff --check
.\.venv\Scripts\python.exe .\scripts\run_codex_finish_checks.py --mode full
```

Для узкой проверки конкретного контура используется targeted pytest; перед
commit/push для code changes применяется полный gate согласно `AGENTS.md` и
соответствующему runbook.

## Legacy CLI-калькулятор

### Справка

```bash
python -m src.main --help
```

### Batch mode

```bash
python -m src.main batch <file>
```

Файл содержит по одной операции `op a b` в строке. Пустые строки и строки с
`#` игнорируются; первая некорректная операция завершает команду с кодом 1.

Пример `commands.txt`:
```text
add 10 5
mul 3 7
# this is a comment
div 20 4
```

Ожидаемый вывод:
```text
add 10 5 = 15
multiply 3 7 = 21
divide 20 4 = 5
```

### Interactive mode

```bash
python -m src.main interactive
```

Команды: `add`, `sub`, `mul`, `div`, `pow`, `mod`, `history`,
`history export <filepath>`, `clear`, `help`, `exit`.

Некорректный ввод выводит ошибку, но не завершает interactive-режим.
