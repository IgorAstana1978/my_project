# Versioned price baseline for future calculations

The historical Invoice519 pricing profile remains bound to `Таблица 05.01.2026
верная.xlsx`, SHA-256
`79b3ace77e84b87c46eb708f1c3b2ae63b5c6d75c5ebf6889c12b99624112ba1`.
Neither its approved mappings nor its frozen calculation/provenance is repriced.

The successor price source is the entire exact `Таблица 09.09.2026
верная-2.xlsx`, SHA-256
`02ca5be9b2eb6775289ee1053c389a659c85e2bd27a2b9867b7d523d6d6e4096`.
The workbook SHA governs dynamic values. This binding does not authorize a
client-facing price, invoice, quote, sending, procurement or production action.

Both price-calculator entrypoints require an explicit
`--price-baseline-version` for a future/non-profile run. The two allowed values
are `historical_invoice519` and `successor_2026_09_09`. The checked frozen
Invoice519 profile accepts only the historical binding already recorded in its
authoritative inputs. Unknown versions, path/SHA mismatch, a mapping from the
wrong version, changed expected values, formula prices and ambiguous same-sheet
lookups fail closed. No fallback to the other baseline occurs.

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

Only five existing hardcoded mapping entries need successor expected-material
values: `ЩР!B8` 13,000 → 15,000 (`C8` stays 1,800), and four mappings using
`КРН!B5` 4,100 → 4,500 (`C5` stays 432). Historical mappings are left intact;
no price cells or C-class names are hardcoded as part of successor binding.
