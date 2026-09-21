# Dynamic approved price baseline manifest v0.1

The historical Invoice519 pricing profile remains bound to `Таблица 05.01.2026
верная.xlsx`, SHA-256
`79b3ace77e84b87c46eb708f1c3b2ae63b5c6d75c5ebf6889c12b99624112ba1`.
Neither its approved mappings nor its frozen calculation/provenance is repriced.

The compatibility successor price source is the entire exact `Таблица 09.09.2026
верная-2.xlsx`, SHA-256
`02ca5be9b2eb6775289ee1053c389a659c85e2bd27a2b9867b7d523d6d6e4096`.
The workbook SHA governs dynamic values. This binding does not authorize a
client-facing price, invoice, quote, sending, procurement or production action.

The static successor remains compatibility-only. A future/non-profile run with
no explicit version resolves this exact chain:

```text
active-price-baseline.json
-> exact manifest path/SHA
-> exact workbook path/SHA
-> governed mapping snapshot
-> DRAFT price calculation
```

The canonical external root is
`C:\Users\IgorN\Documents\invoice_quote_filler_data\prices`. Immutable
manifests use `manifests/<manifest-id>.json`; the mutable selector is
`active-price-baseline.json`. Missing, stale or corrupt members fail closed.
Explicit `historical_invoice519` always overrides the selector. The checked
frozen Invoice519 profile keeps its existing authoritative inputs and never
reprices from the active baseline.

## Authority split

Technical mapping identity is defined independently from price values. It
includes stable mapping ID, apparatus/cabinet semantics, source sheet/row,
expected label and an identity fingerprint. The manifest can approve new price
values only for the unchanged fingerprint. Label, source, identity, added or
removed price names, formulas, missing values and duplicates produce `HOLD`.

`audit_price_baseline_candidate.py` is read-only: it verifies the active chain,
computes candidate workbook SHA and structural/price diffs, and prints a
content-bound approval payload. It does not publish a manifest or update the
selector.

`activate_price_baseline_manifest.py` accepts only an exact audit/approval
binding, rechecks every input and the workbook snapshot, publishes the manifest
with no-overwrite semantics, then replaces the selector atomically and verifies
the complete chain. Tests use synthetic roots only. A successful technical run
is still `DRAFT / NOT APPROVED`; quote, send, procurement and production remain
closed.

## Actual ingestion classification of the 16 changed exact names

The bounded A/B workbook scan and current `calc_quote_price_draft.py` lookup
definitions/mappings classify changed names as follows. A dynamic price is
read from the SHA-bound `КРН` sheet; B has at least one exact expected-value
contract. C is currently unused by this calculator/workflow, though its price
is part of the approved successor workbook source.

| Class | Changed exact name |
| --- | --- |
| A | `ВА47 1 полюсный` |
| A | `ВА47 2 полюсный` |
| A | `ВА47 3 полюсный до 63А` |
| B | `ВА55/57/59, АМ1  3 полюсные от 16 до 63А` |
| B | `УЗО АД-32 1Р+N до 63А EKF` |
| C | `ВА47 1 полюсный 10А` |
| C | `ВА47 3 полюсный 10А` |
| C | `ВА55/57/59 400А` |
| C | `ВА55/57/59,  АМ1 от 80 до 100А` |
| C | `Контактор до 250А` |
| C | `Контактор до 400А` |
| C | `Контактор до 630А` |
| C | `ПН-2 100А` |
| C | `ПН-2 250А` |
| C | `ПН-2 400А` |
| C | `Реле времени суточное ТЭ-15` |

The compatibility release changed five exact mapping entries: `ЩР!B8` 13,000
→ 15,000 (`C8` remained 1,800), and four mappings using `КРН!B5` 4,100 → 4,500
(`C5` remained 432). Those historical/successor constants remain frozen for
reproducibility. Future compatible price-only changes are stored in manifests
and require no new Python constants or expected-price edits.
