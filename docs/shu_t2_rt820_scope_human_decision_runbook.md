# ШУ-Т2 / RT-820 Human Decision writer

This runbook covers only the fail-closed publication of one immutable Human
Decision for project `2024/086`. It does not authorize publication by itself.
It does not apply the decision, create a technical or pricing-profile
successor, run a calculator, approve a price, create a quote/invoice, or start
downstream work.

## Why this writer is case-scoped

The generic `human_decisions_batch.v0.22/v0.23` tools validate or apply a
component-replay batch. They do not create the schema required here and their
apply path produces an applied replay overlay. The existing additive builders
publish technical or pricing-profile successors and are therefore the wrong
artifact type and authorization boundary.

`scripts/publish_shu_t2_rt820_scope_human_decision.py` is intentionally narrow:
it accepts five explicit input paths and five expected SHA-256 values, validates
their exact case identities and cross-bindings, and publishes only
`technical_shu_t2_rt820_scope_human_decision.v0.1`.

## Exact decision contract

- Project: `2024/086`.
- Decision ID: `IGOR-SHU-T2-RT820-SCOPE-2024-086-001`.
- Status: `IGOR_SHU_T2_RT820_SCOPE_APPROVED_NOT_APPLIED`.
- Authority: `IGOR_DIRECT_HUMAN_APPROVAL`.
- Application status: `NOT_APPLIED`.
- Output filename:
  `technical-shu-t2-rt820-scope-human-decision-v0.1.json`.

The exact scope contains four pairs:

| Section | Technical | Pricing | Relay | Sensor |
|---:|---|---|---|---|
| 10 | `TFE-016` | `PRICE-POSITION-009` | `COMP-031` | `COMP-034` |
| 12 | `TFE-041` | `PRICE-POSITION-023` | `COMP-085` | `COMP-088` |
| 14 | `TFE-061` | `PRICE-POSITION-035` | `COMP-128` | `COMP-131` |
| 16 | `TFE-083` | `PRICE-POSITION-047` | `COMP-178` | `COMP-181` |

Each relay/sensor pair records one future `EKF-RT-820` component row with
quantity `1`, install type `temperature_relay_din_2mod`, and module width `2`.
The exact mapping is `КРН!A19:C19`: material `15000 KZT`, work `900 KZT`.
TST05 remains provenance only. A separate TST05 row/charge, generic work `432`,
family/fuzzy/similar-relay fallback, or double counting fails closed.

The decision supersedes only the prior
`forbidden_transfer_designation = "ШУ-Т2"` boundary for the eight listed
evidence IDs. It does not hard-code a new outside-cabinet exclusion count.
Every other supply boundary and Human Decision remains unchanged. The existing
ШУ-Т1 group, rows, pricing positions, and fingerprint are checked exactly and
cannot be changed by this publication.

## Safety and publication

Only `safety.human_decision_recorded` is `true`. Every apply, calculator,
pricing, floor, quote/invoice, client-send, procurement, production, downstream,
and scope-expansion flag is a required boolean `false`.

The output parent directory must not exist before publication. The writer
creates it exclusively, writes and `fsync`s a private staging file inside it,
validates the staged payload against the committed closed schema, rechecks all
input bytes and SHA values for TOCTOU, then creates the final file through an
exclusive no-overwrite hard link. It rereads the final JSON strictly, checks the
published bytes, validates the final payload, removes staging, and verifies that
the directory contains exactly the one final output. Publication is not
successful until all of those steps finish. Any failure after the hard link but
before that point rolls back the final file created by the invocation, staging,
and the empty directory. Rollback checks file identity before removing the final
path; a foreign replacement is preserved and reported as an explicit cleanup
blocker. Cleanup failure cannot produce the success marker.

## CLI

First inspect the CLI without publication:

```powershell
.\.venv\Scripts\python.exe `
  scripts\publish_shu_t2_rt820_scope_human_decision.py --help
```

The command below is a template only. Do not run it without a new, separate
Igor authorization naming all five exact paths/hashes, the exact output, and
immutable/no-overwrite intent:

```powershell
.\.venv\Scripts\python.exe `
  scripts\publish_shu_t2_rt820_scope_human_decision.py `
  --technical-successor <EXACT_TECHNICAL_SUCCESSOR_JSON> `
  --technical-successor-sha256 <EXACT_TECHNICAL_SUCCESSOR_SHA256> `
  --composition-decision <EXACT_COMPOSITION_DECISION_JSON> `
  --composition-decision-sha256 <EXACT_COMPOSITION_DECISION_SHA256> `
  --cabinet-pricing-decision <EXACT_CABINET_PRICING_DECISION_JSON> `
  --cabinet-pricing-decision-sha256 <EXACT_CABINET_PRICING_SHA256> `
  --rt820-code-install-decision <EXACT_RT820_DECISION_JSON> `
  --rt820-code-install-decision-sha256 <EXACT_RT820_DECISION_SHA256> `
  --pricing-profile <EXACT_PRICING_PROFILE_JSON> `
  --pricing-profile-sha256 <EXACT_PRICING_PROFILE_SHA256> `
  --output <EXACT_NEW_OUTPUT_JSON> `
  --authorization `
    IGOR_SHU_T2_RT820_SCOPE_HUMAN_DECISION_PUBLICATION_AUTHORIZED
```

The token is only an operator acknowledgement. Its presence in committed code
or this runbook is not Human Approval and does not permit a real invocation.
On success the writer emits `PUBLISHED_IMMUTABLE_NO_OVERWRITE` with the final
SHA-256 and byte size.

## Review checks

Code review should run `py_compile`, targeted and full pytest with coverage,
Ruff, Black `--check`, MyPy, schema loading/validation, and `git diff --check`.
Positive publication tests must use temporary synthetic paths only. Real inputs
may be checked read-only through the writer's validation functions; no real
output directory may be supplied or created during code-only review.
