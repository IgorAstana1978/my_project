# invoice_quote_filler v0.2.1: compact Codex prompt card

Короткий reusable prompt для узких задач. Не повторяй исторический контекст:
используй текущий `AGENTS.md` и явно указывай только task-specific red points.

## Reusable template

```text
Repo:
C:\Users\IgorN\projects\my_project

Expected HEAD:
<expected SHA and message>

Goal / expected outcome (Task:):
<one observable outcome>

Relevant context:
<only facts needed for this task>

Scope only:
<exact file(s)>

Constraints / task-specific red points:
- Guardrails: use current repo guardrails from AGENTS.md;
- technical PASS is not commercial approval;
- do not approve final price, lead time, composition, or client send;
- do not modify original Excel files;
- do not weaken checks for formulas, totals, currencies, dates, company details,
  templates, or generated outputs;
- no client files or generated files in Git, including `.xls`, `.xlsx`,
  generated `.csv`, screenshots, or temp files;
- exact-file staging only; do not use git add .;
- no commit or push without separate Human Approval from Igor;
- procurement, workshop, shipment, and client send require Igor's decision.

Allowed commands:
<existing commands confirmed in the repo; no API/model/network calls>

Checks / evidence:
<existing targeted check>
<relevant full checks required for this change>
git diff --check
.\scripts\finish_quote_workflow.ps1

Done when / stop condition:
<observable PASS and exact allowed changed files>

Max attempts: 3

Abort conditions:
- a new file, dependency, architectural change, or scope expansion is required;
- a file outside Scope only must change;
- passing requires weaker tests, validation, coverage, or safety;
- HEAD differs, the initial tree is not clean, or unrelated changes appear.

Final report:
- initial HEAD and status;
- changed files and full allowed-file diff;
- Checks: results and CODEX_FINISH_REPORT;
- unresolved cause and required scope decision on STOP;
- git status --short --untracked-files=all;
- confirm that git add/commit/push were not run.
```

## Bounded goal loop

Default `Max attempts: 3`. После failure определи причину и внеси одно
минимальное in-scope исправление. После каждой попытки запускай только
указанные checks и сразу останавливайся при выполнении stop condition. После
трёх попыток остановись и покажи unresolved cause. Не расширяй scope без
отдельного решения Игоря, не скрывай failure и не ослабляй tests, validation,
coverage или safety ради PASS. Остановись раньше, если нужен новый файл,
dependency, архитектурное изменение или выход за scope.

## Минимальный достаточный prompt

Начинай с самого маленького prompt/tool set. Добавляй инструкции только при
конкретном failure или eval gap; не повторяй исторический контекст из repo.
Вместо расплывчатого «будь краток» используй: «Начни с вывода, сохрани
обязательные факты, риски, проверки и следующий шаг; убери вступления, повторы
и необязательный фон».

## Короткий bounded-пример

```text
Goal / expected outcome (Task:): обновить compact prompt card по заданию.
Scope only: docs/invoice_quote_filler_v0_2_1_codex_compact_prompt_card.md
Checks / evidence:
<existing targeted check confirmed to exit successfully under current repo settings>
.\.venv\Scripts\python.exe -m pytest
git diff --check
.\scripts\finish_quote_workflow.ps1
Done when / stop condition: разрешённый файл — единственное изменение, targeted
и релевантные full checks проходят, guardrails сохранены.
Max attempts: 3
Abort conditions: нужен второй файл, новый dependency или ослабление guardrail.
Final report: полный diff, результаты checks и status; без git add/commit/push.
```

Если одиночный targeted pytest блокируется общим coverage gate, не отключай
coverage и не ослабляй порог: выполни полный approved pytest suite и отдельно
сообщи результат targeted assertions.

## STOP report

```text
STOP: Max attempts: 3 исчерпан.
Failed check: <exact check>.
Unresolved cause: <cause>.
Scope decision: <нужен / не нужен выход за scope и почему>.
git add/commit/push не выполнялись.
```

Для quote generation, Excel templates, Excel runtime, dependencies, real client files
или commercial data используй расширенный prompt. Во всех случаях technical
PASS не является commercial approval; отправка клиенту, закупка, цех и shipment
требуют отдельного решения Игоря.
