"""Orchestrates the end-to-end OE testing workflow for one job."""
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

import pandas as pd

from .audit_log_service import audit_event
from .compute_service import compute_overall_conclusion, compute_sample
from .error_handling import SUPPORT_CONTACT
from .excel_writer import write_working_paper
from .extraction_service import extract_sample, flag_missing_fields
from .job_manager import Job
from .unified_api_client import get_api

DOCUMENT_SAMPLE_EXTENSIONS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".tiff"}
EXCEL_SAMPLE_EXTENSIONS = {".xlsx", ".xls", ".csv"}


class PendingSample(NamedTuple):
    label: str
    file_path: Path | None  # set for document/image samples that still need AI extraction
    extracted: dict[str, Any] | None  # pre-populated for samples read from an Excel/CSV row


def find_document_sample_files(folder: str) -> list[Path]:
    folder_path = Path(folder)
    if not folder_path.is_dir():
        raise ValueError(f"Sample source folder does not exist: {folder}")
    return sorted(
        p for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() in DOCUMENT_SAMPLE_EXTENSIONS
    )


def find_excel_sample_files(folder: str) -> list[Path]:
    folder_path = Path(folder)
    return sorted(
        p for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() in EXCEL_SAMPLE_EXTENSIONS
    )


def read_excel_samples(path: Path, extraction_fields: list[dict[str, Any]]) -> list[PendingSample]:
    """Reads one Excel/CSV sample file, returning one PendingSample per row.

    Columns are matched to extraction field names case-insensitively; extraction
    fields with no matching column are left as None (flagged later as not extracted).
    """
    df = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_excel(path)
    column_lookup = {str(c).strip().lower(): c for c in df.columns}

    samples = []
    for i, row in df.iterrows():
        extracted: dict[str, Any] = {}
        for field in extraction_fields:
            name = field["name"]
            column = column_lookup.get(name.strip().lower())
            value = row.get(column) if column is not None else None
            extracted[name] = None if pd.isna(value) else value
        label = f"{path.stem} (row {i + 2})"
        samples.append(PendingSample(label, None, extracted))
    return samples


def read_sample_identifiers(list_path: str) -> list[str]:
    """Reads the first column of the uploaded 'list of samples' file (csv/xlsx)."""
    path = Path(list_path)
    df = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_excel(path)
    if df.empty:
        return []
    return [str(v).strip().lower() for v in df.iloc[:, 0].dropna().tolist()]


def _matches_identifier(value: Any, identifiers: list[str]) -> bool:
    value_l = str(value or "").strip().lower()
    if not value_l:
        return False
    return any(value_l == ident or ident in value_l for ident in identifiers)


def run_oe_test(job: Job, form: dict[str, Any], output_folder: str, env: str, client_id: str, client_secret: str) -> Path:
    api = get_api(env, client_id, client_secret)

    job.log("Validating inputs...")
    document_files = find_document_sample_files(form["sample_source"])
    excel_files = find_excel_sample_files(form["sample_source"])
    if not document_files and not excel_files:
        raise ValueError(
            "No supported sample files found. Attach PDF/Word/image documents and/or an "
            "Excel or CSV file with one sample per row."
        )

    extraction_fields = form["extraction_fields"]
    compute_fields = form["compute_fields"]

    primary_field = next((f["name"] for f in extraction_fields if f.get("is_primary")), None)
    if extraction_fields and not primary_field:
        raise ValueError("Mark one Extraction Structure field as the primary identifier field.")

    pending: list[PendingSample] = [PendingSample(p.stem, p, None) for p in document_files]
    for excel_path in excel_files:
        pending.extend(read_excel_samples(excel_path, extraction_fields))

    sample_rows: list[dict[str, Any]] = []
    resolved: list[tuple[PendingSample, dict[str, Any]]] = []
    for sample in pending:
        job.log(f"Extracting data from {sample.label}...")
        try:
            if sample.extracted is not None:
                extracted, missing_fields = flag_missing_fields(dict(sample.extracted))
            else:
                extracted, missing_fields = extract_sample(api, sample.file_path, extraction_fields)
        except Exception as exc:
            job.log(f"Extraction failed for {sample.label}: {exc}")
            audit_event("sample_error", stage="extraction", sample=sample.label, error=str(exc), exception_type=type(exc).__name__, traceback=traceback.format_exc())
            sample_rows.append({"Sample": sample.label, "pass_fail": "Fail", "rationale": str(exc)})
            continue

        if missing_fields:
            audit_event("missing_fields", sample=sample.label, fields=missing_fields)
            job.log(
                f"Warning: could not extract fields {', '.join(missing_fields)} for "
                f"{sample.label}. Contact {SUPPORT_CONTACT} if this persists."
            )
        resolved.append((sample, extracted))

    list_of_samples_path = form.get("list_of_samples_path")
    if list_of_samples_path:
        identifiers = read_sample_identifiers(list_of_samples_path)
        matched = [
            (sample, extracted) for sample, extracted in resolved
            if _matches_identifier(extracted.get(primary_field), identifiers)
        ]
        if not matched and not form.get("ignore_sample_mismatch"):
            raise ValueError(
                "None of the samples' primary field values matched an identifier in the List of "
                "Samples file. Re-submit with 'ignore mismatch' checked to proceed with all samples."
            )
        if matched:
            resolved = matched

    declared_size = form.get("sample_size")
    if declared_size:
        declared_size = int(declared_size)
        if declared_size != len(resolved) and not form.get("ignore_sample_mismatch"):
            raise ValueError(
                f"Sample size mismatch: {len(resolved)} samples matched, "
                f"but {declared_size} declared. Re-submit with 'ignore mismatch' checked to proceed."
            )

    for sample, extracted in resolved:
        job.log(f"Computing test fields for {sample.label}...")
        try:
            computed = compute_sample(
                api,
                extracted,
                compute_fields,
                form["overall_pass_fail_criteria"],
                form["test_objective"],
            )
        except Exception as exc:
            job.log(f"Computation failed for {sample.label}: {exc}")
            audit_event("sample_error", stage="computation", sample=sample.label, error=str(exc), exception_type=type(exc).__name__, traceback=traceback.format_exc())
            sample_rows.append({"Sample": sample.label, **extracted, "pass_fail": "Fail", "rationale": str(exc)})
            continue

        row = {"Sample": sample.label, **extracted, **computed}
        sample_rows.append(row)

    job.log("Computing overall conclusion across all samples...")
    conclusion_summaries = [
        {"Sample": row["Sample"], "pass_fail": row.get("pass_fail"), "rationale": row.get("rationale")}
        for row in sample_rows
    ]
    overall_conclusion = compute_overall_conclusion(
        api,
        conclusion_summaries,
        form["overall_pass_fail_criteria"],
        form.get("overall_conclusion_instructions", ""),
    )

    job.log("Writing output working paper...")
    metadata = {
        "Audit Name": form["audit_name"],
        "Test Name": form["test_name"],
        "Test Objective": form["test_objective"],
        "Test Date": form["test_date"],
        "Test Type": form["test_type"],
        "Population": form.get("population") or "N/A",
        "Sample Size": len(resolved),
        "Date of Testing": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Human Review Completed By": form["human_reviewed_by"],
        "Human Review Date": form["human_review_date"],
    }
    metadata["Human Review Confirmation"] = (
        f"I confirm that {form['human_reviewed_by']} manually reviewed the evidence files "
        f"for appropriateness on {form['human_review_date']}."
    )

    output_filename = form["output_filename"]
    if not output_filename.lower().endswith(".xlsx"):
        output_filename += ".xlsx"
    output_path = Path(output_folder) / output_filename

    write_working_paper(output_path, metadata, overall_conclusion, sample_rows)
    job.log("Done.")
    return output_path

