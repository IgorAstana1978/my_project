from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = PROJECT_ROOT / "scripts" / "build_component_replay_readiness_bundle.py"
VALIDATOR_PATH = (
    PROJECT_ROOT / "scripts" / "validate_component_replay_readiness_bundle.py"
)
POLICY_OWNER = PROJECT_ROOT / "scripts" / "project_spec_extraction.py"
PROJECT_ID = "PROJECT-SYNTHETIC"
PROTECTED_IDS = ("COMP-034", "COMP-088", "COMP-131", "COMP-181")


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = cast(Any, load_module("direct_replay_builder_for_tests", BUILDER_PATH))
validator = cast(Any, load_module("direct_replay_validator_for_tests", VALIDATOR_PATH))


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def provenance(row: int) -> dict[str, Any]:
    return {
        "pdf": "Synthetic section.pdf",
        "pdf_sha256": "a" * 64,
        "page": 1,
        "specification_position_or_locator": "synthetic_position=1",
        "source_decision_ids": [f"DEC-{row:03d}"],
        "source_record_ids": [f"SRC-{row:03d}"],
        "row_locator": f"component_row={row}",
    }


def not_found_placeholder(row: int, reason: str) -> dict[str, Any]:
    return {
        "value": None,
        "status": "NOT_FOUND",
        "reason": reason,
        "provenance": provenance(row),
    }


def application_record(
    *,
    index: int,
    evidence_id: str,
    classification: str,
    label: str,
    field: str,
    raw_quantity: Any,
    raw_type_model: Any = None,
    route: str = "SYNTHETIC_ROUTE",
) -> dict[str, Any]:
    return {
        "record_id": f"ICF-{index:03d}",
        "component_evidence_id": evidence_id,
        "evidence_position_id": "TFE-001",
        "section": "9",
        "field": field,
        "component_or_apparatus_class": "COMPONENT",
        "applicability_classification": classification,
        "remediation_route": route,
        "determination": f"Synthetic frozen determination {index}",
        "raw_designation": label,
        "raw_quantity": raw_quantity,
        "raw_type_model": raw_type_model,
        "raw_ratings": None,
        "value_applied": False,
        "approval_created": False,
        "not_an_approval": True,
    }


def applicability_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    index = 1
    for offset in range(29):
        records.append(
            application_record(
                index=index,
                evidence_id=f"COMP-NPE-{offset:03d}",
                classification="FIELD_NOT_APPLICABLE_SUPPORTED_BY_CONTRACT",
                label="Шина N и PE",
                field="row_level_rating",
                raw_quantity=None,
                route="NO_DATA_ACTION_FIELD_NOT_APPLICABLE",
            )
        )
        index += 1
    for offset in range(16):
        records.append(
            application_record(
                index=index,
                evidence_id=f"COMP-METER-{offset:03d}",
                classification="FIELD_SEMANTICS_MISMATCH",
                label="Счетчик учета электроэнергии - 3шт",
                field="row_level_rating",
                raw_quantity=3,
                raw_type_model="СО-Э711 R TX P IPП RS Z Д",
                route="SCHEMA_OR_VALIDATOR_CHANGE_REQUIRED",
            )
        )
        index += 1
    for offset in range(4):
        records.append(
            application_record(
                index=index,
                evidence_id=f"COMP-REG-{offset:03d}",
                classification="EXPLICIT_RAW_VALUE_NOT_NORMALIZED",
                label="Регулятор РТ 007S(с датчиком температуры TST05) шт - 1шт",
                field="row_level_rating",
                raw_quantity=1,
                route="NORMALIZER_CORRECTION_REQUIRED",
            )
        )
        index += 1
    for evidence_id in PROTECTED_IDS:
        records.append(
            application_record(
                index=index,
                evidence_id=evidence_id,
                classification="EXPLICIT_RAW_VALUE_NOT_NORMALIZED",
                label="Датчик температуры TST05 шт - 5шт",
                field="row_level_rating",
                raw_quantity=5,
                route="NORMALIZER_CORRECTION_REQUIRED",
            )
        )
        index += 1
    for offset in range(26):
        records.append(
            application_record(
                index=index,
                evidence_id=f"COMP-QMISS-{offset:03d}",
                classification="REQUIRED_VALUE_MISSING",
                label="Автоматический выключатель",
                field="quantity_per_cabinet",
                raw_quantity=None,
                route="NEW_ENGINEERING_SOURCE_REQUIRED",
            )
        )
        index += 1
    for offset in range(3):
        records.append(
            application_record(
                index=index,
                evidence_id=f"COMP-QCONFLICT-{offset:03d}",
                classification="REQUIRED_VALUE_CONFLICTED",
                label="Автоматический выключатель",
                field="quantity_per_cabinet",
                raw_quantity=None,
                route="EXTRACTOR_ROW_ALIGNMENT_CORRECTION_REQUIRED",
            )
        )
        index += 1
    assert len(records) == 82
    return records


def classification_counts() -> dict[str, int]:
    return {
        "EXPLICIT_RAW_VALUE_NOT_NORMALIZED": 8,
        "FIELD_NOT_APPLICABLE_BUT_SCHEMA_CHANGE_REQUIRED": 0,
        "FIELD_NOT_APPLICABLE_SUPPORTED_BY_CONTRACT": 29,
        "FIELD_SEMANTICS_MISMATCH": 16,
        "REQUIRED_VALUE_CONFLICTED": 3,
        "REQUIRED_VALUE_MISSING": 26,
        "UNDETERMINED_REQUIRES_IGOR": 0,
    }


def cumulative_review(records: list[dict[str, Any]]) -> dict[str, Any]:
    components = [
        {
            "value": (
                "Шина N/PE"
                if record["applicability_classification"]
                == "FIELD_NOT_APPLICABLE_SUPPORTED_BY_CONTRACT"
                else (
                    "РЕГУЛЯТОР"
                    if record["component_evidence_id"].startswith("COMP-REG-")
                    else (
                        "ДАТЧИК ТЕМПЕРАТУРЫ"
                        if record["component_evidence_id"] in PROTECTED_IDS
                        else record["raw_designation"]
                    )
                )
            ),
            "status": "PROJECT_EVIDENCE_UNAPPROVED",
            "component_evidence_id": record["component_evidence_id"],
            "provenance": provenance(index),
        }
        for index, record in enumerate(records, start=1)
    ]
    return {
        "schema_version": ("technical_field_component_scheme_completion_review.v0.1"),
        "case_id": "CASE-CUMULATIVE-SYNTHETIC",
        "project_id": PROJECT_ID,
        "artifact_status": "REVIEW_ONLY_NOT_CONFIRMED",
        "positions": [
            {
                "evidence_position_id": "TFE-001",
                "existing_review_position_id": "REVIEW-POS-001",
                "canonical_identity": {
                    "section_id": "9",
                    "discipline": "ЭОМ",
                    "canonical_designation": "ШУ-Т1",
                },
                "project_source": {
                    "pdf": "Synthetic section.pdf",
                    "pdf_sha256": "a" * 64,
                },
                "quantity": {
                    "value": 5,
                    "status": "FROZEN_APPROVED_QUANTITY",
                },
                "technical_fields": {
                    "components": {
                        "resolution_status": "PROJECT_EVIDENCE_UNAPPROVED",
                        "evidence_values": components,
                    },
                    "apparatus": {"evidence_values": []},
                    "ratings": {"evidence_values": []},
                    "scheme": thermostat_scheme("ШУ-Т1"),
                },
            },
            {
                "evidence_position_id": "TFE-002",
                "existing_review_position_id": "REVIEW-POS-002",
                "canonical_identity": {
                    "section_id": "12",
                    "discipline": "ЭОМ",
                    "canonical_designation": "EMPTY",
                },
                "project_source": {
                    "pdf": "Synthetic second section.pdf",
                    "pdf_sha256": "b" * 64,
                },
                "quantity": {
                    "value": 1,
                    "status": "FROZEN_APPROVED_QUANTITY",
                },
                "technical_fields": {
                    "components": {
                        "resolution_status": "NOT_FOUND",
                        "evidence_values": [
                            not_found_placeholder(
                                999,
                                "No component in frozen position",
                            )
                        ],
                    },
                    "apparatus": {
                        "resolution_status": "NOT_FOUND",
                        "evidence_values": [
                            not_found_placeholder(
                                1000,
                                "No apparatus in frozen position",
                            )
                        ],
                    },
                    "ratings": {
                        "resolution_status": "NOT_FOUND",
                        "evidence_values": [
                            not_found_placeholder(
                                1001,
                                "No ratings in frozen position",
                            )
                        ],
                    },
                },
            },
            *[
                {
                    "evidence_position_id": f"TFE-RT-{section}",
                    "existing_review_position_id": f"REVIEW-RT-{section}",
                    "canonical_identity": {
                        "section_id": section,
                        "discipline": "ЭОМ",
                        "canonical_designation": "ШУ-Т1",
                    },
                    "project_source": {
                        "pdf": f"Synthetic section {section}.pdf",
                        "pdf_sha256": section[0] * 64,
                    },
                    "quantity": {
                        "value": 1,
                        "status": "FROZEN_APPROVED_QUANTITY",
                    },
                    "technical_fields": {
                        "components": {"evidence_values": []},
                        "apparatus": {"evidence_values": []},
                        "ratings": {"evidence_values": []},
                        "scheme": thermostat_scheme("ШУ-Т1"),
                    },
                }
                for section in ("11", "13", "15")
            ],
            {
                "evidence_position_id": "TFE-RT-10",
                "existing_review_position_id": "REVIEW-RT-10",
                "canonical_identity": {
                    "section_id": "10",
                    "discipline": "ЭОМ",
                    "canonical_designation": "ШУ-Т2",
                },
                "project_source": {
                    "pdf": "Synthetic section 10.pdf",
                    "pdf_sha256": "c" * 64,
                },
                "quantity": {
                    "value": 1,
                    "status": "FROZEN_APPROVED_QUANTITY",
                },
                "technical_fields": {
                    "components": {"evidence_values": []},
                    "apparatus": {"evidence_values": []},
                    "ratings": {"evidence_values": []},
                    "scheme": thermostat_scheme("ШУ-Т2"),
                },
            },
        ],
        "controls": {
            "external_shu_t1_source_rows": 16,
            "new_evidence_ids_for_external_rows": 0,
            "external_rows_included_in_composition_price_procurement_production": 0,
            "rt_820_complete_set_records": 4,
            "separate_tst05_commercial_rows": 0,
            "separate_tst05_pricing_rows": 0,
            "separate_tst05_procurement_rows": 0,
            "calculator_run": False,
            "confirmed_composition_created": False,
            "pricing_executed": False,
            "procurement_started": False,
            "production_started": False,
        },
    }


def field_applicability(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "unresolved_field_applicability_audit.v0.1",
        "case_id": "CASE-APPLICABILITY-SYNTHETIC",
        "project_id": PROJECT_ID,
        "artifact_status": "READY_FOR_HUMAN_FIELD_APPLICABILITY_REVIEW",
        "classification_counts": classification_counts(),
        "classification_total": 82,
        "records": records,
        "additional_blockers_outside_82": [
            {
                "blocker_id": "CONFIRMED_INSTALL_TYPE_GAP_FOR_N_PE_BUS",
                "meaning": "Synthetic N/PE install type remains unresolved.",
                "included_in_field_count": False,
                "schema_or_validator_changed": False,
                "install_type_selected": False,
                "next_boundary": "separate bounded design decision",
            }
        ],
        "safety_flags": {
            "calculator_run": False,
            "confirmed_composition_created": False,
            "pricing_executed": False,
            "procurement_started": False,
            "production_started": False,
        },
    }


AUTHORITY_DATA = {
    "017": (
        "human_decisions_batch.v0.17",
        "human_decisions_batch.v0.16",
        None,
        ("CE1", "CE2A", "CE2B", "D1A"),
        "IGOR_HUMAN_APPROVAL",
    ),
    "018": (
        "human_decisions_batch.v0.18",
        "human_decisions_batch.v0.17",
        None,
        ("IP1",),
        "IGOR_HUMAN_APPROVAL",
    ),
    "019": (
        "human_decisions_batch.v0.19",
        "human_decisions_batch.v0.18",
        "018",
        ("H19-1", "H19-2", "H19-3", "H19-4"),
        "IGOR_DIRECT_HUMAN_APPROVAL",
    ),
    "020": (
        "human_decisions_batch.v0.20",
        "human_decisions_batch.v0.19",
        "019",
        ("H20-1", "H20-2", "H20-3", "H20-4"),
        "IGOR_DIRECT_HUMAN_APPROVAL",
    ),
}


def thermostat_scheme(designation: str) -> dict[str, Any]:
    return {
        "resolution_status": "PROJECT_EVIDENCE_UNAPPROVED",
        "evidence_values": [
            {
                "value": "SCHEME_OR_QUESTIONNAIRE_PAGE",
                "status": "PROJECT_EVIDENCE_UNAPPROVED",
                "source_role": "PROJECT_SCHEME_OR_QUESTIONNAIRE",
                "raw_text_excerpt": (
                    f"{designation} | QF Регулятор РТ 007S"
                    "(с датчиком температуры TST05) шт 1"
                ),
                "provenance": provenance(700),
            }
        ],
        "classification": "REFERENCE_ONLY_NO_TECHNICAL_SCHEME_VALUE",
        "source_reference_preserved": True,
        "technical_scheme_value_approved": False,
        "scheme_content_approved": False,
        "standalone_scheme_field_required_for_confirmed_composition": False,
    }


def rt007s_rule_payload() -> dict[str, Any]:
    return {
        "rule_id": "IGOR_COMMERCIAL_NOMENCLATURE_RULE_SHU_T1_THERMOSTAT_V1",
        "target_designation": "ШУ-Т1",
        "forbidden_transfer_designation": "ШУ-Т2",
        "sections": ["9", "11", "13", "15"],
        "commercial_item_name": "Терморегулятор RT-820, комплект с датчиком",
        "bridge_commercial_item_name": "Терморегулятор",
        "future_price_lookup_name": "Терморегулятор RT-820",
        "commercial_quantity_per_cabinet": 1,
        "supply_form": "COMPLETE_SET_WITH_TEMPERATURE_SENSOR",
        "bundle_members": [
            {"name": "Регулятор РТ 007S", "quantity": 1},
            {"name": "Датчик температуры TST05", "quantity": 1},
        ],
        "bridge_status": "COMMERCIAL_GROUPING_RULE_APPROVED_BY_IGOR",
        "application_status": "NOT_EXECUTED",
        "anti_double_counting": True,
        "raw_source_evidence_preserved": True,
        "technical_source_rows": "PRESERVED_SEPARATELY",
        "technical_model_equivalence": "NOT_ASSERTED",
        "commercial_item_per_cabinet": "ONE_COMPLETE_SET",
        "technical_approval_created": False,
        "pricing_executed": False,
        "confirmed_composition_created": False,
    }


def h19_3_decision(authority: str) -> dict[str, Any]:
    payload = rt007s_rule_payload()
    return {
        "decision_id": "HDA-019-H19-3",
        "decision_code": "H19-3",
        "decision_type": "COMMERCIAL_THERMOSTAT_COMPLETE_SET_NORMALIZATION",
        "technical_field": "commercial_normalization",
        "authority": authority,
        "accepted_status": "APPROVED_BY_IGOR",
        "accepted_value": [
            {
                "section_id": section,
                "commercial_item_name": payload["commercial_item_name"],
                "future_price_lookup_name": payload["future_price_lookup_name"],
                "commercial_quantity_per_cabinet": 1,
                "supply_form": payload["supply_form"],
                "separate_TST05_pricing": False,
                "separate_TST05_procurement": False,
                "application_status": "NOT_EXECUTED",
            }
            for section in payload["sections"]
        ],
        "approval_boundary": {
            "technical_source_rows": "PRESERVED_SEPARATELY",
            "technical_model_equivalence": "NOT_ASSERTED",
            "commercial_item_per_cabinet": "ONE_COMPLETE_SET",
            "separate_TST05_pricing_and_procurement": "PROHIBITED",
            "application_status": "NOT_EXECUTED",
        },
        "source_position_provenance": {
            "frozen_audit_bridge": [
                {
                    "section": section,
                    "rule_id": payload["rule_id"],
                    "commercial_item_name": payload["bridge_commercial_item_name"],
                    "future_price_lookup_name": payload["future_price_lookup_name"],
                    "commercial_quantity_per_cabinet": 1,
                    "bundle_members": copy.deepcopy(payload["bundle_members"]),
                    "status": payload["bridge_status"],
                    "application_status": "NOT_EXECUTED",
                    "anti_double_counting": True,
                    "technical_approval_created": False,
                    "pricing_executed": False,
                    "confirmed_composition_created": False,
                }
                for section in payload["sections"]
            ],
            "igor_semantic_override": (
                "commercial_item_name is the complete set with sensor; "
                "TST05 is not a separate commercial or procurement row"
            ),
        },
    }


def authority_batch(batch_id: str) -> dict[str, Any]:
    schema, compatible, prior, codes, authority = AUTHORITY_DATA[batch_id]
    result: dict[str, Any] = {
        "schema_version": schema,
        "case_id": f"CASE-AUTHORITY-{batch_id}-SYNTHETIC",
        "project_id": PROJECT_ID,
        "artifact_status": "FROZEN_HUMAN_APPROVAL_DECISIONS",
        "batch_id": batch_id,
        "compatible_with": compatible,
        "technical_field_decisions": [
            (
                h19_3_decision(authority)
                if batch_id == "019" and code == "H19-3"
                else {
                    "decision_id": f"HDA-{batch_id}-{code}",
                    "decision_code": code,
                    "authority": authority,
                    "accepted_status": "APPROVED_BY_IGOR",
                }
            )
            for code in codes
        ],
        "safety_flags": {
            "calculator_run": False,
            "confirmed_composition_created": False,
            "pricing_executed": False,
            "procurement_started": False,
            "production_started": False,
        },
    }
    if prior is not None:
        result["prior_batch_id"] = prior
    return result


def quantity_fingerprints(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "record_id": record["record_id"],
            "component_evidence_id": record["component_evidence_id"],
            "evidence_position_id": record["evidence_position_id"],
            "section": record["section"],
            "field": record["field"],
            "applicability_classification": record["applicability_classification"],
            "remediation_route": record["remediation_route"],
        }
        for record in records
        if record["applicability_classification"]
        in {"REQUIRED_VALUE_MISSING", "REQUIRED_VALUE_CONFLICTED"}
    ]


@dataclass
class Fixture:
    root: Path
    manifest_path: Path
    manifest: dict[str, Any]
    sources: dict[str, tuple[Path, dict[str, Any]]]

    def write(self) -> None:
        for role_key, (path, value) in self.sources.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            content = json_bytes(value)
            path.write_bytes(content)
            descriptor = next(
                item
                for item in self.manifest["source_artifacts"]
                if item["input_path"] == str(path.resolve())
            )
            descriptor["sha256"] = sha256(content)
            if role_key == "batch-019":
                self.manifest["supply_boundary"]["expected_rt007s_authority_proof"][
                    "artifact_sha256"
                ] = descriptor["sha256"]
            assert role_key
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_bytes(json_bytes(self.manifest))


def descriptor(role: str, path: Path, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": role,
        "input_path": str(path.resolve()),
        "schema_version": data["schema_version"],
        "sha256": "",
        "case_id": data["case_id"],
        "project_id": data["project_id"],
        "artifact_status": data["artifact_status"],
    }


def make_fixture(tmp_path: Path) -> Fixture:
    records = applicability_records()
    cumulative = cumulative_review(records)
    applicability = field_applicability(records)
    sources: dict[str, tuple[Path, dict[str, Any]]] = {
        "cumulative": (
            tmp_path / "case-cumulative" / "cumulative.json",
            cumulative,
        ),
        **{
            f"batch-{batch_id}": (
                tmp_path / f"case-authority-{batch_id}" / f"batch-{batch_id}.json",
                authority_batch(batch_id),
            )
            for batch_id in AUTHORITY_DATA
        },
        "applicability": (
            tmp_path / "case-applicability" / "applicability.json",
            applicability,
        ),
    }
    source_descriptors = [
        descriptor("cumulative_review", *sources["cumulative"]),
        *[
            descriptor("authority_batch", *sources[f"batch-{batch_id}"])
            for batch_id in AUTHORITY_DATA
        ],
        descriptor("field_applicability", *sources["applicability"]),
    ]
    install_fingerprint = copy.deepcopy(
        applicability["additional_blockers_outside_82"][0]
    )
    manifest = {
        "schema_version": "component_replay_intake.v0.1",
        "case_id": "CASE-REPLAY-OPERATION-SYNTHETIC",
        "project_id": PROJECT_ID,
        "source_artifacts": source_descriptors,
        "authority_lineage": {
            "ordered_schemas": [value[0] for value in AUTHORITY_DATA.values()],
            "ordered_batch_ids": list(AUTHORITY_DATA),
        },
        "policy_binding": {
            "source_commit": git_head(),
            "owner_path": "scripts/project_spec_extraction.py",
            "owner_sha256": sha256(POLICY_OWNER.read_bytes()),
            "function_names": [
                "classify_component_field_applicability",
                "normalize_explicit_component_model_type",
            ],
            "required_types": ["ComponentCandidate", "Provenance"],
            "expected_classification_counts": classification_counts(),
        },
        "expected_counts": {
            "canonical_position_count": 6,
            "component_bearing_position_count": 1,
            "component_field_evidence_entry_count": 82,
            "component_absence_evidence_entry_count": 1,
            "identified_component_evidence_record_count": 82,
            "unique_component_evidence_id_count": 82,
            "position_quantity_total": 10,
        },
        "expected_quantity_invariants": [
            {
                "type": "POSITION_QUANTITY_TOTAL_EQUALS",
                "partition": None,
                "expected_total": 10,
            },
            {
                "type": "PARTITION_QUANTITY_EQUALS",
                "partition": "9",
                "expected_total": 5,
            },
            {
                "type": "PARTITION_QUANTITY_EQUALS",
                "partition": "12",
                "expected_total": 1,
            },
            *[
                {
                    "type": "PARTITION_QUANTITY_EQUALS",
                    "partition": section,
                    "expected_total": 1,
                }
                for section in ("10", "11", "13", "15")
            ],
        ],
        "required_invariants": [
            "COUNTS_MATCH_FROZEN_STATE",
            "POSITION_BOUNDARIES_PRESERVED",
            "BLOCKERS_PRESERVED",
            "SUPPLY_BOUNDARY_PRESERVED",
            "COMPLETE_SET_EXCLUSIVE",
            "APPLICABILITY_CONFORMS_TO_OWNER",
        ],
        "supply_boundary": {
            "expected_outside_cabinet_exclusions": 16,
            "expected_new_evidence_ids_for_exclusions": 0,
            "expected_external_rows_included": 0,
            "expected_standalone_tst05": {
                "commercial": 0,
                "pricing": 0,
                "procurement": 0,
            },
            "expected_standalone_rt007s": {
                "commercial": 0,
                "pricing": 0,
                "procurement": 0,
            },
            "expected_rt007s_authority_proof": {
                "source_schema": "human_decisions_batch.v0.19",
                "batch_id": "019",
                "artifact_sha256": "",
                "decision_id": "HDA-019-H19-3",
                "decision_code": "H19-3",
                "decision_type": "COMMERCIAL_THERMOSTAT_COMPLETE_SET_NORMALIZATION",
                "technical_field": "commercial_normalization",
                "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
                "accepted_status": "APPROVED_BY_IGOR",
                "rule_payload": rt007s_rule_payload(),
            },
        },
        "complete_set_rules": {
            "expected_rt_820_complete_sets": 4,
            "protected_component_records": [
                {
                    "component_evidence_id": evidence_id,
                    "evidence_position_id": "TFE-001",
                    "raw_quantity": 5,
                }
                for evidence_id in PROTECTED_IDS
            ],
            "forbid_five_to_one": True,
        },
        "blocker_requirements": {
            "expected_quantity_blocker_count": 29,
            "expected_install_type_blocker_count": 1,
            "quantity_blocker_fingerprints": quantity_fingerprints(records),
            "install_type_blocker_fingerprints": [install_fingerprint],
            "require_exact_preservation": True,
        },
        "safety": {
            "confirmed_composition_authorized": False,
            "pricing_authorized": False,
            "commercial_authorized": False,
            "production_authorized": False,
        },
        "output_contract": {
            "schema_version": "component_replay_readiness_bundle.v0.1",
            "artifact_status": "PRELIMINARY_REPLAY_ONLY_NOT_CONFIRMED",
            "authorization": False,
        },
    }
    fixture = Fixture(
        tmp_path,
        tmp_path / "replay-operation" / "intake.json",
        manifest,
        sources,
    )
    fixture.write()
    return fixture


def source(fixture: Fixture, key: str) -> dict[str, Any]:
    return fixture.sources[key][1]


def componentless_field(fixture: Fixture, field: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        source(fixture, "cumulative")["positions"][1]["technical_fields"][field],
    )


def componentless_placeholder(fixture: Fixture, field: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        componentless_field(fixture, field)["evidence_values"][0],
    )


def run(
    fixture: Fixture,
    output: Path,
    *,
    validate_only: bool = False,
    before_drift_check: Callable[[], None] | None = None,
) -> Any:
    fixture.write()
    return builder.run_builder(
        intake_manifest=fixture.manifest_path,
        output_dir=output,
        validate_only=validate_only,
        before_drift_check=before_drift_check,
    )


def test_direct_happy_path_projects_real_shapes(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    output = tmp_path / "output"
    result = run(fixture, output)
    assert result.status == "PASS", result.red_flags
    bundle_path = output / builder.BUNDLE_NAME
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert bundle["artifact_status"] == "PRELIMINARY_REPLAY_ONLY_NOT_CONFIRMED"
    assert bundle["counts"] == fixture.manifest["expected_counts"]
    assert len(bundle["field_applicability_records"]) == 82
    assert len(bundle["blockers"]) == 30
    assert bundle["supply_boundary"]["outside_cabinet_exclusions"] == 16
    assert bundle["complete_set_controls"]["rt_820_complete_sets"] == 4
    proof = bundle["supply_boundary"]["rt007s_authority_proof"]
    assert proof["decision_id"] == "HDA-019-H19-3"
    assert proof["rule_payload"]["sections"] == ["9", "11", "13", "15"]
    assert proof["rule_payload"]["raw_source_evidence_preserved"] is True
    serialized = json.dumps(bundle, ensure_ascii=False)
    assert "input_path" not in serialized
    assert str(tmp_path) not in serialized
    validation = validator.validate_component_replay_readiness_bundle(
        fixture.manifest_path,
        bundle_path,
    )
    assert validation.status == "PASS"


def test_triple_not_found_preserves_component_count_semantics(
    tmp_path: Path,
) -> None:
    fixture = make_fixture(tmp_path)
    output = tmp_path / "output"
    result = run(fixture, output)
    assert result.status == "PASS", result.red_flags
    bundle = json.loads((output / builder.BUNDLE_NAME).read_text(encoding="utf-8"))
    assert bundle["counts"] == fixture.manifest["expected_counts"]
    assert bundle["counts"]["component_absence_evidence_entry_count"] == 1
    assert bundle["counts"]["component_field_evidence_entry_count"] == 82
    assert bundle["counts"]["identified_component_evidence_record_count"] == 82
    assert bundle["counts"]["unique_component_evidence_id_count"] == 82
    componentless = next(
        item for item in bundle["positions"] if item["position_id"] == "TFE-002"
    )
    assert componentless["component_field_evidence"] == []
    assert len(componentless["component_absence_evidence"]) == 1
    assert len(bundle["component_absence_evidence"]) == 1


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda fixture: componentless_placeholder(
                fixture,
                "apparatus",
            ).update(value="unexpected"),
            "field absence value must be null",
        ),
        (
            lambda fixture: componentless_placeholder(
                fixture,
                "ratings",
            ).update(status="PROJECT_EVIDENCE_UNAPPROVED"),
            "field absence status must be NOT_FOUND",
        ),
        (
            lambda fixture: componentless_field(
                fixture,
                "apparatus",
            ).update(resolution_status="PROJECT_EVIDENCE_UNAPPROVED"),
            "parent resolution_status must be NOT_FOUND",
        ),
        (
            lambda fixture: componentless_placeholder(
                fixture,
                "components",
            ).update(component_evidence_id=None),
            "component_evidence_id must be a non-empty string",
        ),
        (
            lambda fixture: componentless_placeholder(
                fixture,
                "apparatus",
            ).update(component_evidence_id=""),
            "component_evidence_id must be a non-empty string",
        ),
        (
            lambda fixture: componentless_placeholder(
                fixture,
                "ratings",
            ).update(reason=""),
            "absence.reason must be a non-empty string",
        ),
        (
            lambda fixture: componentless_placeholder(
                fixture,
                "components",
            ).update(provenance="malformed"),
            "absence.provenance must be an object",
        ),
    ],
)
def test_invalid_not_found_placeholder_fails_without_output(
    tmp_path: Path,
    mutation: Callable[[Fixture], None],
    expected: str,
) -> None:
    fixture = make_fixture(tmp_path)
    mutation(fixture)
    output = tmp_path / "output"
    result = run(fixture, output)
    assert result.status == "FAIL"
    assert expected in " ".join(result.red_flags)
    assert not output.exists()


@pytest.mark.parametrize(
    ("batch_key", "mutation", "expected"),
    [
        (
            "batch-018",
            lambda batch: batch.update(compatible_with="human_decisions_batch.v0.16"),
            "compatible_with mismatch",
        ),
        (
            "batch-019",
            lambda batch: batch.update(prior_batch_id="017"),
            "prior_batch_id mismatch",
        ),
        (
            "batch-020",
            lambda batch: batch["technical_field_decisions"][0].update(
                decision_code="CE1"
            ),
            "unknown decision_code",
        ),
        (
            "batch-017",
            lambda batch: batch.update(prior_batch_id="016"),
            "must not contain prior_batch_id",
        ),
    ],
)
def test_authority_chain_and_schema_specific_codes_fail_closed(
    tmp_path: Path,
    batch_key: str,
    mutation: Callable[[dict[str, Any]], None],
    expected: str,
) -> None:
    fixture = make_fixture(tmp_path)
    mutation(source(fixture, batch_key))
    output = tmp_path / "output"
    result = run(fixture, output)
    assert result.status == "FAIL"
    assert expected in " ".join(result.red_flags)
    assert not output.exists()


def test_different_case_ids_same_project_are_allowed(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    case_ids = {
        descriptor_value["case_id"]
        for descriptor_value in fixture.manifest["source_artifacts"]
    }
    assert len(case_ids) == 6
    result = run(fixture, tmp_path / "output", validate_only=True)
    assert result.status == "PASS", result.red_flags


def test_mixed_project_is_rejected(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    source(fixture, "batch-019")["project_id"] = "OTHER-PROJECT"
    result = run(fixture, tmp_path / "output")
    assert result.status == "FAIL"
    assert "project_id mismatch" in " ".join(result.red_flags)
    assert not (tmp_path / "output").exists()


def test_absolute_inputs_and_output_inside_any_input_case(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    assert all(
        Path(item["input_path"]).is_absolute()
        for item in fixture.manifest["source_artifacts"]
    )
    result = run(
        fixture,
        fixture.sources["batch-018"][0].parent / "output",
    )
    assert result.status == "FAIL"
    assert "inside an input frozen case" in " ".join(result.red_flags)


def test_post_commit_policy_binding_does_not_require_current_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = make_fixture(tmp_path)
    synthetic_prior_commit = "1" * 40
    fixture.manifest["policy_binding"]["source_commit"] = synthetic_prior_commit
    fixture.write()
    owner_bytes = POLICY_OWNER.read_bytes()
    monkeypatch.setattr(
        validator,
        "_git_blob_bytes",
        lambda commit, owner_path: owner_bytes,
    )
    context = validator.load_intake_context(fixture.manifest_path)
    assert context.manifest["policy_binding"]["source_commit"] == synthetic_prior_commit
    assert "_git_head" not in VALIDATOR_PATH.read_text(encoding="utf-8")


def test_missing_policy_commit_and_sha_mismatch_fail_closed(tmp_path: Path) -> None:
    missing = make_fixture(tmp_path / "missing")
    missing.manifest["policy_binding"]["source_commit"] = "f" * 40
    result = run(missing, tmp_path / "missing-output")
    assert result.status == "FAIL"
    assert "source commit does not exist" in " ".join(result.red_flags)

    mismatch = make_fixture(tmp_path / "mismatch")
    mismatch.manifest["policy_binding"]["owner_sha256"] = "0" * 64
    result = run(mismatch, tmp_path / "mismatch-output")
    assert result.status == "FAIL"
    assert "blob SHA-256 mismatch" in " ".join(result.red_flags)


def test_missing_policy_blob_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = make_fixture(tmp_path)
    fixture.write()

    def missing_blob(commit: str, owner_path: str) -> bytes:
        raise validator.ReplayValidationError(
            "policy owner blob is missing in source commit"
        )

    monkeypatch.setattr(validator, "_git_blob_bytes", missing_blob)
    with pytest.raises(
        validator.ReplayValidationError,
        match="policy owner blob is missing",
    ):
        validator.load_intake_context(fixture.manifest_path)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda fixture: source(fixture, "cumulative").update(controls={}),
            "controls missing",
        ),
        (
            lambda fixture: source(fixture, "applicability").update(records=[]),
            "records are empty",
        ),
        (
            lambda fixture: source(fixture, "applicability").update(
                additional_blockers_outside_82=[]
            ),
            "blocker count mismatch",
        ),
        (
            lambda fixture: fixture.manifest["complete_set_rules"].update(
                protected_component_records=[]
            ),
            "complete-set controls unexpectedly empty",
        ),
    ],
)
def test_empty_controls_or_records_fail_with_nonzero_expectations(
    tmp_path: Path,
    mutation: Callable[[Fixture], None],
    expected: str,
) -> None:
    fixture = make_fixture(tmp_path)
    mutation(fixture)
    result = run(fixture, tmp_path / "output")
    assert result.status == "FAIL"
    assert expected in " ".join(result.red_flags)


@pytest.mark.parametrize(
    ("control", "value", "expected"),
    [
        ("external_shu_t1_source_rows", 15, "outside_cabinet_exclusions"),
        ("new_evidence_ids_for_external_rows", 1, "new_evidence_ids"),
        ("rt_820_complete_set_records", 3, "RT-820"),
    ],
)
def test_exact_16_0_4_controls(
    tmp_path: Path,
    control: str,
    value: int,
    expected: str,
) -> None:
    fixture = make_fixture(tmp_path)
    source(fixture, "cumulative")["controls"][control] = value
    result = run(fixture, tmp_path / "output")
    assert result.status == "FAIL"
    assert expected in " ".join(result.red_flags)


def test_protected_components_cannot_change_five_to_one(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    record = next(
        item
        for item in source(fixture, "applicability")["records"]
        if item["component_evidence_id"] == "COMP-034"
    )
    record["raw_quantity"] = 1
    result = run(fixture, tmp_path / "output")
    assert result.status == "FAIL"
    assert "5-to-1" in " ".join(result.red_flags)


def test_exact_29_plus_1_blocker_fingerprints(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    source(fixture, "applicability")["records"][-1][
        "remediation_route"
    ] = "CHANGED_ROUTE"
    result = run(fixture, tmp_path / "output")
    assert result.status == "FAIL"
    assert "fingerprint mismatch" in " ".join(result.red_flags)


def test_exact_applicability_29_16_8(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    source(fixture, "applicability")["classification_counts"][
        "FIELD_SEMANTICS_MISMATCH"
    ] = 15
    result = run(fixture, tmp_path / "output")
    assert result.status == "FAIL"
    assert "classification counts mismatch" in " ".join(result.red_flags)


def test_standalone_tst05_is_rejected_independently(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    source(fixture, "cumulative")["controls"]["separate_tst05_commercial_rows"] = 1
    result = run(fixture, tmp_path / "output")
    assert result.status == "FAIL"
    assert "standalone_tst05" in " ".join(result.red_flags)


def test_external_zero_with_standalone_rt007s_is_rejected(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    controls = source(fixture, "cumulative")["controls"]
    assert (
        controls["external_rows_included_in_composition_price_procurement_production"]
        == 0
    )
    decision = next(
        item
        for item in source(fixture, "batch-019")["technical_field_decisions"]
        if item["decision_code"] == "H19-3"
    )
    decision["accepted_value"][0]["commercial_item_name"] = "РТ 007S"
    output = tmp_path / "output"
    result = run(fixture, output)
    assert result.status == "FAIL"
    assert "standalone RT007S downstream representation" in " ".join(result.red_flags)
    assert not output.exists()


def test_missing_rt007s_authority_proof_is_rejected(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    batch = source(fixture, "batch-019")
    batch["technical_field_decisions"] = [
        item
        for item in batch["technical_field_decisions"]
        if item["decision_code"] != "H19-3"
    ]
    output = tmp_path / "output"
    result = run(fixture, output)
    assert result.status == "FAIL"
    assert "RT007S authority decision is missing" in " ".join(result.red_flags)
    assert not output.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decision_id", "HDA-019-WRONG"),
        ("decision_code", "H19-4"),
        ("authority", "WRONG_AUTHORITY"),
        ("accepted_status", "NOT_APPROVED"),
        ("decision_type", "WRONG_RULE_PAYLOAD"),
    ],
)
def test_rt007s_decision_fingerprint_changes_are_rejected(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    fixture = make_fixture(tmp_path)
    decision = next(
        item
        for item in source(fixture, "batch-019")["technical_field_decisions"]
        if item["decision_code"] == "H19-3"
    )
    decision[field] = value
    output = tmp_path / "output"
    result = run(fixture, output)
    assert result.status == "FAIL"
    assert not output.exists()


def test_rt007s_rule_payload_change_is_rejected(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    decision = next(
        item
        for item in source(fixture, "batch-019")["technical_field_decisions"]
        if item["decision_code"] == "H19-3"
    )
    decision["source_position_provenance"]["frozen_audit_bridge"][0][
        "anti_double_counting"
    ] = False
    output = tmp_path / "output"
    result = run(fixture, output)
    assert result.status == "FAIL"
    assert "rule payload mismatch" in " ".join(result.red_flags)
    assert not output.exists()


def test_rt007s_raw_evidence_without_commercial_row_passes(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    result = run(fixture, tmp_path / "output", validate_only=True)
    assert result.status == "PASS", result.red_flags


def test_rt007s_rule_cannot_transfer_to_shu_t2(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    source(fixture, "cumulative")["positions"][0]["canonical_identity"][
        "canonical_designation"
    ] = "ШУ-Т2"
    output = tmp_path / "output"
    result = run(fixture, output)
    assert result.status == "FAIL"
    assert "transferred to ШУ-Т2" in " ".join(result.red_flags)
    assert not output.exists()


@pytest.mark.parametrize("kind", ["duplicate", "new", "missing"])
def test_duplicate_new_or_missing_evidence_id(
    tmp_path: Path,
    kind: str,
) -> None:
    fixture = make_fixture(tmp_path)
    components = source(fixture, "cumulative")["positions"][0]["technical_fields"][
        "components"
    ]["evidence_values"]
    if kind == "duplicate":
        components[1]["component_evidence_id"] = components[0]["component_evidence_id"]
    elif kind == "new":
        source(fixture, "applicability")["records"][0][
            "component_evidence_id"
        ] = "COMP-NEW"
    else:
        components.pop()
    result = run(fixture, tmp_path / "output")
    assert result.status == "FAIL"
    assert "evidence ID" in " ".join(result.red_flags)


@pytest.mark.parametrize("field", ["value_applied", "approval_created"])
def test_normalization_applied_or_approved_is_rejected(
    tmp_path: Path,
    field: str,
) -> None:
    fixture = make_fixture(tmp_path)
    record = next(
        item
        for item in source(fixture, "applicability")["records"]
        if item["applicability_classification"] == "EXPLICIT_RAW_VALUE_NOT_NORMALIZED"
    )
    record[field] = True
    result = run(fixture, tmp_path / "output")
    assert result.status == "FAIL"
    assert "applied or approved" in " ".join(result.red_flags)


def test_validate_only_drift_and_no_output_on_failure(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    validate_only = tmp_path / "validate-only"
    result = run(fixture, validate_only, validate_only=True)
    assert result.status == "PASS", result.red_flags
    assert not validate_only.exists()

    drift_output = tmp_path / "drift-output"

    def drift() -> None:
        fixture.manifest_path.write_bytes(fixture.manifest_path.read_bytes() + b" ")

    result = run(
        fixture,
        drift_output,
        before_drift_check=drift,
    )
    assert result.status == "FAIL"
    assert "input drift" in " ".join(result.red_flags)
    assert not drift_output.exists()

    failed = make_fixture(tmp_path / "failed")
    source(failed, "cumulative")["controls"]["external_shu_t1_source_rows"] = 99
    failed_output = tmp_path / "failed-output"
    result = run(failed, failed_output)
    assert result.status == "FAIL"
    assert not failed_output.exists()


def test_duplicate_paths_and_descriptor_identity_fail_closed(tmp_path: Path) -> None:
    duplicate = make_fixture(tmp_path / "duplicate")
    duplicate.write()
    duplicate.manifest["source_artifacts"][1] = copy.deepcopy(
        duplicate.manifest["source_artifacts"][0]
    )
    duplicate.manifest_path.write_bytes(json_bytes(duplicate.manifest))
    result = builder.run_builder(
        intake_manifest=duplicate.manifest_path,
        output_dir=tmp_path / "duplicate-output",
    )
    assert result.status == "FAIL"
    assert "duplicate direct input path" in " ".join(result.red_flags)

    identity = make_fixture(tmp_path / "identity")
    identity.write()
    identity.manifest["source_artifacts"][0]["case_id"] = "WRONG-CASE"
    identity.manifest_path.write_bytes(json_bytes(identity.manifest))
    result = builder.run_builder(
        intake_manifest=identity.manifest_path,
        output_dir=tmp_path / "identity-output",
    )
    assert result.status == "FAIL"
    assert "case_id mismatch" in " ".join(result.red_flags)


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    fixture.write()
    path, data = fixture.sources["applicability"]
    raw = json_bytes(data).decode("utf-8")
    marker = '  "schema_version": "unresolved_field_applicability_audit.v0.1"'
    assert marker in raw
    raw = raw.replace(
        marker,
        f"{marker},\n{marker}",
        1,
    )
    content = raw.encode()
    path.write_bytes(content)
    descriptor_value = next(
        item
        for item in fixture.manifest["source_artifacts"]
        if item["role"] == "field_applicability"
    )
    descriptor_value["sha256"] = sha256(content)
    fixture.manifest_path.write_bytes(json_bytes(fixture.manifest))
    result = builder.run_builder(
        intake_manifest=fixture.manifest_path,
        output_dir=tmp_path / "output",
    )
    assert result.status == "FAIL"
    assert "duplicate JSON key" in " ".join(result.red_flags)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda fixture: fixture.manifest["safety"].update(pricing_authorized=True),
        lambda fixture: source(fixture, "cumulative")["controls"].update(
            pricing_executed=True
        ),
    ],
)
def test_authorization_or_downstream_flag_is_rejected(
    tmp_path: Path,
    mutation: Callable[[Fixture], None],
) -> None:
    fixture = make_fixture(tmp_path)
    mutation(fixture)
    result = run(fixture, tmp_path / "output")
    assert result.status == "FAIL"
    assert not (tmp_path / "output").exists()


def test_direct_contract_has_no_normalized_intermediate_schemas() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (BUILDER_PATH, VALIDATOR_PATH)
    )
    assert "component_cumulative_review.v0.1" not in combined
    assert "component_authority_batch.v0.1" not in combined
    assert "--intake-manifest" in combined
    assert "--output-dir" in combined
    assert "--validate-only" in combined
    forbidden_calls = (
        "component_to_draft(",
        "extract_pdf(",
        "extract_workbook(",
    )
    for token in forbidden_calls:
        assert token not in combined
