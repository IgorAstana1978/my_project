# Phase 2.35 — gated top-level specification rows

## Scope and boundary

This phase adds a narrow opt-in PDF specification-row parser for the existing
section-aware extraction workflow. The legacy `--project-pdf` path and its
`preliminary_composition_draft.v0.1` serialization remain unchanged because
`specification_rows` defaults to `False` in both `extract_pdf()` and
`build_artifacts()`.

Only `build_section_aware_artifacts()` enables the option. No schema migration,
OCR, dependency, component-tail extraction, alias merge, pricing, calculator,
commercial mapping, or quote generation is introduced.

## Gate

For each page, column bands are inferred from that page's own ordered header
geometry for position, description, type/model, unit, and quantity. The gated
path requires:

- a usable text layer;
- all five header roles in monotonic X order;
- at least three unique `N.N` anchors in monotonic source-row order;
- a distinct quantity band with at least two aligned, non-zero numeric
  fragments.

An attempted specification page that fails the gate produces a manual-review
red flag, creates no row-derived item, and is not passed to the legacy line
parser. Pages with no specification evidence continue through the legacy path.

## Row-head extraction

The parser inspects only the small geometric head around each position anchor.
A literal full-token designation in the position/description columns has
priority. Otherwise, a complete board-like token may be accepted from the
type/model column. Only this model fallback has a semantic guard. Its description
source is the nearest vertical row-head cluster around the selected model
identity, not every description block in the wider row window. The cluster
center follows the anchor/model geometry, while its tolerance is derived from
their offset and the local neighboring-row gaps. This excludes a preceding
group/section heading above the current row.

The selected description is tokenized, and a description containing an
enclosure noun but no words beyond generic enclosure/form-factor terms (for
example, cabinet/panel/body, mounting, door, modules, IP rating, or dimensions)
is left for manual review and creates no item. Functional descriptions remain
eligible, so `Вводное устройство для лифтов` can retain model `ЯРВ-100`.
Literal designation behavior is unchanged. Substrings are not promoted, so
`ЩР` inside `ЩРВ-П-18` cannot become a separate item. Ordinary equipment models
do not match the board-like model grammar.

A model-only candidate with no non-empty local description cluster is rejected
fail-closed with a manual-review diagnostic. For an accepted model-only row,
the exact selected local description blocks are included in raw provenance;
the excluded preceding group/section heading is not. Literal-row provenance
selection remains unchanged.

Quantity is retained only for one positive numeric fragment in the inferred
quantity band. Multiple candidates or a nearby zero-coordinate orphan leave
quantity null. Unit and the exact selected row-head fragments are retained in
the provenance locator/raw text. Multi-line tails are never converted into
components.

Repeated normalized designations merge provenance. A later quantity fills an
earlier null; differing non-null quantities become a conflict and reset the
quantity to null. Panel-label/type-model alias merging remains out of scope.

## Verification boundary

The implementation is covered by no more than five logical tests: stable
synthetic extraction; ambiguous quantity; tail exclusion; broken gate/full
token/model-fallback semantic guarding; and the four-page v0.1 semantic regression excluding
`created_at`. A controlled Section 13 pilot must be created outside Git only
after the local test and quality gates pass, then compared only with the frozen
blind draft.
