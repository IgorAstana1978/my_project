# Phase 2.27b handoff: commercial writer core

## Starting point

- HEAD: `cadb840 add commercial quote reconciliation inspection`
- Expected initial worktree: clean
- Existing commercial CSV preflight and commercial reconciliation inspector are
  the certified validation boundaries for this phase.

## Scope

Add one isolated commercial CSV-to-XLSX path:

- `scripts/run_invoice_quote_commercial_from_csv.py`
- `tests/test_run_invoice_quote_commercial_from_csv.py`

Do not change the existing five-column CSV workflow or the checked launcher.

## Required flow

1. Require PASS from `preflight_quote_commercial_input.py`.
2. Require the certified capacity100 profile.
3. Build a temporary XLSX candidate outside Git.
4. Write item data to C:G with the technical-writer value contract.
5. Write `unit_price_kzt` to H as a numeric integer.
6. Do not patch I formulas and do not write or calculate VAT.
7. Require PASS from `inspect_quote_commercial_reconciliation.py`.
8. Publish the requested final path atomically only after reconciliation PASS.

On any failure, no final output may be created and the temporary candidate must
be removed.

## Safety and reporting invariants

- Output is an internal draft only.
- Technical PASS is not commercial approval.
- Manual Igor review and separate Human Approval remain required.
- Existing output paths fail closed.
- Output inside the Git project fails closed.
- Reports must not include unit prices, line totals, grand totals, full CSV
  rows, or client-ready claims.
- Generated CSV/XLSX files, client files, screenshots, temporary files, tokens,
  and secrets must not be added to Git.
- No commit or push without separate Igor approval.

## Required quality gate

- Targeted `pytest --no-cov`
- Full `pytest`
- `mypy`
- `ruff check .`
- `black --check .`
- `git diff --check`
- `.\scripts\finish_quote_workflow.ps1`
