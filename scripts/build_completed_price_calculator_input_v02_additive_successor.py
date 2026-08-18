"""Build an immutable additive v0.2 completed-input successor for ШУ-Т1.

The builder is deliberately case-scoped.  It validates three direct Igor Human
Decision artifacts, preserves the complete 14-group/109-row parent prefix and
publishes a successor only through an exclusive sibling-file link.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ID = "2024/086"
BASE_SCHEMA = "price_calculator_input_draft.v0.2"
BASE_STATUS = "V02_TECHNICAL_COMPLETION_APPLIED_NOT_PRICED"
MAPPING_STATUS = "APPROVED_HUMAN_DECISIONS_APPLIED"
SUCCESSOR_CONTRACT = "controlled_additive_completed_input_successor.v0.1"
PUBLICATION_AUTHORIZATION = "IGOR_SHU_T1_TECHNICAL_SUCCESSOR_PUBLICATION_AUTHORIZED"
REPO_ROOT = Path(__file__).resolve().parents[1]

BASE_COMPLETED_INPUT = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-PRICE-CALCULATOR-APPLICATION-20260812-001\price-calculator-input-v0.2-completed.json"
)
BASE_COMPLETED_INPUT_SHA256 = (
    "71d933c14a603c24ba8072311b84992d1708cbc7ff1fede59727e727218f5bdb"
)
COMPOSITION_DECISION = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-SHU-T1-HUMAN-DECISIONS-20260817-001\technical-shu-t1-composition-human-decisions-v0.1.json"
)
COMPOSITION_SHA256 = "bccf62150488037b7df50804c88454119748be103da22dad456db2969126c008"
CABINET_PRICING_DECISION = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-SHU-T1-CABINET-PRICING-DECISION-20260817-001\technical-shu-t1-cabinet-pricing-human-decisions-v0.1.json"
)
CABINET_PRICING_SHA256 = (
    "b3a1bb84bacb2cc5127752cb378b2151552fcb443f02116b12269a086add4247"
)
RT820_DECISION = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-RT820-CODE-INSTALL-DECISION-20260818-001\technical-rt820-code-install-human-decisions-v0.1.json"
)
RT820_SHA256 = "95c9f2610a6e8429242789e17c3b69ffae31db28655736aed12caa1d3939630f"

DECISION_CONTRACTS = (
    (
        "technical_composition_human_decision",
        COMPOSITION_DECISION,
        COMPOSITION_SHA256,
        "technical_shu_t1_composition_human_decisions.v0.1",
        "IGOR_SHU_T1_COMPOSITION_APPROVED_NOT_APPLIED",
        "IGOR-SHU-T1-COMPOSITION-2024-086-001",
    ),
    (
        "cabinet_pricing_human_decision",
        CABINET_PRICING_DECISION,
        CABINET_PRICING_SHA256,
        "technical_shu_t1_cabinet_pricing_human_decisions.v0.1",
        "APPROVED_NOT_APPLIED",
        "IGOR-SHU-T1-CABINET-PRICING-2024-086-001",
    ),
    (
        "rt820_code_install_human_decision",
        RT820_DECISION,
        RT820_SHA256,
        "technical_rt820_code_install_human_decisions.v0.1",
        "IGOR_RT820_CODE_INSTALL_APPROVED_NOT_APPLIED",
        "IGOR-RT820-CODE-INSTALL-2024-086-001",
    ),
)

EXPECTED_SCOPE = (
    ("9", "TFE-006", 11, 27),
    ("11", "TFE-029", 35, 53),
    ("13", "TFE-052", 55, 75),
    ("15", "TFE-074", 78, 100),
)
RT_EVIDENCE = ("COMP-006", "COMP-056", "COMP-106", "COMP-153")
TST05_EVIDENCE = ("COMP-009", "COMP-059", "COMP-109", "COMP-156")
AD12_EVIDENCE = ("COMP-007", "COMP-057", "COMP-107", "COMP-154")
VA_EVIDENCE = ("COMP-008", "COMP-058", "COMP-108", "COMP-155")


class ContractError(ValueError):
    """Raised when an input or successor violates the exact contract."""


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path, description: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read {description}: {path}: {exc}") from exc
    try:
        value = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid {description}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{description} root must be an object")
    return value, raw


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def exact_binding(
    role: str,
    path: Path,
    sha256: str,
    schema: str,
    status: str,
    decision_id: str,
) -> dict[str, Any]:
    return {
        "role": role,
        "path": str(path),
        "sha256": sha256,
        "schema_version": schema,
        "status": status,
        "decision_id": decision_id,
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_APPLIED",
    }


def validate_base(base: Mapping[str, Any]) -> None:
    rows = base.get("calculator_input_format", {}).get("row_drafts")
    groups = base.get("cabinet_groups")
    completion = base.get("completion")
    require(base.get("schema_version") == BASE_SCHEMA, "base schema mismatch")
    require(
        base.get("draft_type") == "price_calculator_input_draft", "base type mismatch"
    )
    require(isinstance(groups, list) and len(groups) == 14, "base requires 14 groups")
    require(isinstance(rows, list) and len(rows) == 109, "base requires 109 rows")
    require(isinstance(completion, Mapping), "base completion missing")
    require(completion.get("status") == BASE_STATUS, "base completion status mismatch")
    require(
        completion.get("authorization_claim_is_not_human_approval") is True,
        "base authorization boundary mismatch",
    )
    require(
        completion.get("scope")
        == {
            "component_groups": 31,
            "rows": "109/109",
            "cabinet_groups": "14/14",
            "duplicate_component_membership": 0,
            "duplicate_cabinet_membership": 0,
            "scope_expansion": False,
        },
        "base completion scope mismatch",
    )
    require(
        base.get("coverage")
        == {
            "installed_component_count": 121,
            "direct_installed_component_count": 107,
            "aggregate_member_count": 14,
            "aggregate_decision_count": 2,
            "pricing_row_draft_count": 109,
            "cabinet_group_count": 14,
            "reserved_meter_space_count": 4,
            "reserved_excluded_from_pricing_count": 4,
            "correction_count": 12,
            "reconfirmation_count": 6,
        },
        "base coverage mismatch",
    )
    safety = base.get("safety")
    require(
        isinstance(safety, Mapping)
        and bool(safety)
        and all(value is False for value in safety.values()),
        "base safety flags must all be false",
    )


def validate_decision_identity(
    decision: Mapping[str, Any], contract: tuple[str, Path, str, str, str, str]
) -> None:
    role, _path, _sha, schema, status, decision_id = contract
    authority = decision.get("authority")
    if isinstance(authority, Mapping):
        authority = authority.get("authority")
    require(decision.get("schema_version") == schema, f"{role} schema mismatch")
    require(decision.get("status") == status, f"{role} status mismatch")
    require(decision.get("decision_id") == decision_id, f"{role} decision ID mismatch")
    require(authority == "IGOR_DIRECT_HUMAN_APPROVAL", f"{role} authority mismatch")
    require(decision.get("application_status") == "NOT_APPLIED", f"{role} applied")
    require(decision.get("scope_expansion") is False, f"{role} scope expansion")
    require(decision.get("immutable") is True, f"{role} is not immutable")
    require(decision.get("no_overwrite") is True, f"{role} permits overwrite")


def validate_human_contracts(
    composition: Mapping[str, Any],
    cabinet: Mapping[str, Any],
    rt820: Mapping[str, Any],
) -> None:
    for decision, contract in zip(
        (composition, cabinet, rt820), DECISION_CONTRACTS, strict=True
    ):
        validate_decision_identity(decision, contract)

    expected_composition_scope = [
        {
            "section": section,
            "invoice_position": invoice_position,
            "excel_row": excel_row,
            "technical_position_id": position,
            "physical_quantity": 1,
        }
        for section, position, invoice_position, excel_row in EXPECTED_SCOPE
    ]
    require(
        composition.get("exact_scope") == expected_composition_scope,
        "composition exact scope mismatch",
    )
    require(
        composition.get("ordered_component_evidence_ids")
        == [
            "COMP-006",
            "COMP-007",
            "COMP-008",
            "COMP-009",
            "COMP-056",
            "COMP-057",
            "COMP-058",
            "COMP-059",
            "COMP-106",
            "COMP-107",
            "COMP-108",
            "COMP-109",
            "COMP-153",
            "COMP-154",
            "COMP-155",
            "COMP-156",
        ],
        "composition evidence coverage mismatch",
    )

    cabinet_scope = cabinet.get("exact_scope")
    cabinet_contract = cabinet.get("cabinet_decision")
    pricing = cabinet.get("component_pricing_decisions")
    calculation = cabinet.get("calculation_contract")
    require(isinstance(cabinet_scope, Mapping), "cabinet exact scope missing")
    require(
        cabinet_scope.get("product") == "ШУ-Т1"
        and cabinet_scope.get("sections_in_order") == ["9", "11", "13", "15"]
        and cabinet_scope.get("physical_cabinets") == 4,
        "cabinet scope mismatch",
    )
    require(isinstance(cabinet_contract, Mapping), "cabinet decision missing")
    require(
        cabinet_contract.get("source_template") == "ЩРН-12"
        and cabinet_contract.get("X_cabinet_base_kzt") == 6936
        and cabinet_contract.get("I_additional_cabinet_cost_kzt") == 0
        and cabinet_contract.get("cabinet_base_counted_exactly_once") is True
        and cabinet_contract.get("technical_equivalence_asserted") is False,
        "cabinet replacement contract mismatch",
    )
    require(
        isinstance(pricing, list) and len(pricing) == 3, "component pricing mismatch"
    )
    require(
        [item.get("manufacturer_article") for item in pricing]
        == ["RT-820", "DA12-16-30-bas", "mcb4729-2-10C"],
        "component articles mismatch",
    )
    require(isinstance(calculation, Mapping), "calculation contract missing")
    require(
        calculation.get("inputs_kzt") == {"X": 6936, "I": 0, "G": 20450, "H": 1764}
        and calculation.get("approved_calculated_unit_price_kzt") == 53763
        and calculation.get("approved_calculated_exact_scope_total_kzt") == 215052,
        "approved ШУ-Т1 calculation mismatch",
    )

    approved = rt820.get("approved_code_install_contract")
    work = rt820.get("pricing_work_semantics")
    tst = rt820.get("tst05_bundle_semantics")
    isolation = rt820.get("scope_isolation")
    require(
        approved
        == {
            "manufacturer": "EKF",
            "product": "Реле температуры RT-820 EKF PROxima",
            "manufacturer_article": "RT-820",
            "supply_form": "ONE_TEMPERATURE_RELAY_WITH_ONE_EXTERNAL_TEMPERATURE_SENSOR",
            "internal_component_code": "EKF-RT-820",
            "install_type": "temperature_relay_din_2mod",
            "module_width_din": 2,
            "quantity_per_individual_cabinet": 1,
            "unit": "комплект",
            "decision_status": "APPROVED_NOT_APPLIED",
            "application_status": "NOT_APPLIED",
        },
        "RT-820 code/install contract mismatch",
    )
    require(isinstance(work, Mapping), "RT-820 work contract missing")
    require(
        work.get("material_source") == "КРН!B19"
        and work.get("material_price_kzt_per_complete_set") == 15000
        and work.get("work_source") == "КРН!C19"
        and work.get("work_price_kzt_per_complete_set") == 900
        and work.get("work_price_semantics") == "EXACT_COMPONENT_WORK_PRICE"
        and work.get("generic_modular_2p_work_price_prohibited") is True
        and work.get("family_fallback_prohibited") is True
        and work.get("fuzzy_fallback_prohibited") is True,
        "RT-820 exact work/fallback contract mismatch",
    )
    require(isinstance(tst, Mapping), "TST05 contract missing")
    require(
        tst.get("source_evidence_preserved_in_provenance") is True
        and tst.get("separate_component_row") is False
        and tst.get("separate_material_charge") is False
        and tst.get("separate_work_charge") is False,
        "TST05 bundle contract mismatch",
    )
    require(
        isinstance(isolation, Mapping)
        and isolation.get("case_scoped_only") is True
        and isolation.get("family_wide_mapping_created") is False
        and isolation.get("other_project_reuse_authorized") is False,
        "RT-820 scope isolation mismatch",
    )


def successor_bindings() -> list[dict[str, Any]]:
    return [exact_binding(*contract) for contract in DECISION_CONTRACTS]


def appended_group() -> dict[str, Any]:
    return {
        "cabinet_group_id": "CABINET-GROUP-015",
        "source_cabinet_template": "ЩРН-12",
        "product_name": "ШУ-Т1",
        "cabinet_code": "CAB-KRN-12",
        "cabinet_label": "Корпус КРН-12 265×330×100 мм, металл",
        "consumables_factor": 1.2,
        "mapping_status": MAPPING_STATUS,
        "row_draft_ids": ["ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112"],
    }


def source_quantity(decision_kind: str) -> dict[str, Any]:
    return {
        "decision_id": "IGOR-SHU-T1-COMPOSITION-2024-086-001",
        "decision_kind": decision_kind,
        "quantity_per_individual_cabinet": 1,
        "applies_once_per_cabinet": True,
        "multiply_by_member_count": False,
        "scope_expansion": False,
    }


def appended_rows() -> list[dict[str, Any]]:
    common_values = {
        "product_name": "ШУ-Т1",
        "cabinet_code": "CAB-KRN-12",
        "consumables_factor": 1.2,
    }
    return [
        {
            "row_id": "ROW-DRAFT-0110",
            "cabinet_group_id": "CABINET-GROUP-015",
            "calculator_values": {
                **common_values,
                "component_code": "EKF-RT-820",
                "component_qty": 1,
                "install_type": "temperature_relay_din_2mod",
            },
            "source_quantity": source_quantity("DIRECT_PER_CABINET_COMPLETE_SET"),
            "source_component_evidence_ids": [
                *RT_EVIDENCE,
                *TST05_EVIDENCE,
            ],
            "approved_signature": {
                "manufacturer": "EKF",
                "product": "Реле температуры RT-820 EKF PROxima",
                "manufacturer_article": "RT-820",
                "supply_form": (
                    "ONE_TEMPERATURE_RELAY_WITH_ONE_EXTERNAL_TEMPERATURE_SENSOR"
                ),
                "module_width_din": 2,
                "TST05_evidence_included_as_provenance_only": True,
                "TST05_separate_component_row": False,
            },
            "mapping_status": MAPPING_STATUS,
            "component_label": "Реле температуры RT-820 EKF PROxima с внешним датчиком",
        },
        {
            "row_id": "ROW-DRAFT-0111",
            "cabinet_group_id": "CABINET-GROUP-015",
            "calculator_values": {
                **common_values,
                "component_code": "EKF-AD12-1P-N-C16-30MA-4P5KA",
                "component_qty": 1,
                "install_type": "diff_1p_n",
            },
            "source_quantity": source_quantity("DIRECT_PER_CABINET_COMPONENT"),
            "source_component_evidence_ids": list(AD12_EVIDENCE),
            "approved_signature": {
                "manufacturer": "EKF",
                "product": "АД12 Basic",
                "manufacturer_article": "DA12-16-30-bas",
                "poles": "1P+N",
                "nominal_current": "16A",
                "residual_current": "30mA",
                "breaking_capacity": "4.5kA",
            },
            "mapping_status": MAPPING_STATUS,
            "component_label": "АД12 Basic АВДТ 2P C16/30мА 4.5kA",
        },
        {
            "row_id": "ROW-DRAFT-0112",
            "cabinet_group_id": "CABINET-GROUP-015",
            "calculator_values": {
                **common_values,
                "component_code": "EKF-VA47-29-2P",
                "component_qty": 1,
                "install_type": "modular_2p",
            },
            "source_quantity": source_quantity("DIRECT_PER_CABINET_COMPONENT"),
            "source_component_evidence_ids": list(VA_EVIDENCE),
            "approved_signature": {
                "manufacturer": "EKF",
                "product": "ВА47-29 BASIC 2P C10",
                "manufacturer_article": "mcb4729-2-10C",
                "poles": "2P",
                "nominal_current": "10A",
                "characteristic": "C",
                "breaking_capacity": "4.5kA",
            },
            "mapping_status": MAPPING_STATUS,
            "component_label": (
                "Автоматический выключатель ВА47-29 BASIC 2P C10 4.5kA"
            ),
        },
    ]


def build_successor_payload(
    base: Mapping[str, Any],
    composition: Mapping[str, Any],
    cabinet: Mapping[str, Any],
    rt820: Mapping[str, Any],
) -> dict[str, Any]:
    validate_base(base)
    validate_human_contracts(composition, cabinet, rt820)
    successor = copy.deepcopy(dict(base))
    successor["source"]["additive_completed_input_successor"] = {
        "contract": SUCCESSOR_CONTRACT,
        "project_id": PROJECT_ID,
        "parent": {
            "path": str(BASE_COMPLETED_INPUT),
            "sha256": BASE_COMPLETED_INPUT_SHA256,
        },
        "direct_human_decision_inputs": successor_bindings(),
        "append_only": True,
        "scope_expansion": False,
    }
    successor["cabinet_groups"].append(appended_group())
    successor["calculator_input_format"]["row_drafts"].extend(appended_rows())
    successor["coverage"].update(
        {
            "installed_component_count": 124,
            "direct_installed_component_count": 110,
            "pricing_row_draft_count": 112,
            "cabinet_group_count": 15,
        }
    )
    successor["completion"]["scope"].update(
        {
            "component_groups": 34,
            "rows": "112/112",
            "cabinet_groups": "15/15",
        }
    )
    successor["completion"]["additive_successor"] = {
        "contract": SUCCESSOR_CONTRACT,
        "application_status": "NOT_APPLIED",
        "pricing_calculation_executed": False,
        "successor_publication_requires_separate_exact_igor_authorization": True,
    }
    validate_successor_payload(successor, base)
    return successor


def validate_successor_payload(
    successor: Mapping[str, Any], base: Mapping[str, Any]
) -> None:
    validate_base(base)
    groups = successor.get("cabinet_groups")
    rows = successor.get("calculator_input_format", {}).get("row_drafts")
    require(
        isinstance(groups, list) and len(groups) == 15, "successor requires 15 groups"
    )
    require(isinstance(rows, list) and len(rows) == 112, "successor requires 112 rows")
    require(groups[:14] == base["cabinet_groups"], "base cabinet-group prefix changed")
    require(
        rows[:109] == base["calculator_input_format"]["row_drafts"],
        "base row prefix changed",
    )
    require(groups[14] == appended_group(), "appended ШУ-Т1 group mismatch")
    require(rows[109:] == appended_rows(), "appended ШУ-Т1 rows mismatch")
    require(
        len({row["row_id"] for row in rows}) == 112,
        "row ID collision",
    )
    require(
        len({group["cabinet_group_id"] for group in groups}) == 15,
        "cabinet-group ID collision",
    )
    require(
        successor.get("coverage")
        == {
            **base["coverage"],
            "installed_component_count": 124,
            "direct_installed_component_count": 110,
            "pricing_row_draft_count": 112,
            "cabinet_group_count": 15,
        },
        "successor coverage mismatch",
    )
    completion = successor.get("completion")
    require(isinstance(completion, Mapping), "successor completion missing")
    require(
        completion.get("scope")
        == {
            **base["completion"]["scope"],
            "component_groups": 34,
            "rows": "112/112",
            "cabinet_groups": "15/15",
        },
        "successor completion scope mismatch",
    )
    metadata = successor.get("source", {}).get("additive_completed_input_successor")
    require(isinstance(metadata, Mapping), "successor metadata missing")
    require(
        metadata.get("contract") == SUCCESSOR_CONTRACT
        and metadata.get("parent")
        == {"path": str(BASE_COMPLETED_INPUT), "sha256": BASE_COMPLETED_INPUT_SHA256}
        and metadata.get("direct_human_decision_inputs") == successor_bindings()
        and metadata.get("append_only") is True
        and metadata.get("scope_expansion") is False,
        "successor exact bindings mismatch",
    )
    require(
        all(value is False for value in successor.get("safety", {}).values()),
        "successor safety flag became true",
    )
    require(
        sum(row["calculator_values"]["component_code"] == "EKF-RT-820" for row in rows)
        == 1,
        "RT-820 must have exactly one component row",
    )
    require(
        all("TST05" not in row["calculator_values"]["component_code"] for row in rows),
        "TST05 separate component row is forbidden",
    )


def serialize(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def ensure_external_output(output: Path) -> None:
    resolved = output.resolve(strict=False)
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return
    raise ContractError("successor output must be outside the repository")


def publish_successor(output: Path) -> str:
    ensure_external_output(output)
    require(output.parent.is_dir(), "target directory must already exist")
    require(not output.exists(), "output already exists; overwrite is forbidden")

    input_specs = (
        (BASE_COMPLETED_INPUT, BASE_COMPLETED_INPUT_SHA256, "base completed input"),
        *(
            (path, sha, role)
            for role, path, sha, _schema, _status, _decision_id in DECISION_CONTRACTS
        ),
    )
    loaded: list[tuple[dict[str, Any], bytes]] = []
    for path, expected_sha, description in input_specs:
        value, raw = load_json(path, description)
        require(
            sha256_bytes(raw) == expected_sha, f"initial SHA mismatch: {description}"
        )
        loaded.append((value, raw))
    base, composition, cabinet, rt820 = (item[0] for item in loaded)
    payload = build_successor_payload(base, composition, cabinet, rt820)
    encoded = serialize(payload)

    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".staging", dir=output.parent
    )
    staging = Path(staging_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        for (path, expected_sha, description), (_value, initial_raw) in zip(
            input_specs, loaded, strict=True
        ):
            current = path.read_bytes()
            require(current == initial_raw, f"TOCTOU bytes changed: {description}")
            require(
                sha256_bytes(current) == expected_sha,
                f"TOCTOU SHA mismatch: {description}",
            )
        require(not output.exists(), "output appeared before publication")
        os.link(staging, output)
        published, published_raw = load_json(output, "published successor")
        require(published_raw == encoded, "published bytes mismatch")
        validate_successor_payload(published, base)
        return sha256_bytes(published_raw)
    finally:
        try:
            staging.unlink()
        except FileNotFoundError:
            pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorization", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.authorization != PUBLICATION_AUTHORIZATION:
        raise ContractError(
            "exact technical-successor publication acknowledgement is required"
        )
    digest = publish_successor(args.output)
    print(f"PUBLISHED_IMMUTABLE_NO_OVERWRITE {args.output} SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
