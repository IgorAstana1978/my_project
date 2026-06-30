# Phase 2.28: commercial quote checked launcher

## Назначение

`make_quote_capacity100_commercial_checked.ps1` создаёт только внутренний
черновик commercial КП из заранее проверяемого восьмиколоночного CSV.

Launcher вызывает изолированный commercial writer, который выполняет
commercial preflight и reconciliation. Technical PASS не является коммерческим
одобрением или разрешением на отправку документа клиенту.

## Короткий запуск

Запускать из корня репозитория:

```powershell
.\scripts\make_quote_capacity100_commercial_checked.ps1 `
  "C:\Users\IgorN\Downloads\commercial_items.csv" `
  "C:\Users\IgorN\Downloads\commercial_internal_draft.xlsx"
```

Первые два позиционных параметра:

1. `CommercialCsv` — заполненный commercial CSV outside Git.
2. `Output` — новый XLSX path outside Git.

По умолчанию используется тот же canonical capacity100 template из
`$env:USERPROFILE\Downloads`, что и в существующем technical launcher. Launcher
не ищет и не выбирает другие XLSX-файлы.

Если canonical template находится в другом месте, путь нужно передать явно:

```powershell
.\scripts\make_quote_capacity100_commercial_checked.ps1 `
  "C:\Users\IgorN\Downloads\commercial_items.csv" `
  "C:\Users\IgorN\Downloads\commercial_internal_draft.xlsx" `
  -Template "C:\Users\IgorN\Downloads\approved_capacity100_template.xlsx"
```

Опциональный `-Python` позволяет явно указать Python executable. Без параметра
используется `.\.venv\Scripts\python.exe`.

## Fail-closed границы

- launcher всегда передаёт certified `--template-capacity 100`;
- input, template и Python executable должны существовать;
- output должен быть новым, а его parent directory должен существовать;
- commercial writer дополнительно запрещает output внутри Git;
- existing technical 5-column workflow остаётся отдельным и неизменным;
- launcher и writer не выполняют Git-команды и не отправляют документы;
- generated CSV/XLSX, client files и временные файлы нельзя добавлять в Git;
- автоматический отчёт не должен раскрывать цены, суммы, итоги или полные CSV
  rows;
- VAT/НДС launcher не записывает и не рассчитывает.

После успешного запуска результат остаётся internal draft. Обязательны ручная
проверка Игоря и отдельное Human Approval перед любым client-ready
использованием или отправкой.
