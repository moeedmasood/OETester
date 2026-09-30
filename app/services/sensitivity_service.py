"""Detects Microsoft Purview / AIP sensitivity labels (Confidential, Highly Confidential,
Personal Information) embedded in Office and PDF evidence files, so labelled files can be
blocked from being sent to AI models for extraction or inference.
"""
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

import pymupdf as fitz
from werkzeug.datastructures import FileStorage

OOXML_EXTENSIONS = {"docx", "xlsx", "pptx"}
PDF_EXTENSIONS = {"pdf"}
SENSITIVITY_CHECKED_EXTENSIONS = OOXML_EXTENSIONS | PDF_EXTENSIONS

# Ordered most-specific-first so "highly confidential" isn't reported as "confidential".
SENSITIVE_LABELS = ["Highly Confidential", "Personal Information", "Confidential"]


def _match_label(text: str) -> str | None:
    lowered = text.lower()
    for label in SENSITIVE_LABELS:
        if label.lower() in lowered:
            return label
    return None


def _read_ooxml_custom_properties(data: bytes) -> str:
    """Reads docProps/custom.xml, where Microsoft Purview/AIP stores MSIP_Label_* sensitivity
    label properties on Word/Excel/PowerPoint files, and returns their names/values as text."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            if "docProps/custom.xml" not in zf.namelist():
                return ""
            xml_bytes = zf.read("docProps/custom.xml")
    except (zipfile.BadZipFile, KeyError):
        return ""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""
    parts = []
    for prop in root:
        name = prop.attrib.get("name", "")
        value = "".join(child.text or "" for child in prop)
        parts.append(f"{name} {value}")
    return " ".join(parts)


def _read_pdf_metadata(data: bytes) -> str:
    """Reads the PDF Info dictionary and XMP metadata, where AIP/Purview stores sensitivity
    labels for PDFs, and returns them as text."""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return ""
    try:
        parts = [str(v) for v in (doc.metadata or {}).values() if v]
        get_xml_metadata = getattr(doc, "get_xml_metadata", None)
        if callable(get_xml_metadata):
            xmp = get_xml_metadata()
            if xmp:
                parts.append(xmp)
        return " ".join(parts)
    finally:
        doc.close()


def _extract_text(filename: str, data: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in OOXML_EXTENSIONS:
        return _read_ooxml_custom_properties(data)
    if ext in PDF_EXTENSIONS:
        return _read_pdf_metadata(data)
    return ""


def find_sensitivity_label(file_storage: FileStorage) -> str | None:
    """Returns the sensitivity label ('Confidential', 'Highly Confidential', or
    'Personal Information') found in an uploaded Office/PDF file's metadata, or None
    if unlabelled/unsupported. Leaves the file stream positioned at the start."""
    filename = file_storage.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SENSITIVITY_CHECKED_EXTENSIONS:
        return None
    file_storage.stream.seek(0)
    data = file_storage.stream.read()
    file_storage.stream.seek(0)
    return _match_label(_extract_text(filename, data))


def find_sensitivity_label_path(path: Path) -> str | None:
    """Same as find_sensitivity_label but for a file already saved on disk."""
    ext = path.suffix.lower().lstrip(".")
    if ext not in SENSITIVITY_CHECKED_EXTENSIONS:
        return None
    return _match_label(_extract_text(path.name, path.read_bytes()))
