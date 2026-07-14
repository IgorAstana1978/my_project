# Confirmed composition builder from a Phase 2.32 bundle

## Назначение

Скрипт scripts/build_confirmed_composition_from_preliminary_bundle.py создаёт
validated confirmed_composition_artifact.v0.1 из существующего Phase 2.32
bundle. Надёжно извлечённые значения переносятся автоматически. Любой
preliminary red flag блокирует workflow до вопросов и Human Approval. Игорю
показываются только безопасно разрешимые исключения, после чего выводится
итоговый технический состав и запрашивается одно подтверждение.

Команда не запускает калькулятор, не создаёт CSV, XLSX или КП и не разрешает
цену, срок, отправку, закупку или производство.

## Prerequisites

- Запускать из корня my_project.
- Использовать существующий Python environment проекта.
- Canonical external root должен существовать заранее:

      C:\Users\IgorN\Documents\production_ai_cases

- Case directory и три Phase 2.32 input-файла также должны существовать.
- Builder не создаёт root/case directory и не импортирует или копирует inputs.

## Входной layout

    C:\Users\IgorN\Documents\production_ai_cases\<CaseId>\
      source-bundle-manifest.txt
      preliminary-composition-draft.json
      igor-review-card.md

Параметр --case-id должен соответствовать grammar
CASE-[A-Z0-9]+(?:-[A-Z0-9]+)* и точно совпадать с именем каталога.
Произвольный output path не поддерживается.

## Запуск

    .\.venv\Scripts\python.exe `
      .\scripts\build_confirmed_composition_from_preliminary_bundle.py `
      --case-id "CASE-2026-001" `
      --confirmation-id "CONFIRM-COMPOSITION-2026-001" `
      --approval-channel "igor_local_terminal"

confirmed_by всегда равен Igor. confirmed_at формируется программой после
финального подтверждения как timezone-aware ISO 8601 timestamp.

## Автоматический перенос

Builder автоматически переносит только присутствующие, непустые,
source-provenanced значения без conflicts, missing_fields, unresolved state
или блокирующего source status:

- item/component IDs;
- product name и item quantity;
- component code/model, label и quantity;
- допустимый install type, кроме manual_review_required;
- cabinet code/label только при наличии фактического provenance;
- фиксированный product_type = switchboard;
- exact input hashes;
- schema/safety constants и разрешённый next_allowed_step.

Confidence, raw evidence и preliminary-only diagnostics не попадают в confirmed
artifact. Brand/model/rating/note не теряются молча: если они не представлены
однозначно в допустимых component_code/component_label, CLI создаёт одно
связанное исключение.

До классификации builder проверяет, что item_id непусты и уникальны, а все
component_id непусты и уникальны во всём будущем artifact. Существующий contract
не задаёт отдельную grammar для IDs, поэтому необычный, но непустой и уникальный
ID не отклоняется только по локально придуманному regex.

Если source.source_files отсутствует целиком, draft считается legacy profile:
provenanced значения не переносятся автоматически и становятся исключениями.
Если source.source_files присутствует, каждый provenance[].source_file обязан
ссылаться на известный metadata entry с непустым status. Для provenance с page
требуется соответствующий page status. Неизвестный источник/status и
блокирующие source/page statuses работают fail-closed.

## Preliminary red flags

Любой непустой red_flags на root, item, cabinet, component или другом вложенном
техническом объекте блокирует workflow. Builder выводит точные source paths,
возвращает FAIL, не запрашивает approval phrase и не создаёт staging/canonical
outputs. Интерактивного принятия preliminary red flag в этой версии нет.

## Вопросы Игорю

CLI спрашивает только:

- conflicts, missing и unresolved values;
- manual_review_required;
- assumptions;
- обязательные confirmed-поля без надёжного значения;
- технические corrections или not_applicable с обязательной причиной;
- supply boundary.

Допустимые действия показываются рядом с каждым исключением. Неизвестное
действие, пустое обязательное значение или cancel завершают операцию без
canonical outputs. Builder не опрашивает каждое корректно извлечённое поле.

Technical conflict с известным target допускает только correction конкретного
confirmed-поля или cancel. Targetless conflict не поддерживает generic accept и
остаётся fail-closed. Technical details допускают correct, not_applicable с
обязательной текстовой причиной или cancel; not_applicable не удаляет компонент.

Assumption считается нетехническим только при явном префиксе Nontechnical: или
[nontechnical]. Его accept требует причины и записывается как
accepted_nontechnical_assumption. Любое иное assumption считается техническим.
Если его нельзя однозначно связать с конкретным confirmed-полем, builder
разрешает только cancel; техническое значение нужно исправить в preliminary
данных или в отдельном поддерживаемом field issue.

Для manual_review_required доступен explicit group review только при полном
точном совпадении уже извлечённого fingerprint: code, label, model, brand,
rating, unit, note и proposed install context. CLI показывает item ID, component
ID, code, label, rating и quantity каждого участника. Оператор выбирает apply,
individual или cancel. Group apply требует явного install type и создаёт
отдельную decision-запись для каждого компонента. При неполном fingerprint
группировка отключена; похожий текст или общий префикс QF не используются.

Для representative cleaned draft с 3 шкафами и 46 QF без пригодных fingerprints
остаются минимум 50 issue decisions: 3 cabinet, 46 install type и 1 supply
boundary, плюс возможные technical details/assumptions/conflicts. При 46 полностью
одинаковых полных fingerprints install-type часть может быть решена одним
показанным group workflow. Реальный Phase 2.32 draft с preliminary red flags
сначала блокируется и требует исправления upstream.

## Итоговый просмотр и Human Approval

После разрешения исключений CLI выводит Case/confirmation ID, позиции,
количества, шкафы, component codes/labels, install types, доступные
final values, corrected values, resolved conflicts, accepted nontechnical
assumptions, not-applicable details с причинами, removed values, supply boundary,
preliminary red flags, unresolved issue count и вычисленный safety status.
Сводка строится из окончательного payload. Approval phrase запрашивается только
при отсутствии preliminary red flags и unresolved issues и при заполненных
обязательных confirmed fields.

Для публикации нужно вручную ввести точную фразу:

    CONFIRM TECHNICAL COMPOSITION

Любой другой ввод блокирует все outputs. Фраза подтверждает только технический
состав, создание confirmed artifact и возможность отдельного будущего шага
calculator-input draft.

## Output layout

    C:\Users\IgorN\Documents\production_ai_cases\<CaseId>\
      confirmed\
        confirmed-composition-artifact.json
        igor-composition-decisions.json
        igor-composition-decisions.md

Existing confirmed directory никогда не перезаписывается.

Decision JSON является operational audit record, но не вторым source of truth
состава. Он содержит Case/confirmation metadata, exact input hashes,
automatic transfers, corrected values, resolved conflicts, accepted
nontechnical assumptions, not-applicable technical details, removed values
только при фактическом удалении, supply boundary, approval phrase и exact
confirmed-artifact SHA-256. Каждое interactive решение содержит issue ID/kind,
message, source/target paths, original/final values, action и reason, когда она
нужна.

Receipt Markdown формируется только из итогового record/state, содержит counts
items/components и всех типов решений, exact artifact SHA-256 и exact SHA-256
canonical decision JSON. Receipt явно указывает, что полный технический состав
находится в artifact и сам receipt является только краткой audit-сводкой.

Связь однонаправленная:

    decision JSON -> exact confirmed artifact SHA-256
    receipt Markdown -> exact decision JSON SHA-256

Confirmed contract не имеет структурного поля decision-record hash, поэтому
такой hash не записывается в свободный notes.

## Validation и hash-drift protection

До вопросов builder:

1. читает exact bytes manifest, draft и review card;
2. вычисляет SHA-256 без нормализации;
3. запускает существующие preliminary validator и source-bundle verifier;
4. проверяет присутствие в review card существующих draft ID и manifest-hash
   markers.

После approval phrase все три файла читаются повторно. Любой hash drift
блокирует публикацию.

Review card содержит human-readable draft ID и raw_input_sha256, но не содержит
exact preliminary-draft hash. Поэтому существующий формат не позволяет
полностью криптографически доказать принадлежность card конкретным draft bytes.
Builder не парсит свободный Markdown как источник состава: он проверяет только
доказуемые identity markers и фиксирует exact review-card hash в decision
record и confirmed source links.

## Atomic publication и Windows

Builder создаёт уникальный staging directory внутри Case directory, то есть на
том же volume. В staging полностью записываются artifact, decision JSON и
receipt. Файлы закрываются после flush и file-level fsync; staged artifact
проходит существующий confirmed validator, а root red_flags дополнительно
должен быть пустым.

После этого staging directory одним rename публикуется как confirmed.
Overwrite запрещён. При обычной ошибке staging удаляется, а canonical
confirmed отсутствует.

Гарантия ограничена возможностями стандартной библиотеки Windows: same-volume
directory rename защищает от частичной обычной публикации, но builder не
обещает POSIX directory fsync или абсолютную durability при внезапной потере
питания/сбое файловой системы. После аварийного завершения следует проверить и
удалить только оставшийся .confirmed-staging-*; существующий confirmed
автоматически не изменять.

## Следующий ручной шаг

После успешного builder оператор отдельно запускает существующий envelope
exporter, передавая canonical external path:

    C:\Users\IgorN\Documents\production_ai_cases\<CaseId>\
      confirmed\confirmed-composition-artifact.json

Envelope export, consumer validation и calculator-input draft не являются
частью этой команды и требуют отдельных безопасных шагов.

Успех builder не разрешает:

- calculator или финальную цену;
- срок и коммерческие условия;
- CSV, XLSX или КП;
- отправку клиенту;
- закупку, резерв или предоплату;
- запуск цеха или производство.
