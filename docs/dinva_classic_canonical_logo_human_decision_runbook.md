# DINVA classic canonical logo Human Decision v0.1

## Назначение и граница

Контур неизменно фиксирует прямое Human Decision Игоря: канонический логотип
семейства `DINVA_CLASSIC_QUOTE_INVOICE_V0_1` — вариант `A / FAMILY /
Invoice519`. Scope решения — только `BRAND_LOGO_ONLY`.

Это решение не утверждает presentation profile, runtime template, КП, счёт,
XLSX/PDF или отправку клиенту. Оно не применяет logo bytes к profile и не
изменяет extractor/renderer. Статус намеренно остаётся
`IGOR_DINVA_CLASSIC_CANONICAL_LOGO_APPROVED_NOT_APPLIED`.

## Exact contract

- schema: `dinva_classic_canonical_logo_human_decision.v0.1`;
- artifact type: `IMMUTABLE_HUMAN_DECISION_CAPTURE`;
- decision ID: `IGOR-DINVA-CLASSIC-CANONICAL-LOGO-20260901-001`;
- authority: `IGOR_DIRECT_HUMAN_APPROVAL`;
- approval scope: `BRAND_LOGO_ONLY`;
- application status: `NOT_APPLIED_TO_PROFILE`;
- output: `dinva-classic-canonical-logo-human-decision-v0.1.json`.

Approved canonical asset:

```text
source: A / FAMILY / Invoice519
role: CLASSIC_FAMILY_EMBEDDED_LOGO
media part: xl/media/image1.png
raw SHA-256: 28a6a59ae0a5ca274c206c70545f70b333cac0276a7c4dcbebbf9156f88e0fa8
normalized-pixel fingerprint: 81d979c4c158452cca8e3b40d23a4fd321538dfcef238b6f8133beb33a122846
native dimensions: 200x68
decoded mode: RGB
```

`capacity100_tuned_v4` разрешён только как
`RUNTIME_GEOMETRY_STYLE_LAYOUT_SOURCE_ONLY`. Его embedded logo с raw SHA-256
`18e0f9446c72f8aa80ea833df07c2e42eb830770a0186decc476c5f948987301`
не является authoritative brand source и не заменяется publisher-ом.

## Canonical source bindings

Publisher требует четыре exact path/SHA bindings и проверяет в каждом
`xl/media/image1.png`, raw asset SHA, dimensions, decoded mode и normalized
RGBA pixel fingerprint.

```text
CLASSIC_FAMILY_EVIDENCE
C:\Users\IgorN\Downloads\2026.06.22_519_ТОО «Sensata Industrial».xlsx
17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5

CLASSIC_FAMILY_EVIDENCE
C:\Users\IgorN\Downloads\2026.06.04_463_ТОО «Rich energy» эталон.xlsx
8cf9f2b4ecca94e51a9f868891b6bc00151ef4b05b012db0d875862599c5253c

CLASSIC_FAMILY_EVIDENCE
C:\Users\IgorN\Downloads\2026.07.02_551_ТОО «TDK Energy».xlsx
d8e652325c142a72ffa4aa390197b3e357b5efc317d07f6d763e01d3c1c4fec9

CERTIFIED_RUNTIME_TEMPLATE_EVIDENCE
C:\Users\IgorN\Downloads\Фирменный_шаблон_счёта-КП_v0.4_capacity100_tuned_v4_ДиН_ВА-КЭС.xlsx
9c5ea4bd3be0dc920860a9900565f38092362edd6b0827a21a28ac53e2808292
```

## Closed safety boundary

В safety object только `human_decision_recorded` и
`canonical_logo_approved` равны `true`. Profile approval/generation/
publication, runtime-template modification, quote/invoice/XLSX/PDF generation,
client send, procurement, reserve, prepayment, payment, production и downstream
authorization остаются `false`.

## Immutable publication semantics

Output разрешён только вне Git, с exact filename и в новом отсутствующем
directory, owner которого уже существует. Collision запрещён. Publisher:

1. строго проверяет четыре path/workbook SHA и embedded PNG contracts;
2. создаёт private staging file с exclusive create, flush и `fsync`;
3. строго перечитывает UTF-8 JSON с duplicate-key rejection;
4. повторно читает все четыре authoritative inputs и сравнивает exact bytes/SHA;
5. публикует no-overwrite hard link и валидирует final bytes/inventory;
6. при ошибке удаляет только собственные staging/link/new empty directory.

## Future publication CLI

Токен ниже является частью contract, но не разрешением на запуск. Нужна новая
прямая команда Игоря с exact новым output path и no-overwrite intent.

```powershell
& '.\.venv\Scripts\python.exe' `
  '.\scripts\publish_dinva_classic_canonical_logo_human_decision.py' `
  --invoice-519 'C:\Users\IgorN\Downloads\2026.06.22_519_ТОО «Sensata Industrial».xlsx' `
  --invoice-519-sha256 '17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5' `
  --invoice-463 'C:\Users\IgorN\Downloads\2026.06.04_463_ТОО «Rich energy» эталон.xlsx' `
  --invoice-463-sha256 '8cf9f2b4ecca94e51a9f868891b6bc00151ef4b05b012db0d875862599c5253c' `
  --invoice-551 'C:\Users\IgorN\Downloads\2026.07.02_551_ТОО «TDK Energy».xlsx' `
  --invoice-551-sha256 'd8e652325c142a72ffa4aa390197b3e357b5efc317d07f6d763e01d3c1c4fec9' `
  --runtime-template 'C:\Users\IgorN\Downloads\Фирменный_шаблон_счёта-КП_v0.4_capacity100_tuned_v4_ДиН_ВА-КЭС.xlsx' `
  --runtime-template-sha256 '9c5ea4bd3be0dc920860a9900565f38092362edd6b0827a21a28ac53e2808292' `
  --output '<EXACT_NEW_OUTPUT_JSON_OUTSIDE_GIT>' `
  --authorization `
    IGOR_DINVA_CLASSIC_CANONICAL_LOGO_HUMAN_DECISION_PUBLICATION_AUTHORIZED
```

Publication PASS фиксирует только Human Decision artifact. Применение этого
решения к future presentation-profile extraction остаётся отдельным scoped
действием и отдельным approval boundary.

## Review gate

Tests используют только synthetic XLSX/PNG в `tmp_path`. Implementation review
не запускает real publisher, не создаёт decision JSON и не вызывает profile,
renderer, XLSX/PDF или downstream.
