# SHU-T2 RT-820 pricing-profile successor runbook

## Назначение

`scripts/build_invoice519_pricing_profile_shu_t2_rt820_successor.py` создаёт
полный immutable pricing-profile snapshot проекта `2024/086`. Контракт является
controlled replacement: число pricing positions остаётся `55`, а четыре
существующие позиции ШУ-Т2 получают строки `ROW-DRAFT-0113..0116`.

Builder не рассчитывает, не утверждает и не применяет цену. Значения `53763`,
`215052`, `122276` и `11963792` записываются только как
`NOT_CALCULATED_NOT_APPROVED` test/contract invariants.

## Exact inputs

Обязательны четыре явные пары path/SHA:

- parent SHU-T1 pricing profile;
- SHU-T2 RT-820 technical successor;
- SHU-T2 RT-820 Human Decision;
- pricing workbook с exact `КРН!A19:C19 = Терморегулятор RT-820 / 15000 / 900`.

Пути и SHA дополнительно сравниваются с case-scoped constants. JSON читается как
UTF-8 с duplicate-key rejection. Workbook открывается read-only; fallback,
generic work `432` и отдельный TST05 charge/row запрещены.

## CLI

```powershell
python scripts/build_invoice519_pricing_profile_shu_t2_rt820_successor.py `
  --parent-pricing-profile <exact-parent.json> `
  --parent-pricing-profile-sha256 <sha256> `
  --technical-successor <exact-technical.json> `
  --technical-successor-sha256 <sha256> `
  --human-decision <exact-decision.json> `
  --human-decision-sha256 <sha256> `
  --pricing-workbook <exact-workbook.xlsx> `
  --pricing-workbook-sha256 <sha256> `
  --output <fresh-external-directory\invoice519-pricing-profile-shu-t2-rt820-successor.json> `
  --authorization IGOR_SHU_T2_RT820_PRICING_PROFILE_SUCCESSOR_PUBLICATION_AUTHORIZED
```

`--output` обязан находиться вне repository; его parent directory не должен
существовать. Повторная публикация и overwrite запрещены.

## Publication protocol

Builder выполняет staged write, `flush`/`fsync`, strict staged reread,
pre-publication TOCTOU recheck четырёх inputs и exclusive hard-link publication.
После link выполняются identity check, strict final reread, повторная validation и
final TOCTOU recheck. Success marker печатается только после удаления staging и
проверки final inventory.

Staged и final reread проходят тот же closed-envelope validator: он заново
строит expected successor из validated parent и четырёх exact inputs, проверяет
exact root/nested key sets и требует полного deep-equal совпадения. Поэтому
изменение `status`, authority/application/immutable state, safety flags,
non-approvals, unrelated scope, authoritative bindings или validation summary
отклоняется и после hard link приводит к rollback без output/marker.

Rollback удаляет только inode, принадлежащий invocation. Foreign replacement
сохраняется, а cleanup failure переводит результат в ошибку.

## Exact successor contract

- coverage: `15 / 55 / 137 / 116 / 11`;
- `CABINET-GROUP-003`: 8 → 12 row IDs;
- positions `009/023/035/047`: identity и non-approval state сохранены;
- остальные 51 positions deep-equal;
- остальные 14 groups, включая ШУ-Т1, deep-equal;
- fingerprint `99db…cb79` удалён;
- fingerprint `4b5c…c0ec` один и содержит восемь positions;
- price/approval state всех 55 positions сохраняется deep-equal parent; у четырёх
  target positions price остаётся `null`, status —
  `NOT_CALCULATED_NOT_APPROVED`;
- `application_status` остаётся exact `NOT_APPLIED`, safety flags и
  non-approvals не ослабляются;
- `ROW-DRAFT-0113..0116` должны совпасть полным exact envelope, включая ordered
  evidence pairs, source quantity/multiplicity, approved signature, mapping
  status и component label.

Детерминированные bytes будущей публикации получаются только через
`serialize(payload)`. Для текущих четырёх exact inputs их frozen SHA-256:
`7b66d2431e2a323f9c0cd60bdaeff2d5d26ebfc0b430f2f6a5530e3a064dc701`.
Вычисление SHA в памяти не является публикацией и не создаёт output directory.

## Разделение разрешений

Code review, publication, calculator run, price approval, КП/счёт, отправка
клиенту, закупка и производство — разные действия. Наличие PASS или publication
artifact не даёт разрешения на следующие действия.
