import ast
import copy
import importlib.util
import json
import py_compile
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "publish_shu_t2_rt820_scope_human_decision.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("shu_t2_rt820_writer_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


writer = cast(Any, load_module())


def write_json(path: Path, value: dict[str, Any]) -> str:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return cast(str, writer.sha256_bytes(path.read_bytes()))


def decision_identity(role: str) -> dict[str, Any]:
    schema, status, decision_id = writer.INPUT_IDENTITIES[role]
    return {
        "schema_version": schema,
        "project_id": writer.PROJECT_ID,
        "decision_id": decision_id,
        "status": status,
        "authority": writer.AUTHORITY,
        "application_status": writer.APPLICATION_STATUS,
        "scope_expansion": False,
        "immutable": True,
        "no_overwrite": True,
    }


def rt820_decision() -> dict[str, Any]:
    value = decision_identity("rt820_code_install_decision")
    value["approved_code_install_contract"] = {
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
    }
    value["pricing_work_semantics"] = {
        "workbook_label_source": "КРН!A19",
        "workbook_label": "Терморегулятор RT-820",
        "material_source": "КРН!B19",
        "material_price_kzt_per_complete_set": 15000,
        "work_source": "КРН!C19",
        "work_price_kzt_per_complete_set": 900,
        "work_price_semantics": "EXACT_COMPONENT_WORK_PRICE",
        "generic_modular_2p_work_price_kzt": 432,
        "generic_modular_2p_work_price_prohibited": True,
        "similar_relay_price_fallback_prohibited": True,
        "family_fallback_prohibited": True,
        "fuzzy_fallback_prohibited": True,
        "price_does_not_create_technical_identity": True,
    }
    value["tst05_bundle_semantics"] = {
        "separate_component_row": False,
        "separate_material_charge": False,
        "separate_work_charge": False,
        "separate_pricing_row": False,
    }
    return value


def technical_row(
    row_id: str,
    group_id: str,
    product: str,
    code: str,
    install: str,
    evidence: str,
) -> dict[str, Any]:
    return {
        "row_id": row_id,
        "cabinet_group_id": group_id,
        "calculator_values": {
            "product_name": product,
            "cabinet_code": "CAB-KRN-12",
            "component_code": code,
            "component_qty": 1,
            "install_type": install,
        },
        "source_component_evidence_ids": [evidence],
    }


def technical_successor(paths: Any, decision_shas: dict[str, str]) -> dict[str, Any]:
    shu_t2_rows = [
        technical_row(
            row_id,
            "CABINET-GROUP-003",
            "ШУ-Т2",
            code,
            install,
            evidence,
        )
        for row_id, code, install, evidence in writer.SHU_T2_ROW_CONTRACTS
    ]
    shu_t1_rows = [
        technical_row(
            row_id,
            "CABINET-GROUP-015",
            "ШУ-Т1",
            code,
            "temperature_relay_din_2mod" if code == "EKF-RT-820" else "locked",
            f"SHU-T1-{row_id}",
        )
        for row_id, code in writer.SHU_T1_ROW_CODES.items()
    ]
    direct_bindings = []
    binding_values = (
        (
            "technical_composition_human_decision",
            "composition_decision",
            paths.composition_decision,
        ),
        (
            "cabinet_pricing_human_decision",
            "cabinet_pricing_decision",
            paths.cabinet_pricing_decision,
        ),
        (
            "rt820_code_install_human_decision",
            "rt820_code_install_decision",
            paths.rt820_code_install_decision,
        ),
    )
    for binding_role, identity_role, path in binding_values:
        schema, status, decision_id = writer.INPUT_IDENTITIES[identity_role]
        direct_bindings.append(
            {
                "role": binding_role,
                "path": str(path),
                "sha256": decision_shas[identity_role],
                "schema_version": schema,
                "status": status,
                "decision_id": decision_id,
                "authority": writer.AUTHORITY,
                "application_status": writer.APPLICATION_STATUS,
            }
        )
    return {
        "schema_version": writer.INPUT_IDENTITIES["technical_successor"][0],
        "source": {
            "project_id": writer.PROJECT_ID,
            "applied_bundle_sha256": writer.APPLIED_LINEAGE_SHA256,
            "applied_source_lineage": {
                "canonical_replay_sha256": writer.CANONICAL_LINEAGE_SHA256
            },
            "additive_completed_input_successor": {
                "project_id": writer.PROJECT_ID,
                "scope_expansion": False,
                "direct_human_decision_inputs": direct_bindings,
            },
        },
        "cabinet_groups": [
            {
                "cabinet_group_id": "CABINET-GROUP-003",
                "product_name": "ШУ-Т2",
                "cabinet_code": "CAB-KRN-12",
                "row_draft_ids": [item[0] for item in writer.SHU_T2_ROW_CONTRACTS],
            },
            {
                "cabinet_group_id": "CABINET-GROUP-015",
                "product_name": "ШУ-Т1",
                "cabinet_code": "CAB-KRN-12",
                "row_draft_ids": list(writer.SHU_T1_ROW_CODES),
            },
        ],
        "calculator_input_format": {"row_drafts": [*shu_t2_rows, *shu_t1_rows]},
        "safety": {
            "price_approved_by_igor": False,
            "production_authorized": False,
            "pricing_started": False,
            "downstream_started": False,
            "sending_authorized": False,
            "commercial_csv_authorized": False,
            "price_calculation_executed": False,
        },
        "completion": {"status": writer.INPUT_IDENTITIES["technical_successor"][1]},
    }


def profile_position(
    contract: tuple[str, str, str, str, str], index: int
) -> dict[str, Any]:
    section, technical_id, pricing_id, _relay, _sensor = contract
    row_pairs = (
        ["ROW-DRAFT-0020", "ROW-DRAFT-0024"],
        ["ROW-DRAFT-0021", "ROW-DRAFT-0025"],
        ["ROW-DRAFT-0022", "ROW-DRAFT-0026"],
        ["ROW-DRAFT-0023", "ROW-DRAFT-0027"],
    )
    return {
        "pricing_position_id": pricing_id,
        "section": section,
        "source_position_id": technical_id,
        "product_name": "ШУ-Т2",
        "cabinet_group_id": "CABINET-GROUP-003",
        "cabinet_code": "CAB-KRN-12",
        "physical_multiplicity": 1,
        "row_draft_ids": row_pairs[index],
        "composition_fingerprint_sha256": writer.CURRENT_SHU_T2_FINGERPRINT,
    }


def pricing_profile(paths: Any, shas: dict[str, str]) -> dict[str, Any]:
    schema, status, decision_id = writer.INPUT_IDENTITIES["pricing_profile"]
    authoritative_inputs = [
        {
            "role": "completed_technical_input_additive_successor",
            "path": str(paths.technical_successor),
            "sha256": shas["technical_successor"],
        },
        {
            "role": "technical_composition_human_decision",
            "path": str(paths.composition_decision),
            "sha256": shas["composition_decision"],
        },
        {
            "role": "cabinet_pricing_human_decision",
            "path": str(paths.cabinet_pricing_decision),
            "sha256": shas["cabinet_pricing_decision"],
        },
        {
            "role": "rt820_code_install_human_decision",
            "path": str(paths.rt820_code_install_decision),
            "sha256": shas["rt820_code_install_decision"],
        },
    ]
    shu_t1_positions = [
        {
            "pricing_position_id": pricing_id,
            "product_name": "ШУ-Т1",
            "cabinet_group_id": "CABINET-GROUP-015",
            "physical_multiplicity": 1,
            "composition_fingerprint_sha256": writer.CURRENT_SHU_T1_FINGERPRINT,
        }
        for pricing_id in writer.SHU_T1_PRICING_POSITIONS
    ]
    return {
        "schema_version": schema,
        "project_id": writer.PROJECT_ID,
        "decision_id": decision_id,
        "status": status,
        "authority": writer.AUTHORITY,
        "application_status": writer.APPLICATION_STATUS,
        "scope_expansion": False,
        "authoritative_inputs": authoritative_inputs,
        "current_completed_technical_scope": {
            "cabinet_groups": [
                {
                    "cabinet_group_id": "CABINET-GROUP-003",
                    "product_name": "ШУ-Т2",
                    "cabinet_code": "CAB-KRN-12",
                },
                {
                    "cabinet_group_id": "CABINET-GROUP-015",
                    "product_name": "ШУ-Т1",
                    "cabinet_code": "CAB-KRN-12",
                    "row_draft_ids": list(writer.SHU_T1_ROW_CODES),
                },
            ],
            "pricing_positions": [
                *[
                    profile_position(contract, index)
                    for index, contract in enumerate(writer.POSITION_SCOPE)
                ],
                *shu_t1_positions,
            ],
        },
        "safety_flags": {
            "pricing_profile_decision_recorded": True,
            "pricing_profile_applied": False,
            "current_scope_pricing_calculated": False,
            "reserved_formula_rules_applied": False,
            "calculator_run_authorized": False,
            "checked_calculator_run_authorized": False,
            "quote_generation_authorized": False,
            "price_approval_for_client": False,
            "lead_time_approved": False,
            "client_send_authorized": False,
            "procurement_authorized": False,
            "production_authorized": False,
            "scope_expansion": False,
        },
    }


def synthetic_inputs(tmp_path: Path) -> tuple[Any, Any]:
    paths = writer.InputPaths(
        tmp_path / "technical.json",
        tmp_path / "composition.json",
        tmp_path / "cabinet.json",
        tmp_path / "rt820.json",
        tmp_path / "profile.json",
    )
    decision_values = {
        "composition_decision": decision_identity("composition_decision"),
        "cabinet_pricing_decision": decision_identity("cabinet_pricing_decision"),
        "rt820_code_install_decision": rt820_decision(),
    }
    decision_shas = {
        role: write_json(getattr(paths, role), value)
        for role, value in decision_values.items()
    }
    technical = technical_successor(paths, decision_shas)
    technical_sha = write_json(paths.technical_successor, technical)
    all_shas = {**decision_shas, "technical_successor": technical_sha}
    profile = pricing_profile(paths, all_shas)
    profile_sha = write_json(paths.pricing_profile, profile)
    shas = writer.ExpectedShas(
        technical_sha,
        decision_shas["composition_decision"],
        decision_shas["cabinet_pricing_decision"],
        decision_shas["rt820_code_install_decision"],
        profile_sha,
    )
    return paths, shas


def rewrite_profile(paths: Any, shas: Any, profile: dict[str, Any]) -> Any:
    return replace(shas, pricing_profile=write_json(paths.pricing_profile, profile))


def rewrite_technical_and_profile(
    paths: Any, shas: Any, technical: dict[str, Any]
) -> Any:
    technical_sha = write_json(paths.technical_successor, technical)
    profile = json.loads(paths.pricing_profile.read_text(encoding="utf-8"))
    binding = next(
        item
        for item in profile["authoritative_inputs"]
        if item["role"] == "completed_technical_input_additive_successor"
    )
    binding["sha256"] = technical_sha
    profile_sha = write_json(paths.pricing_profile, profile)
    return replace(shas, technical_successor=technical_sha, pricing_profile=profile_sha)


def prepared_payload(tmp_path: Path) -> dict[str, Any]:
    paths, shas = synthetic_inputs(tmp_path)
    loaded = writer.load_and_validate_inputs(paths, shas)
    return cast(dict[str, Any], writer.build_payload(loaded, "2026-08-20T12:00:00Z"))


def cli_arguments(paths: Any, shas: Any, output: Path) -> list[str]:
    return [
        "--technical-successor",
        str(paths.technical_successor),
        "--technical-successor-sha256",
        shas.technical_successor,
        "--composition-decision",
        str(paths.composition_decision),
        "--composition-decision-sha256",
        shas.composition_decision,
        "--cabinet-pricing-decision",
        str(paths.cabinet_pricing_decision),
        "--cabinet-pricing-decision-sha256",
        shas.cabinet_pricing_decision,
        "--rt820-code-install-decision",
        str(paths.rt820_code_install_decision),
        "--rt820-code-install-decision-sha256",
        shas.rt820_code_install_decision,
        "--pricing-profile",
        str(paths.pricing_profile),
        "--pricing-profile-sha256",
        shas.pricing_profile,
        "--output",
        str(output),
        "--authorization",
        writer.PUBLICATION_AUTHORIZATION,
    ]


def test_writer_and_test_py_compile_with_portable_exception_syntax(
    tmp_path: Path,
) -> None:
    for source in (SCRIPT, Path(__file__)):
        py_compile.compile(
            str(source),
            cfile=str(tmp_path / f"{source.stem}.pyc"),
            doraise=True,
        )
    writer_source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(writer_source, filename=str(SCRIPT), feature_version=(3, 13))
    assert "except OSError as exc:" in writer_source
    assert "except FileNotFoundError, OSError:" not in writer_source


def test_exact_positive_publication_and_published_bytes(tmp_path: Path) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    output = tmp_path / "case-output" / writer.OUTPUT_FILENAME
    result = writer.publish_decision(paths, shas, output)

    assert output.is_file()
    assert result.sha256 == writer.sha256_bytes(output.read_bytes())
    assert result.size == len(output.read_bytes())
    assert result.encoded == output.read_bytes()
    published, raw = writer.load_json(output, "published test decision")
    writer.validate_payload(published)
    assert writer.serialize(published) == raw
    assert list(output.parent.iterdir()) == [output]


def test_authorization_token_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def forbidden_publish(*_args: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("publication must not be called")

    monkeypatch.setattr(writer, "publish_decision", forbidden_publish)
    arguments = [
        "--technical-successor",
        str(tmp_path / "technical.json"),
        "--technical-successor-sha256",
        "0" * 64,
        "--composition-decision",
        str(tmp_path / "composition.json"),
        "--composition-decision-sha256",
        "0" * 64,
        "--cabinet-pricing-decision",
        str(tmp_path / "cabinet.json"),
        "--cabinet-pricing-decision-sha256",
        "0" * 64,
        "--rt820-code-install-decision",
        str(tmp_path / "rt820.json"),
        "--rt820-code-install-decision-sha256",
        "0" * 64,
        "--pricing-profile",
        str(tmp_path / "profile.json"),
        "--pricing-profile-sha256",
        "0" * 64,
        "--output",
        str(tmp_path / "output" / writer.OUTPUT_FILENAME),
        "--authorization",
        "IGOR_CODE_ONLY_WRITER_DEVELOPMENT_AUTHORIZED",
    ]
    with pytest.raises(writer.ContractError, match="publication authorization"):
        writer.main(arguments)
    assert called is False


@pytest.mark.parametrize("role", list(writer.INPUT_IDENTITIES))
def test_wrong_sha_for_each_input_fails(role: str, tmp_path: Path) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    changed = replace(shas, **{role: "0" * 64})
    with pytest.raises(writer.ContractError, match="initial SHA mismatch"):
        writer.load_and_validate_inputs(paths, changed)


@pytest.mark.parametrize("bad_sha", ["A" * 64, "0" * 63, "z" * 64])
def test_sha_format_fails_closed(bad_sha: str, tmp_path: Path) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    with pytest.raises(writer.ContractError, match="lowercase hexadecimal"):
        writer.load_and_validate_inputs(
            paths, replace(shas, technical_successor=bad_sha)
        )


def test_duplicate_keys_fail_closed(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"project_id":"2024/086","project_id":"X"}', encoding="utf-8")
    with pytest.raises(writer.ContractError, match="duplicate JSON key"):
        writer.load_json(duplicate, "duplicate input")


@pytest.mark.parametrize("mode", ["missing", "extra", "wrong_technical"])
def test_missing_extra_or_wrong_position_fails(mode: str, tmp_path: Path) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    profile = json.loads(paths.pricing_profile.read_text(encoding="utf-8"))
    positions = profile["current_completed_technical_scope"]["pricing_positions"]
    if mode == "missing":
        positions.pop(0)
    elif mode == "extra":
        extra = copy.deepcopy(positions[0])
        extra["pricing_position_id"] = "PRICE-POSITION-999"
        positions.append(extra)
    else:
        positions[0]["source_position_id"] = "TFE-999"
    changed = rewrite_profile(paths, shas, profile)
    with pytest.raises(writer.ContractError, match="position|requires exactly one"):
        writer.load_and_validate_inputs(paths, changed)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda payload: payload["exact_scope"]["positions"][0].__setitem__(
                "sensor_evidence_id", "COMP-088"
            ),
            "const",
        ),
        (
            lambda payload: payload["bundle_semantics"].__setitem__(
                "separate_tst05_component_row", True
            ),
            "const",
        ),
        (
            lambda payload: payload["rt820_contract"].__setitem__(
                "component_qty_per_physical_cabinet", 2
            ),
            "const",
        ),
        (
            lambda payload: payload["rt820_contract"].__setitem__("work_kzt", 432),
            "const",
        ),
        (
            lambda payload: payload["rt820_contract"].__setitem__(
                "fuzzy_fallback_prohibited", False
            ),
            "const",
        ),
        (
            lambda payload: payload["supersession"].__setitem__(
                "all_other_supply_boundaries_unchanged", False
            ),
            "const",
        ),
    ],
)
def test_payload_semantic_drift_fails_closed(
    mutator: Any, message: str, tmp_path: Path
) -> None:
    payload = prepared_payload(tmp_path)
    mutator(payload)
    with pytest.raises(writer.ContractError, match=message):
        writer.validate_payload(payload)


def test_rt820_source_or_fallback_drift_in_input_fails(tmp_path: Path) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    rt820 = json.loads(paths.rt820_code_install_decision.read_text(encoding="utf-8"))
    rt820["pricing_work_semantics"]["work_price_kzt_per_complete_set"] = 432
    new_rt_sha = write_json(paths.rt820_code_install_decision, rt820)
    technical = json.loads(paths.technical_successor.read_text(encoding="utf-8"))
    binding = technical["source"]["additive_completed_input_successor"][
        "direct_human_decision_inputs"
    ][2]
    binding["sha256"] = new_rt_sha
    changed = rewrite_technical_and_profile(
        paths, replace(shas, rt820_code_install_decision=new_rt_sha), technical
    )
    profile = json.loads(paths.pricing_profile.read_text(encoding="utf-8"))
    profile_binding = next(
        item
        for item in profile["authoritative_inputs"]
        if item["role"] == "rt820_code_install_human_decision"
    )
    profile_binding["sha256"] = new_rt_sha
    changed = rewrite_profile(paths, changed, profile)
    with pytest.raises(writer.ContractError, match="pricing/work or fallback"):
        writer.load_and_validate_inputs(paths, changed)


def test_shu_t1_change_fails_even_with_updated_input_shas(tmp_path: Path) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    technical = json.loads(paths.technical_successor.read_text(encoding="utf-8"))
    shu_t1 = next(
        row
        for row in technical["calculator_input_format"]["row_drafts"]
        if row["row_id"] == "ROW-DRAFT-0110"
    )
    shu_t1["calculator_values"]["component_code"] = "EKF-RT-820-CHANGED"
    changed = rewrite_technical_and_profile(paths, shas, technical)
    with pytest.raises(writer.ContractError, match="SHU-T1 row changed"):
        writer.load_and_validate_inputs(paths, changed)


def test_wrong_input_path_role_fails_closed(tmp_path: Path) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    swapped = replace(
        paths,
        composition_decision=paths.cabinet_pricing_decision,
        cabinet_pricing_decision=paths.composition_decision,
    )
    swapped_shas = replace(
        shas,
        composition_decision=shas.cabinet_pricing_decision,
        cabinet_pricing_decision=shas.composition_decision,
    )
    with pytest.raises(writer.ContractError, match="schema mismatch"):
        writer.load_and_validate_inputs(swapped, swapped_shas)


def test_existing_output_directory_is_no_overwrite(tmp_path: Path) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    output = tmp_path / "case-output" / writer.OUTPUT_FILENAME
    output.parent.mkdir()
    with pytest.raises(writer.ContractError, match="output directory already exists"):
        writer.publish_decision(paths, shas, output)
    assert list(output.parent.iterdir()) == []


def test_toctou_mutation_cleans_staging_and_output_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    original = Path.read_bytes
    calls = 0

    def changed(path: Path) -> bytes:
        nonlocal calls
        raw = original(path)
        if path == paths.technical_successor:
            calls += 1
            if calls >= 2:
                return raw + b" "
        return raw

    monkeypatch.setattr(Path, "read_bytes", changed)
    output = tmp_path / "case-output" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="TOCTOU"):
        writer.publish_decision(paths, shas, output)
    assert not output.exists()
    assert not output.parent.exists()


def test_atomic_link_failure_cleans_staging_and_output_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_inputs(tmp_path)

    def fail_link(_source: Path, _target: Path) -> None:
        raise OSError("synthetic atomic failure")

    monkeypatch.setattr(writer.os, "link", fail_link)
    output = tmp_path / "case-output" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="atomic no-overwrite"):
        writer.publish_decision(paths, shas, output)
    assert not output.exists()
    assert not output.parent.exists()


def test_final_strict_reread_failure_rolls_back_link_staging_and_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    original = writer.load_json

    def fail_final_reread(path: Path, label: str) -> Any:
        if label == "published Human Decision":
            raise writer.ContractError("synthetic final strict reread failure")
        return original(path, label)

    monkeypatch.setattr(writer, "load_json", fail_final_reread)
    output = tmp_path / "case-output" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="final strict reread"):
        writer.publish_decision(paths, shas, output)
    assert not output.exists()
    assert not output.parent.exists()


def test_final_payload_validation_failure_rolls_back_everything(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    original_link = writer.os.link
    original_validate = writer.validate_payload
    link_created = False
    linked_staging: Path | None = None
    validations_before_link = 0

    def track_successful_link(source: Path, target: Path) -> None:
        nonlocal link_created, linked_staging
        original_link(source, target)
        linked_staging = source
        link_created = True

    def fail_final_validation(payload: Any) -> None:
        nonlocal validations_before_link
        if link_created:
            raise writer.ContractError("synthetic final payload validation failure")
        validations_before_link += 1
        original_validate(payload)

    monkeypatch.setattr(writer.os, "link", track_successful_link)
    monkeypatch.setattr(writer, "validate_payload", fail_final_validation)
    output = tmp_path / "case-output" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError) as raised:
        writer.main(cli_arguments(paths, shas, output))
    assert str(raised.value) == "synthetic final payload validation failure"
    assert link_created is True
    assert linked_staging is not None
    assert validations_before_link == 2
    assert not output.exists()
    assert not linked_staging.exists()
    assert not output.parent.exists()
    assert "PUBLISHED_IMMUTABLE_NO_OVERWRITE" not in capsys.readouterr().out


def test_foreign_final_replacement_is_preserved_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    original = writer.load_json
    foreign = b"foreign replacement"

    def replace_final(path: Path, label: str) -> Any:
        if label == "published Human Decision":
            path.unlink()
            path.write_bytes(foreign)
            raise writer.ContractError("synthetic post-link failure")
        return original(path, label)

    monkeypatch.setattr(writer, "load_json", replace_final)
    output = tmp_path / "case-output" / writer.OUTPUT_FILENAME
    with pytest.raises(
        writer.ContractError, match="foreign final replacement preserved"
    ):
        writer.publish_decision(paths, shas, output)
    assert output.read_bytes() == foreign
    assert list(output.parent.iterdir()) == [output]


def test_staging_cleanup_failure_cannot_return_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    original = Path.unlink

    def fail_staging_cleanup(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name.endswith(".staging"):
            raise OSError("synthetic staging cleanup failure")
        original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_staging_cleanup)
    output = tmp_path / "case-output" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="rollback cleanup blocked"):
        writer.publish_decision(paths, shas, output)
    assert not output.exists()
    assert output.parent.exists()
    assert any(path.name.endswith(".staging") for path in output.parent.iterdir())


def test_success_marker_is_not_printed_after_post_link_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, shas = synthetic_inputs(tmp_path)
    original = writer.load_json

    def fail_final_reread(path: Path, label: str) -> Any:
        if label == "published Human Decision":
            raise writer.ContractError("synthetic post-link failure")
        return original(path, label)

    monkeypatch.setattr(writer, "load_json", fail_final_reread)
    output = tmp_path / "case-output" / writer.OUTPUT_FILENAME
    with pytest.raises(writer.ContractError, match="post-link failure"):
        writer.main(cli_arguments(paths, shas, output))
    assert "PUBLISHED_IMMUTABLE_NO_OVERWRITE" not in capsys.readouterr().out
    assert not output.exists()
    assert not output.parent.exists()


@pytest.mark.parametrize("bad_value", [None, "false", 0])
def test_missing_null_string_or_numeric_safety_flags_fail(
    bad_value: Any, tmp_path: Path
) -> None:
    payload = prepared_payload(tmp_path)
    if bad_value is None:
        payload["safety"].pop("production_authorized")
    else:
        payload["safety"]["production_authorized"] = bad_value
    with pytest.raises(writer.ContractError, match="schema const"):
        writer.validate_payload(payload)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("project_id", "OTHER"),
        ("status", "APPLIED"),
        ("authority", "NOT_IGOR"),
        ("application_status", "APPLIED"),
    ],
)
def test_metadata_drift_fails_schema(
    field: str, bad_value: str, tmp_path: Path
) -> None:
    payload = prepared_payload(tmp_path)
    payload[field] = bad_value
    with pytest.raises(writer.ContractError, match="schema const"):
        writer.validate_payload(payload)


def test_schema_is_closed_and_matches_writer_contract() -> None:
    schema = writer.load_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == writer.SCHEMA_VERSION
