"""Text extraction from PDF, DOCX, and TXT files."""

import hashlib
import os
from pathlib import Path

from app.core.logging import get_logger

log = get_logger("text_extraction")


def compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file for deduplication."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF using PyMuPDF (fitz)."""
    import fitz  # PyMuPDF

    text_parts = []
    with fitz.open(file_path) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts).strip()


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX using python-docx."""
    from docx import Document

    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()


def extract_text_from_txt(file_path: str) -> str:
    """Extract text from plain text file."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().strip()


# Map MIME types to extractors
EXTRACTORS = {
    "application/pdf": extract_text_from_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": extract_text_from_docx,
    "text/plain": extract_text_from_txt,
}

# Fallback: map file extensions
EXTENSION_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


def extract_text_from_file(file_path: str, mime_type: str | None = None) -> str:
    """Extract text from a file, auto-detecting format if needed.

    Args:
        file_path: Path to the file on disk.
        mime_type: Optional MIME type hint. Falls back to extension detection.

    Returns:
        Extracted plain text.

    Raises:
        ValueError: If file format is unsupported.
        FileNotFoundError: If file does not exist.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Resolve MIME type from extension if not provided
    if mime_type is None or mime_type not in EXTRACTORS:
        ext = Path(file_path).suffix.lower()
        mime_type = EXTENSION_MAP.get(ext)

    if mime_type is None or mime_type not in EXTRACTORS:
        raise ValueError(
            f"Unsupported file format: {Path(file_path).suffix}. "
            f"Supported: {', '.join(EXTENSION_MAP.keys())}"
        )

    extractor = EXTRACTORS[mime_type]
    text = extractor(file_path)

    log.info(
        "text_extracted",
        file_path=file_path,
        mime_type=mime_type,
        word_count=len(text.split()) if text else 0,
    )
    return text
