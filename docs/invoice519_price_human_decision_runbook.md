# Invoice 519 price-only Human Decision publisher

This runbook covers only the fail-closed capture of Igor's direct Human
Approval of the project price for project `2024/086`, Invoice 519. It does not
authorize a real invocation of the publisher.

## Contract boundary

The artifact contract is:

- schema: `invoice519_price_human_decision.v0.1`;
- artifact type: `IMMUTABLE_HUMAN_DECISION_CAPTURE`;
- decision ID: `IGOR-INVOICE519-PRICE-2024-086-001`;
- status: `IGOR_INVOICE519_PRICE_APPROVED_NOT_APPLIED`;
- authority: `IGOR_DIRECT_HUMAN_APPROVAL`;
- approval scope: `PRICE_ONLY`;
- application status: `NOT_APPLIED`;
- output filename: `invoice519-price-human-decision-v0.1.json`.

The approved price is `19,499,186 KZT`. It is the exact reconciliation of the
unchanged checked 55-position subtotal `11,963,792 KZT` and the separately
checked 33-position subtotal `7,535,394 KZT`.

Price approval is not price application. It does not authorize or create a
quote, invoice, XLSX, PDF, client publication, client send, lead time,
procurement, reserve, prepayment, production, or any downstream action.

## Exact coverage

The committed contract contains both exact membership lists, not only counts.
The frozen pricing profile contributes these 55 canonical Invoice 519 position
numbers:

```text
6,7,8,9,10,11,12,13,14,16,17,18,19,20,27,30,31,32,33,34,35,36,37,
39,40,41,42,43,50,51,52,53,54,55,56,57,59,60,61,62,63,70,73,74,
75,76,77,78,79,81,82,83,84,85,88
```

The nine checked missing families contribute these 33 positions:

```text
1,2,3,4,5,15,21,22,23,24,25,26,28,29,38,44,45,46,47,48,49,58,
64,65,66,67,68,69,71,72,80,86,87
```

The validator derives and requires:

- unique frozen membership: `55`;
- unique missing membership: `33`;
- overlap: `0`;
- union: exact integers `1..88`;
- uncovered: `0`;
- family membership union: exact missing 33;
- family subtotal sum: `7,535,394 KZT`;
- combined total: `11,963,792 + 7,535,394 = 19,499,186 KZT`.

Frozen 55 positions are not recalculated by this publisher.

## Input bindings

The publisher accepts seven explicit path/SHA pairs and then requires each path
and SHA to equal the committed case-specific binding:

| Role | SHA-256 |
|---|---|
| `completed_technical_input` | `c27c2c3032699cb07c981aeb4af429b27ec18180225319f45ce65ab77fedee44` |
| `main_price_workbook` | `79b3ace77e84b87c46eb708f1c3b2ae63b5c6d75c5ebf6889c12b99624112ba1` |
| `custom_sche_metal_workbook` | `b51d7087e0bd8f92e48985294062ead6826c6b50ce3cfacd0f9d0dc22c05f7f2` |
| `pricing_profile` | `ae604108514a2b19b58c262c0e2fae379be6eac8a7286ffc2da605ac29637c9e` |
| `canonical_invoice_519` | `17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5` |
| `ukrm_price_workbook` | `3570045b9e8de542136664c99ff74963f1db6a0a3f5c24f7ac9e81482f5128b6` |
| `yarv100_price_workbook` | `d41f1730c446fde866ed1739cf71e73c1f58f83c46f6e2c41e2478e005e9b35d` |

The current UKRM workbook hash differs from the earlier PASS byte hash. Before
this implementation it was rechecked read-only: the approved source range
`10квар!A2:J8` retained the exact material/work values used by the checked UKRM
calculation. The contract binds the current bytes shown above; any later byte
change fails before publication.

The completed input and pricing profile are also parsed as strict JSON. The
completed input must preserve its non-approval safety boundary. The profile
must preserve its schema/status/`NOT_APPLIED` state and expose exactly the
frozen 55 Invoice 519 position numbers.

## Fail-closed publication

The publisher rejects duplicate JSON keys, unknown or malformed source hashes,
wrong input roles or paths, changed profile membership, any reconciliation
drift, extra schema fields, and any enabled safety authorization.

Only `safety.human_decision_recorded` and `safety.price_approved` are `true`.
Price application and every commercial or downstream authorization remain
required boolean `false` values.

After all inputs pass, the publisher builds the payload in memory, validates it
against the committed closed schema, writes and `fsync`s a private staging
file, validates the staging bytes, and rechecks every input for TOCTOU. It then
creates the final path by exclusive no-overwrite hard link, strictly rereads
and validates the final JSON, removes staging, and verifies the final directory
inventory. A failure after the hard link rolls back the link, staging, and the
new empty directory. A foreign replacement is preserved and reported.

## CLI template

Inspecting `--help` is read-only. The full command below is a template only and
must not be run without a new, separate Igor authorization naming the exact
inputs, hashes, output path, and immutable no-overwrite intent:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\publish_invoice519_price_human_decision.py `
  --completed-technical-input <EXACT_PATH> `
  --completed-technical-input-sha256 <EXACT_SHA256> `
  --main-price-workbook <EXACT_PATH> `
  --main-price-workbook-sha256 <EXACT_SHA256> `
  --custom-sche-metal-workbook <EXACT_PATH> `
  --custom-sche-metal-workbook-sha256 <EXACT_SHA256> `
  --pricing-profile <EXACT_PATH> `
  --pricing-profile-sha256 <EXACT_SHA256> `
  --canonical-invoice-519 <EXACT_PATH> `
  --canonical-invoice-519-sha256 <EXACT_SHA256> `
  --ukrm-price-workbook <EXACT_PATH> `
  --ukrm-price-workbook-sha256 <EXACT_SHA256> `
  --yarv100-price-workbook <EXACT_PATH> `
  --yarv100-price-workbook-sha256 <EXACT_SHA256> `
  --output <EXACT_NEW_OUTPUT_JSON> `
  --authorization `
    IGOR_INVOICE519_PRICE_HUMAN_DECISION_PUBLICATION_AUTHORIZED
```

The authorization token is only an operator acknowledgement. Its presence in
committed code or this runbook is not Human Approval for a real invocation.

## Application boundary and review

There is intentionally no application path, `apply_*.py`, quote bridge, or
downstream consumer in v0.1. A future use of the approved price must create a
separate additive successor under a separate exact Human Approval. It must not
change this immutable decision artifact or infer quote/client authorization.

Code review should run targeted tests, full pytest with the 100% coverage gate,
Ruff, Black `--check`, MyPy, schema validation, and `git diff --check`. Positive
publication tests use synthetic temporary inputs and output paths only. Code
review must not invoke the publisher with real inputs or create a runtime Human
Decision artifact.
