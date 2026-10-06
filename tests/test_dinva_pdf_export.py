from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import export_dinva_pdf as exporter  # type: ignore[import-not-found]
import pytest
from test_dinva_future_content import make_plan
from test_dinva_v0_5_print_successor import print_successor
from test_render_dinva_classic_quote_invoice import canonical_file


@pytest.mark.parametrize("entry", ["export", "_export"])
@pytest.mark.parametrize(
    "claim",
    [
        None,
        "old-token",
        "TEST_ONLY_DINVA_PDF_EXPORT",
        "cached-approved-artifact",
        "fabricated-log-proof",
        "production-runtime-contract",
        "signed-claim",
        "matching-input-output-shas",
    ],
)
def test_every_production_api_claim_is_closed(
    tmp_path: Path, monkeypatch: Any, entry: str, claim: Any
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    monkeypatch.setenv("DINVA_PDF_NATIVE_TEST", "1")
    monkeypatch.setattr(
        exporter.subprocess,
        "run",
        lambda *a, **k: pytest.fail("production execution forbidden"),
    )
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda *a, **k: pytest.fail("approval/runtime/log must not be read"),
    )
    with pytest.raises(ValueError, match="^NOT_IMPLEMENTED_PENDING_WU5$"):
        getattr(exporter, entry)(
            {"allow_test_profile": False},
            tmp_path / "real.pdf",
            claim,
            approval_path=tmp_path / "cached.fixture",
            approval_sha="a" * 64,
            inspector_python=Path("arbitrary.exe"),
            runtime_binding={"status": "approved"},
        )
    assert not (tmp_path / "real.pdf").exists()


@pytest.mark.parametrize(
    "args",
    [
        ["--export"],
        ["--export", "--approval", "old.fixture", "--approval-sha256", "a" * 64],
        [
            "--export",
            "--authorization",
            "recomputed-token",
            "--inspector-python",
            "arbitrary.exe",
        ],
        ["--export", "--workbook", "accepted.xlsx", "--output", "real.pdf"],
        ["--output", "real.pdf"],
        ["--approval=old.fixture"],
        ["--authorization=cached"],
        ["--inspector-python=arbitrary.exe"],
        ["--export=true"],
    ],
)
def test_production_cli_closes_before_inputs(
    args: list[str], monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(
        exporter,
        "preflight",
        lambda *a, **k: pytest.fail("must not preflight real export"),
    )
    monkeypatch.setattr(
        exporter.subprocess, "run", lambda *a, **k: pytest.fail("must not execute")
    )
    assert exporter.main(args) == 1
    assert capsys.readouterr().out.strip() == "HOLD: NOT_IMPLEMENTED_PENDING_WU5"


@pytest.mark.parametrize("entry", ["export", "_export"])
def test_cached_approval_bytes_cannot_enable_production(
    tmp_path: Path, entry: str
) -> None:
    artifact = tmp_path / "TEST-ONLY-cached-approval.fixture"
    artifact.write_text(
        json.dumps(
            {
                "test_only": True,
                "schema_version": "dinva_pdf_export_approval.v0.1",
                "approved_by": "Igor",
                "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
                "runtime_binding": {"status": "approved"},
            }
        ),
        encoding="utf-8",
    )
    before = artifact.read_bytes()
    with pytest.raises(ValueError, match="^NOT_IMPLEMENTED_PENDING_WU5$"):
        getattr(exporter, entry)(
            {}, tmp_path / "real.pdf", artifact, exporter.digest(artifact)
        )
    assert artifact.read_bytes() == before and not (tmp_path / "real.pdf").exists()


def test_unsafe_production_authority_is_retired() -> None:
    for name in (
        "HUMAN_ROLLOUT_ROOT",
        "APPROVAL_SCHEMA",
        "RUNTIME_SCHEMA",
        "verify_human_evidence",
        "validate_export_approval",
        "trusted_runtime",
        "runtime_tree_sha",
        "authorization",
    ):
        assert not hasattr(exporter, name)


@pytest.mark.parametrize(
    "trust",
    [
        {},
        {"test_only": False},
        {"test_only": None},
        {"binding": {"status": "approved"}},
    ],
)
def test_private_native_pipeline_rejects_production(
    monkeypatch: Any, tmp_path: Path, trust: Any
) -> None:
    monkeypatch.setattr(
        exporter.subprocess, "run", lambda *a, **k: pytest.fail("must not execute")
    )
    with pytest.raises(ValueError, match="^NOT_IMPLEMENTED_PENDING_WU5$"):
        exporter._export_test_only({}, tmp_path / "real.pdf", trust, timeout=5)


def test_read_only_cli_preflight_is_still_usable(monkeypatch: Any, capsys: Any) -> None:
    calls: list[Any] = []
    plan = {"read_only": True, "production_export_authorized": False}
    monkeypatch.setattr(exporter, "preflight", lambda *a, **k: plan)
    monkeypatch.setattr(exporter, "recheck", lambda value: calls.append(value))
    args = []
    for name in ("workbook", "profile", "document"):
        args += ["--" + name, "TEST-ONLY.fixture", "--" + name + "-sha256", "a" * 64]
    assert exporter.main(args) == 0 and calls == [plan]
    assert (
        "READ_ONLY=true; PRODUCTION_PDF=NOT_IMPLEMENTED_PENDING_WU5"
        in capsys.readouterr().out
    )


def runtime_fixture(tmp_path: Path, monkeypatch: Any) -> dict[str, Any]:
    runtime = tmp_path / "TEST-ONLY-python.fixture"
    runtime.write_bytes(b"TEST-ONLY NON-EXECUTABLE")
    inspector = tmp_path / "inspector.fixture"
    inspector.write_bytes(b"TEST-ONLY INSPECTOR")
    monkeypatch.setattr(exporter, "INSPECTOR", inspector)
    return {
        "test_only": True,
        "executable": runtime,
        "executable_sha256": exporter.digest(runtime),
        "inspector_sha256": exporter.digest(inspector),
    }


@pytest.mark.parametrize(
    "field", ["pdf_sha256", "expectations_sha256", "runtime_sha256", "inspector_sha256"]
)
def test_inspector_receipt_binds_synthetic_chain(
    tmp_path: Path, monkeypatch: Any, field: str
) -> None:
    from types import SimpleNamespace

    trust = runtime_fixture(tmp_path, monkeypatch)
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"TEST-ONLY")
    exp = tmp_path / "expectations.json"
    exp.write_bytes(b"{}")
    receipt = {
        "status": "PASS",
        "pdf_sha256": exporter.digest(pdf),
        "expectations_sha256": exporter.digest(exp),
        "runtime_sha256": trust["executable_sha256"],
        "inspector_sha256": trust["inspector_sha256"],
    }
    receipt[field] = "b" * 64
    monkeypatch.setattr(
        exporter.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(receipt)),
    )
    with pytest.raises(ValueError, match="receipt"):
        exporter.run_inspector(trust, pdf, expectations_path=exp, timeout=5)


@pytest.mark.parametrize("subject", ["runtime", "inspector"])
def test_synthetic_runtime_drift_holds(
    tmp_path: Path, monkeypatch: Any, subject: str
) -> None:
    trust = runtime_fixture(tmp_path, monkeypatch)
    (trust["executable"] if subject == "runtime" else exporter.INSPECTOR).write_bytes(
        b"DRIFT"
    )
    monkeypatch.setattr(
        exporter.subprocess,
        "run",
        lambda *a, **k: pytest.fail("unverified test runtime execution"),
    )
    with pytest.raises(ValueError, match="drift"):
        exporter.run_inspector(
            trust, tmp_path / "not-read.pdf", expectations_path=None, timeout=5
        )


def export_plan(tmp_path: Path, monkeypatch: Any) -> Any:
    plan, _ = make_plan(
        tmp_path, monkeypatch, native=True, case_id="CASE-TEST-ONLY-PDF"
    )
    if os.environ.get("DINVA_PDF_NATIVE_PROFILE"):
        profile = json.loads(Path(os.environ["DINVA_PDF_NATIVE_PROFILE"]).read_bytes())
    else:
        _, profile, _ = print_successor(tmp_path, monkeypatch)
    pp = tmp_path / "profile.json"
    ps = canonical_file(pp, profile)
    dp = tmp_path / "document.json"
    ds = canonical_file(dp, plan.document)
    xp = tmp_path / "synthetic'quote.xlsx"
    exporter.renderer.render(
        profile_path=pp,
        expected_profile_sha256=ps,
        document_path=dp,
        expected_document_sha256=ds,
        output=xp,
        allow_test_profile=True,
    )
    return exporter.preflight(
        xp,
        exporter.hashlib.sha256(xp.read_bytes()).hexdigest(),
        pp,
        ps,
        dp,
        ds,
        allow_test_profile=True,
    )


def test_pdf_preflight_exact_subject_and_closed_output(
    tmp_path: Path, monkeypatch: Any
) -> None:
    plan = export_plan(tmp_path, monkeypatch)
    assert plan["read_only"] is True and plan["production_export_authorized"] is False
    assert plan["production_pdf_status"] == "NOT_IMPLEMENTED_PENDING_WU5"
    before = {p.name for p in tmp_path.iterdir()}
    exporter.recheck(plan)
    out = tmp_path / "synthetic.pdf"
    if os.name == "nt":
        standalone = exporter.subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(exporter.NATIVE_ENGINE),
                "-Workbook",
                str(plan["workbook"]),
                "-Output",
                str(out),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            standalone.returncode != 0
            and not out.exists()
            and "DIRECT_NATIVE_PDF_EXPORT_CLOSED" in standalone.stderr
        )
    with pytest.raises(ValueError, match="^NOT_IMPLEMENTED_PENDING_WU5$"):
        exporter.export(plan, out, "wrong")
    assert not out.exists() and {p.name for p in tmp_path.iterdir()} == before
    assert not hasattr(exporter, "authorization")
    with pytest.raises(ValueError, match="^NOT_IMPLEMENTED_PENDING_WU5$"):
        exporter.export(plan, out, exporter.TEST_AUTHORIZATION)
    with pytest.raises(ValueError, match="^NOT_IMPLEMENTED_PENDING_WU5$"):
        exporter.export(plan, out, tmp_path / "approval.json", "a" * 64)
    with pytest.raises(ValueError, match="TEST-ONLY synthetic"):
        exporter.export_test_only(
            plan,
            tmp_path.parent / "escape.pdf",
            exporter.TEST_AUTHORIZATION,
            inspector_python=Path("not-executed.exe"),
        )
    plan["document"]["payer"] = "ALTERED"
    with pytest.raises(ValueError, match="plan mutated"):
        exporter.recheck(plan)


@pytest.mark.parametrize(
    "fault",
    [
        "real_plan",
        "real_case",
        "real_approval",
        "test_mode_off",
        "outside_subject",
        "outside_source",
        "outside_output",
    ],
)
def test_test_only_cannot_be_used_for_real_subjects(
    tmp_path: Path, monkeypatch: Any, fault: str
) -> None:
    plan = export_plan(tmp_path, monkeypatch)
    output = tmp_path / "synthetic.pdf"
    source = next(
        x
        for x in plan["document"]["approval_provenance"]["source_bindings"]
        if x["role"] == "AUTHORITATIVE_DOCUMENT_TEXT_SOURCE"
    )
    if fault == "real_plan":
        plan["allow_test_profile"] = False
    elif fault == "real_case":
        data = json.loads(Path(source["path"]).read_bytes())
        data["case_id"] = "CASE-LABORATORY-VRU-20260924-001"
        Path(source["path"]).write_text(json.dumps(data), encoding="utf-8")
        source["sha256"] = exporter.digest(Path(source["path"]))
    elif fault == "real_approval":
        plan["document"]["approval_provenance"]["approval_id"] = "REAL-APPROVAL"
    elif fault == "test_mode_off":
        monkeypatch.delenv("DINVA_RENDERER_TEST_MODE")
    elif fault == "outside_subject":
        plan["profile_path"] = tmp_path.parent / "outside.json"
    elif fault == "outside_source":
        folder = tmp_path / "different-owner-scope"
        folder.mkdir()
        path = folder / "source.json"
        path.write_bytes(Path(source["path"]).read_bytes())
        source["path"] = str(path)
    else:
        output = tmp_path.parent / "outside.pdf"
    monkeypatch.setattr(
        exporter.subprocess,
        "run",
        lambda *a, **k: pytest.fail("native execution forbidden"),
    )
    with pytest.raises(ValueError, match="NOT_IMPLEMENTED_PENDING_WU5"):
        exporter.export_test_only(
            plan,
            output,
            exporter.TEST_AUTHORIZATION,
            inspector_python=Path("not-executed.exe"),
        )
    assert not output.exists()


@pytest.mark.skipif(
    os.environ.get("DINVA_PDF_NATIVE_TEST") != "1",
    reason="explicit native synthetic Excel smoke",
)
def test_native_branded_pdf_and_independent_validation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    plan = export_plan(tmp_path, monkeypatch)
    runtime = Path(os.environ["DINVA_PDF_INSPECTOR_PYTHON"])
    out = tmp_path / "synthetic'branded.pdf"
    result = exporter.export_test_only(
        plan, out, exporter.TEST_AUTHORIZATION, inspector_python=runtime
    )
    assert (
        result["status"] == "PASS_TEST_ONLY"
        and result["client_send_authorized"] is False
    )
    assert (
        result["test_only"] is True and result["production_export_authorized"] is False
    )
    assert result["production_pdf_status"] == "NOT_IMPLEMENTED_PENDING_WU5"
    assert result["page_count"] > 0 and result["logo_matches"] > 0
    assert result["embedded_fonts"]
    from pypdf import PdfReader

    metadata = PdfReader(out).metadata
    assert metadata is not None
    assert metadata["/DINVATestOnly"] == "true"
    assert metadata["/DINVAProductionPDFStatus"] == "NOT_IMPLEMENTED_PENDING_WU5"
    assert "/DINVAPDFExportApprovalSHA256" not in metadata
    assert "/DINVAInspectorRuntimeContractSHA256" not in metadata
    assert plan["workbook"].read_bytes() == plan["snapshots"][plan["workbook"]]
    with pytest.raises(ValueError, match="collision"):
        exporter.export_test_only(
            plan, out, exporter.TEST_AUTHORIZATION, inspector_python=runtime
        )
    expected = exporter.expectations(plan, result["page_count"] + 1)
    ep = tmp_path / "expectations-bad.json"
    ep.write_text(json.dumps(expected), encoding="utf-8")
    audit = exporter.subprocess.run(
        [
            str(runtime),
            str(exporter.INSPECTOR),
            "--pdf",
            str(out),
            "--pdf-sha256",
            exporter.digest(out),
            "--expectations",
            str(ep),
            "--expectations-sha256",
            exporter.digest(ep),
        ],
        capture_output=True,
        text=True,
    )
    assert audit.returncode != 0 and "pages" in audit.stdout
    # The independent auditor must reject content/totals/signatures and source
    # identity omissions, rather than trusting a producer's PASS flag.
    for missing in ["MISSING_APPROVED_TOTAL", "MISSING_DIRECTOR_SIGNATURE"]:
        expected = exporter.expectations(plan, result["page_count"])
        expected["texts"].append(missing)
        ep.write_text(json.dumps(expected), encoding="utf-8")
        audit = exporter.subprocess.run(
            [
                str(runtime),
                str(exporter.INSPECTOR),
                "--pdf",
                str(out),
                "--pdf-sha256",
                exporter.digest(out),
                "--expectations",
                str(ep),
                "--expectations-sha256",
                exporter.digest(ep),
            ],
            capture_output=True,
            text=True,
        )
        assert audit.returncode != 0 and "missing business text" in audit.stdout
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, NumberObject

    for defect in ["logo", "font", "clip"]:
        writer = PdfWriter(clone_from=str(out))
        page: Any = writer.pages[0]
        if defect == "logo":
            del page["/Resources"]["/XObject"]
        elif defect == "font":
            for ref in page["/Resources"]["/Font"].values():
                obj = ref.get_object()
                if obj.get("/FontDescriptor"):
                    descriptor = obj["/FontDescriptor"].get_object()
                    if "/FontFile2" in descriptor:
                        del descriptor[NameObject("/FontFile2")]
        else:
            stream = page.get_contents()
            for operands, op in stream.operations:
                if op == b"re":
                    operands[3] = NumberObject(0)
            page.replace_contents(stream)
        broken = tmp_path / f"broken-{defect}.pdf"
        with broken.open("xb") as dst:
            writer.write(dst)
        expected = exporter.expectations(plan, result["page_count"])
        ep.write_text(json.dumps(expected), encoding="utf-8")
        audit = exporter.subprocess.run(
            [
                str(runtime),
                str(exporter.INSPECTOR),
                "--pdf",
                str(broken),
                "--pdf-sha256",
                exporter.digest(broken),
                "--expectations",
                str(ep),
                "--expectations-sha256",
                exporter.digest(ep),
            ],
            capture_output=True,
            text=True,
        )
        assert audit.returncode != 0, (defect, audit.stdout)
