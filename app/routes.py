import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .services.anonymisation_service import ENTITY_TYPES as ANONYMISE_ENTITY_TYPES, anonymise_files
from .services.job_manager import create_job, get_job, run_in_background
from .services.processing import run_oe_test
from .services.redaction_service import build_rules, redact_files, validate_rule
from .services.unified_api_client import get_api

bp = Blueprint("main", __name__)

LIST_FILE_EXTENSIONS = {"xlsx", "xls", "csv"}
SAMPLE_FILE_EXTENSIONS = {"pdf", "doc", "docx", "png", "jpg", "jpeg", "tiff", "xlsx", "xls", "csv"}
ANONYMISE_FILE_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx"}
REDACT_FILE_EXTENSIONS = {"docx", "pptx", "xlsx", "pdf"}

MAX_WORDS = 100
MAX_FILE_SIZE_MB = 15
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_EXTRACTION_FIELDS = 10
MAX_COMPUTE_FIELDS = 5
MAX_SAMPLE_FILES = 25
MAX_ANONYMISE_FILES = 25
MAX_REDACT_FILES = 25

# Text/textarea fields on the form that are subject to the word-count limit.
WORD_LIMITED_TEXT_FIELDS = [
    "audit_name", "test_name", "test_objective", "justification_for_sample",
    "overall_pass_fail_criteria", "output_filename", "human_reviewed_by",
]


def _allowed_list_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in LIST_FILE_EXTENSIONS


def _allowed_sample_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in SAMPLE_FILE_EXTENSIONS


def _allowed_anonymise_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ANONYMISE_FILE_EXTENSIONS


def _allowed_redact_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in REDACT_FILE_EXTENSIONS


def _word_count(text: str) -> int:
    return len(text.split())


def _file_size(file_storage: FileStorage) -> int:
    file_storage.stream.seek(0, 2)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    return size


def _parse_fields_file(file_storage: FileStorage) -> list[dict[str, Any]]:
    """Reads a name/type/description[/source_fields] table from an uploaded csv/xlsx into field dicts."""
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    df = pd.read_csv(file_storage) if ext == "csv" else pd.read_excel(file_storage)
    df.columns = [str(c).strip().lower() for c in df.columns]

    fields = []
    for _, row in df.iterrows():
        name = str(row.get("name", "") or "").strip()
        if not name:
            continue
        field: dict[str, Any] = {
            "name": name,
            "type": str(row.get("type", "str") or "str").strip().lower(),
            "description": str(row.get("description", "") or "").strip(),
        }
        source_fields_raw = str(row.get("source_fields", "") or "").strip()
        if source_fields_raw:
            field["source_fields"] = [s.strip() for s in re.split(r"[|,]", source_fields_raw) if s.strip()]
        primary_raw = str(row.get("primary", "") or "").strip().lower()
        if primary_raw in {"true", "yes", "1"}:
            field["is_primary"] = True
        fields.append(field)
    return fields


@bp.route("/", methods=["GET"])
def home():
    return render_template("home.html")


@bp.route("/oe-test", methods=["GET"])
def oe_test_page():
    return render_template("oe_test.html")


@bp.route("/anonymise", methods=["GET"])
def anonymise_page():
    entity_labels = {
        "EMAIL_ADDRESS": "Email Address",
        "PHONE_NUMBER": "Phone Number",
        "TFN": "Tax File Number (TFN)",
        "DRIVER_LICENSE": "Driver Licence",
        "LOCATION": "Location",
        "PERSON": "Person Name",
        "ABN": "Australian Business Number (ABN)",
        "MEDICARE": "Medicare Number",
    }
    entities = [(e, entity_labels.get(e, e.replace("_", " ").title())) for e in ANONYMISE_ENTITY_TYPES]
    return render_template("anonymise.html", entity_types=entities)


@bp.route("/redact", methods=["GET"])
def redact_page():
    return render_template("redact.html")


@bp.route("/parse-fields-file", methods=["POST"])
def parse_fields_file():
    """Parses an uploaded Extraction/Compute Structure file so the UI can preview it as manual rows."""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "No file provided."}), 400
    if not _allowed_list_file(file.filename):
        return jsonify({"ok": False, "error": "File must be .xlsx, .xls, or .csv."}), 400
    try:
        fields = _parse_fields_file(file)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Could not read file: {exc}"}), 400
    return jsonify({"ok": True, "fields": fields})


@bp.route("/submit", methods=["POST"])
def submit():
    form = request.form
    errors = []

    required_fields = [
        "audit_name", "test_name", "test_date", "test_type", "test_objective",
        "output_filename", "overall_pass_fail_criteria", "human_reviewed_by", "human_review_date",
    ]
    for field in required_fields:
        if not form.get(field, "").strip():
            errors.append(f"'{field}' is required.")

    for field in WORD_LIMITED_TEXT_FIELDS:
        word_count = _word_count(form.get(field, ""))
        if word_count > MAX_WORDS:
            errors.append(f"'{field}' exceeds the {MAX_WORDS}-word limit ({word_count} words).")

    if form.get("evidence_not_confidential") != "on":
        errors.append("Confirm that the submitted evidence is not Confidential, Highly Confidential, and/or personal information.")
    if form.get("evidence_manually_reviewed") != "on":
        errors.append("Confirm that a human has manually reviewed the evidence files for appropriateness.")

    list_file_check = request.files.get("list_of_samples")
    if list_file_check and list_file_check.filename and _file_size(list_file_check) > MAX_FILE_SIZE_BYTES:
        errors.append(f"List of Samples file exceeds the {MAX_FILE_SIZE_MB} MB limit.")

    try:
        extraction_fields = json.loads(form.get("extraction_fields_json", "[]"))
        compute_fields = json.loads(form.get("compute_fields_json", "[]"))
    except json.JSONDecodeError:
        extraction_fields, compute_fields = [], []
        errors.append("Extraction/Compute structure was not valid JSON.")

    extraction_fields_file = request.files.get("extraction_fields_file")
    if extraction_fields_file and extraction_fields_file.filename:
        if not _allowed_list_file(extraction_fields_file.filename):
            errors.append("Extraction Structure file must be .xlsx, .xls, or .csv.")
        elif _file_size(extraction_fields_file) > MAX_FILE_SIZE_BYTES:
            errors.append(f"Extraction Structure file exceeds the {MAX_FILE_SIZE_MB} MB limit.")
        else:
            try:
                extraction_fields = _parse_fields_file(extraction_fields_file)
            except Exception as exc:
                errors.append(f"Could not read Extraction Structure file: {exc}")

    compute_fields_file = request.files.get("compute_fields_file")
    if compute_fields_file and compute_fields_file.filename:
        if not _allowed_list_file(compute_fields_file.filename):
            errors.append("Compute Structure file must be .xlsx, .xls, or .csv.")
        elif _file_size(compute_fields_file) > MAX_FILE_SIZE_BYTES:
            errors.append(f"Compute Structure file exceeds the {MAX_FILE_SIZE_MB} MB limit.")
        else:
            try:
                compute_fields = _parse_fields_file(compute_fields_file)
            except Exception as exc:
                errors.append(f"Could not read Compute Structure file: {exc}")

    if not extraction_fields:
        errors.append("At least one Extraction Structure field is required.")
    elif len(extraction_fields) > MAX_EXTRACTION_FIELDS:
        errors.append(f"Extraction Structure is limited to {MAX_EXTRACTION_FIELDS} fields ({len(extraction_fields)} provided).")
    else:
        primary_count = sum(1 for f in extraction_fields if f.get("is_primary"))
        if primary_count != 1:
            errors.append(
                "Mark exactly one Extraction Structure field as the primary identifier field "
                "(used to match samples against the List of Samples file)."
            )

    if len(compute_fields) > MAX_COMPUTE_FIELDS:
        errors.append(f"Compute Structure is limited to {MAX_COMPUTE_FIELDS} fields ({len(compute_fields)} provided).")

    for f in extraction_fields + compute_fields:
        name_words = _word_count(f.get("name", ""))
        desc_words = _word_count(f.get("description", ""))
        if name_words > MAX_WORDS or desc_words > MAX_WORDS:
            errors.append(f"Field '{f.get('name', '?')}' name/description exceeds the {MAX_WORDS}-word limit.")

    extraction_field_names = {f.get("name") for f in extraction_fields if f.get("name")}
    for cf in compute_fields:
        sources = cf.get("source_fields") or []
        if not 1 <= len(sources) <= 2:
            errors.append(
                f"Compute field '{cf.get('name', '?')}' must reference 1 or 2 Extraction Structure fields."
            )
        else:
            unknown = [s for s in sources if s not in extraction_field_names]
            if unknown:
                errors.append(
                    f"Compute field '{cf.get('name', '?')}' references unknown extraction field(s): "
                    + ", ".join(unknown)
                )

    uploaded_samples = [f for f in request.files.getlist("sample_files") if f.filename]
    if not uploaded_samples:
        errors.append("Select at least one sample file.")
    elif len(uploaded_samples) > MAX_SAMPLE_FILES:
        errors.append(f"Sample/Evidence Files is limited to {MAX_SAMPLE_FILES} files ({len(uploaded_samples)} provided).")
    oversized_samples = [f.filename for f in uploaded_samples if _file_size(f) > MAX_FILE_SIZE_BYTES]
    if oversized_samples:
        errors.append(f"Sample file(s) exceed the {MAX_FILE_SIZE_MB} MB limit: " + ", ".join(oversized_samples))
    invalid_samples = [f.filename for f in uploaded_samples if not _allowed_sample_file(f.filename)]
    if invalid_samples:
        errors.append("Sample selection contains unsupported files: " + ", ".join(invalid_samples))

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(parents=True, exist_ok=True)

    sample_upload_dir = upload_dir / f"samples_{uuid4().hex}"
    sample_upload_dir.mkdir()
    for sample in uploaded_samples:
        sample.save(sample_upload_dir / secure_filename(Path(sample.filename).name))

    list_of_samples_path = None
    list_file = request.files.get("list_of_samples")
    if list_file and list_file.filename and _allowed_list_file(list_file.filename):
        saved_path = upload_dir / f"samples_{uuid4().hex}_{secure_filename(list_file.filename)}"
        list_file.save(saved_path)
        list_of_samples_path = str(saved_path)

    job_data = {
        "audit_name": form["audit_name"],
        "test_name": form["test_name"],
        "test_date": form["test_date"],
        "test_type": form["test_type"],
        "test_objective": form["test_objective"],
        "population": form.get("population", "").strip(),
        "sample_size": form.get("sample_size", "").strip(),
        "justification_for_sample": form.get("justification_for_sample", "").strip(),
        "sample_source": str(sample_upload_dir),
        "output_filename": form["output_filename"].strip(),
        "overall_pass_fail_criteria": form["overall_pass_fail_criteria"],
        "human_reviewed_by": form["human_reviewed_by"].strip(),
        "human_review_date": form["human_review_date"],
        "ignore_sample_mismatch": form.get("ignore_sample_mismatch") == "true",
        "extraction_fields": extraction_fields,
        "compute_fields": compute_fields,
        "list_of_samples_path": list_of_samples_path,
    }

    job = create_job()
    cfg = current_app.config
    run_in_background(
        job,
        lambda j: run_oe_test(
            j, job_data, cfg["OUTPUT_FOLDER"], cfg["UNIFIED_API_ENV"], cfg["CLIENT_ID"], cfg["CLIENT_SECRET"]
        ),
    )
    return jsonify({"ok": True, "job_id": job.id})


@bp.route("/status/<job_id>", methods=["GET"])
def status(job_id: str):
    job = get_job(job_id)
    if job is None:
        return jsonify({"ok": False, "error": "Unknown job id."}), 404
    return jsonify({"ok": True, **job.to_dict()})


@bp.route("/download/<path:filename>")
def download_file(filename: str):
    return send_from_directory(current_app.config["OUTPUT_FOLDER"], filename, as_attachment=True)


@bp.route("/anonymise/submit", methods=["POST"])
def anonymise_submit():
    errors = []

    entity_types = request.form.getlist("entity_types")
    invalid_entities = [e for e in entity_types if e not in ANONYMISE_ENTITY_TYPES]
    if invalid_entities:
        errors.append("Unsupported entity type(s) selected: " + ", ".join(invalid_entities))
    if not entity_types:
        errors.append("Select at least one type of information to anonymise.")

    uploaded_files = [f for f in request.files.getlist("files") if f.filename]
    if not uploaded_files:
        errors.append("Select at least one file to anonymise.")
    elif len(uploaded_files) > MAX_ANONYMISE_FILES:
        errors.append(f"You can anonymise at most {MAX_ANONYMISE_FILES} files at a time ({len(uploaded_files)} provided).")
    oversized = [f.filename for f in uploaded_files if _file_size(f) > MAX_FILE_SIZE_BYTES]
    if oversized:
        errors.append(f"File(s) exceed the {MAX_FILE_SIZE_MB} MB limit: " + ", ".join(oversized))
    invalid_files = [f.filename for f in uploaded_files if not _allowed_anonymise_file(f.filename)]
    if invalid_files:
        errors.append("Unsupported file type(s): " + ", ".join(invalid_files))

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    batch_dir = upload_dir / f"anonymise_{uuid4().hex}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = []
    for f in uploaded_files:
        path = batch_dir / secure_filename(Path(f.filename).name)
        f.save(path)
        saved_paths.append(path)

    job = create_job()
    cfg = current_app.config

    def _run(j):
        api = get_api(cfg["UNIFIED_API_ENV"], cfg["CLIENT_ID"], cfg["CLIENT_SECRET"])
        j.result = anonymise_files(j, api, saved_paths, entity_types)
        return None

    run_in_background(job, _run)
    return jsonify({"ok": True, "job_id": job.id})


@bp.route("/redact/validate-rule", methods=["POST"])
def redact_validate_rule():
    data = request.get_json(silent=True) or {}
    problems = validate_rule(
        str(data.get("label", "")), str(data.get("pattern_type", "format")), str(data.get("pattern", ""))
    )
    return jsonify({"ok": not problems, "problems": problems})


@bp.route("/redact/submit", methods=["POST"])
def redact_submit():
    errors = []

    try:
        raw_rules = json.loads(request.form.get("rules_json", "[]"))
    except json.JSONDecodeError:
        raw_rules = []
        errors.append("Redaction rules were not valid JSON.")

    if not raw_rules:
        errors.append("Add at least one redaction rule.")

    uploaded_files = [f for f in request.files.getlist("files") if f.filename]
    if not uploaded_files:
        errors.append("Select at least one file to redact.")
    elif len(uploaded_files) > MAX_REDACT_FILES:
        errors.append(f"You can redact at most {MAX_REDACT_FILES} files at a time ({len(uploaded_files)} provided).")
    oversized = [f.filename for f in uploaded_files if _file_size(f) > MAX_FILE_SIZE_BYTES]
    if oversized:
        errors.append(f"File(s) exceed the {MAX_FILE_SIZE_MB} MB limit: " + ", ".join(oversized))
    invalid_files = [f.filename for f in uploaded_files if not _allowed_redact_file(f.filename)]
    if invalid_files:
        errors.append(
            "Unsupported file type(s) - only Word (.docx), PowerPoint (.pptx), Excel (.xlsx), and PDF (.pdf) "
            "are supported: " + ", ".join(invalid_files)
        )

    rules, rule_errors = build_rules(raw_rules) if raw_rules else ([], [])
    errors.extend(rule_errors)

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    batch_dir = upload_dir / f"redact_{uuid4().hex}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = []
    for f in uploaded_files:
        path = batch_dir / secure_filename(Path(f.filename).name)
        f.save(path)
        saved_paths.append(path)

    output_dir = Path(current_app.config["OUTPUT_FOLDER"]) / f"redacted_{uuid4().hex}"
    try:
        zip_path, summary = redact_files(saved_paths, rules, output_dir)
    except Exception as exc:
        return jsonify({"ok": False, "errors": [f"Redaction failed: {exc}"]}), 500

    download_path = f"{output_dir.name}/{zip_path.name}"
    return jsonify({"ok": True, "summary": summary, "download_path": download_path})
