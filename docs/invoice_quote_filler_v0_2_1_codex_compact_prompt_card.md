# invoice_quote_filler v0.2.1: compact Codex prompt card

Короткий reusable prompt для обычных узких задач. Текущие правила безопасности
уже закреплены в repo, поэтому не нужно повторять весь исторический контекст.

```text
Repo:
C:\Users\IgorN\projects\my_project

HEAD:
<expected SHA and message>

Task:
<one clear task>

Scope only:
<exact file 1>
<exact file 2>

Guardrails:
- use current repo guardrails;
- exact-file staging only;
- do not use git add .;
- no client files or generated files in Git;
- no commit or push without separate Human Approval.

Checks:
<targeted check>
<full checks required for this change>
git diff --check
.\scripts\finish_quote_workflow.ps1

Final report:
- changed files;
- check results;
- CODEX_FINISH_REPORT;
- git status --short --untracked-files=all.
```

## Когда prompt должен оставаться коротким

Для обычной docs/test/helper-задачи достаточно шаблона выше. Codex должен
использовать текущие repo guardrails, operator run card, quote workflow state,
finish wrapper и handoff, а не просить повторить их в каждом prompt.

## Когда нужен расширенный prompt

Добавлять подробный контекст, отдельный safety scope и явные approvals, если
задача меняет опасные области:

- quote generation;
- Excel templates;
- dependencies или requirements;
- real client files;
- Excel runtime;
- commercial data.

Для этих областей technical PASS не является commercial approval. Отправка
клиенту, закупка, цех и shipment требуют отдельного решения Игоря.

## Постоянные ограничения

- Не добавлять `.xls`, `.xlsx`, generated `.csv`, screenshots, client или temp
  files в Git.
- Не использовать `git add .`.
- Перед commit показывать status, staged diff и релевантные проверки.
- Не делать commit/push без отдельного Human Approval.
