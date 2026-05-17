from __future__ import annotations

from pathlib import Path
import csv
import io
import subprocess
import tempfile

import fitz
from docx import Document
from pypdf import PdfReader

from .config import AppSettings
from .schemas import IngestedBook, InputType, OCRMetadata
from .utils import normalize_text, read_text_with_fallback


def ingest_book(path: Path, input_type: InputType, settings: AppSettings) -> IngestedBook:
    if input_type == InputType.TXT:
        text = normalize_text(read_text_with_fallback(path))
        return IngestedBook(
            book_id=path.stem,
            title=path.stem,
            input_path=str(path),
            input_type=input_type,
            normalized_text=text,
        )

    if input_type == InputType.DOCX:
        document = Document(path)
        paragraphs = [para.text.strip() for para in document.paragraphs if para.text.strip()]
        text = normalize_text("\n".join(paragraphs))
        return IngestedBook(
            book_id=path.stem,
            title=path.stem,
            input_path=str(path),
            input_type=input_type,
            normalized_text=text,
        )

    if input_type == InputType.PDF:
        return _ingest_pdf(path, settings)

    raise ValueError(f"Unsupported input type: {input_type}")


def _ingest_pdf(path: Path, settings: AppSettings) -> IngestedBook:
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    joined_text = normalize_text("\n\n".join(page for page in pages if page))
    if len(joined_text) >= settings.pipeline.min_pdf_text_chars:
        return IngestedBook(
            book_id=path.stem,
            title=path.stem,
            input_path=str(path),
            input_type=InputType.PDF,
            normalized_text=joined_text,
            page_texts=pages,
        )

    ocr_texts, avg_conf, warnings = _ocr_pdf(path)
    joined_ocr_text = normalize_text("\n\n".join(ocr_texts))
    if avg_conf is not None and avg_conf < settings.pipeline.low_ocr_confidence:
        warnings.append(f"OCR confidence is low: {avg_conf:.2f}")
    return IngestedBook(
        book_id=path.stem,
        title=path.stem,
        input_path=str(path),
        input_type=InputType.PDF,
        normalized_text=joined_ocr_text,
        page_texts=ocr_texts,
        warnings=warnings,
        ocr=OCRMetadata(
            used_ocr=True,
            average_confidence=avg_conf,
            warnings=warnings,
        ),
    )


def _ocr_pdf(path: Path) -> tuple[list[str], float | None, list[str]]:
    warnings: list[str] = []
    langs = _choose_tesseract_languages()
    doc = fitz.open(path)
    texts: list[str] = []
    confidences: list[float] = []
    with tempfile.TemporaryDirectory(prefix="novel-agent-ocr-") as tmp_dir:
        temp_root = Path(tmp_dir)
        for page_index, page in enumerate(doc):
            image_path = temp_root / f"page-{page_index + 1}.png"
            pixmap = page.get_pixmap(dpi=200, alpha=False)
            pixmap.save(str(image_path))

            text_result = subprocess.run(
                ["tesseract", str(image_path), "stdout", "-l", langs],
                capture_output=True,
                text=True,
                check=False,
            )
            if text_result.returncode != 0:
                warnings.append(f"Tesseract OCR failed on page {page_index + 1}")
                texts.append("")
                continue
            texts.append(text_result.stdout.strip())

            tsv_result = subprocess.run(
                ["tesseract", str(image_path), "stdout", "-l", langs, "tsv"],
                capture_output=True,
                text=True,
                check=False,
            )
            if tsv_result.returncode == 0:
                confidences.extend(_parse_tesseract_confidences(tsv_result.stdout))
    avg_conf = sum(confidences) / len(confidences) if confidences else None
    return texts, avg_conf, warnings


def _choose_tesseract_languages() -> str:
    result = subprocess.run(
        ["tesseract", "--list-langs"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return "eng"
    langs = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if {"chi_sim", "eng"}.issubset(langs):
        return "chi_sim+eng"
    if "chi_sim" in langs:
        return "chi_sim"
    return "eng"


def _parse_tesseract_confidences(raw_tsv: str) -> list[float]:
    values: list[float] = []
    reader = csv.DictReader(io.StringIO(raw_tsv), delimiter="\t")
    for row in reader:
        text = (row.get("text") or "").strip()
        conf = (row.get("conf") or "").strip()
        if not text or not conf:
            continue
        try:
            numeric = float(conf)
        except ValueError:
            continue
        if numeric >= 0:
            values.append(numeric)
    return values
