# DINVA classic presentation profile approval v0.1

## Назначение и граница решения

Этот процесс создаёт отдельный immutable approved presentation profile только
из exact DRAFT, который Игорь отдельно утвердил прямым Human Approval. PASS
реализации, тестов или preflight сам по себе не утверждает profile и не
разрешает real publication.

Production approval связан одновременно с:

- DRAFT SHA-256
  `e1240c471435ba99709ff8cd44571151e9467f1d010b7e83770869383d734b40`;
- presentation contract fingerprint
  `246ad0bf2526319eb5b0be067f6d8493560b5ec0722662b1eaf2340ec31bd8cc`;
- authority `IGOR_DIRECT_HUMAN_APPROVAL`;
- отдельным exact publication authorization token.

Caller-supplied SHA от изменённого DRAFT не является approval provenance.
Publisher требует exact production SHA как supplied и actual SHA, strict UTF-8
JSON без duplicate keys, closed current profile shape, исходный статус
`DRAFT_PROFILE_CANDIDATE / DRAFT_UNAPPROVED` и independently recomputed exact
contract fingerprint.

## Разрешённая трансформация

Исходный DRAFT никогда не изменяется. Approved profile создаётся deep-copy и
допускает только две semantic mutations:

1. `artifact_status` становится `IMMUTABLE_APPROVED_PROFILE`.
2. `approval_provenance` становится `APPROVED` с authority
   `IGOR_DIRECT_HUMAN_APPROVAL`, UTC timestamp, approved contract fingerprint и
   deterministic approval ID:

   `IGOR-DINVA-CLASSIC-PRESENTATION-PROFILE-V0-1-20260902-001|DRAFT_SHA256=e1240c471435ba99709ff8cd44571151e9467f1d010b7e83770869383d734b40`

`schema_version`, `profile_id`, `document_family`, `reference_provenance`, весь
`presentation_contract` и `presentation_contract_fingerprint` остаются
deep-equal исходному DRAFT. Текущие schema, production renderer и independent
validator используют существующие top-level и `approval_provenance` contracts;
их изменение для этого процесса не требуется.

## Publication preflight и invocation

До real publication отдельно проверить Git baseline, exact source path/SHA,
отсутствие нового output case directory и отсутствие output. Exact real output
path выбирается только новым прямым решением Игоря и не hardcode в publisher.

```powershell
& '.\.venv\Scripts\python.exe' `
  'scripts\publish_dinva_classic_presentation_profile_approval.py' `
  --draft-profile '<EXACT_OUTSIDE_GIT_DRAFT.json>' `
  --draft-profile-sha256 'e1240c471435ba99709ff8cd44571151e9467f1d010b7e83770869383d734b40' `
  --output '<NEW_CASE_DIRECTORY\dinva-classic-presentation-profile-v0.1-APPROVED.json>' `
  --authorization 'IGOR_DINVA_CLASSIC_PRESENTATION_PROFILE_APPROVAL_PUBLICATION_AUTHORIZED'
```

Publisher требует новый case directory, существующего owner, exact filename и
outside-Git path. Он использует private dot-prefixed staging, flush + fsync,
strict staged/final reread, TOCTOU reread DRAFT, atomic no-overwrite hard-link
и final inventory из ровно одного JSON. Rollback удаляет только publisher-owned
staging/link и созданный им пустой directory; чужие artifacts не удаляются.

## Что approved profile не разрешает

Approved profile лишь становится допустимым profile input для будущего
renderer. Для любого render всё ещё необходимы отдельно approved document JSON
и отдельное exact render authorization. Этот процесс не разрешает document JSON
creation, XLSX/PDF/КП/счёт, client send, procurement, reserve, payment,
production, commit, push или любые downstream actions.

## Проверка реализации

Использовать только synthetic/tmp-path fixtures: exact SHA/fingerprint gates,
две разрешённые mutations, renderer `validate_profile(...,
allow_test_profile=False)`, current profile schema compatibility, no-overwrite,
TOCTOU rollback и отсутствие staging residue. Real publication всегда остаётся
отдельной Human Approval boundary.
