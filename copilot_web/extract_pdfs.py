#!/usr/bin/env python3
"""
extract_pdfs.py - Build-time PDF text extraction script.

This script runs during Docker build to extract all PDFs to .txt sidecar files.
It handles both text-layer PDFs (pdfplumber) and image-based PDFs (OCR via pytesseract).

Usage:
    python extract_pdfs.py

Outputs:
    For each PDF in projects/*/:
        - {pdf_name}.txt (extracted text)
"""

import os
import sys
import glob
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")


def _is_image_based_pdf(pdf_path: str, sample_pages: int = 2) -> bool:
    """Quick check: if pdfplumber extracts <100 chars from first N pages, treat as image-based."""
    try:
        import pdfplumber
        total_text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages[:sample_pages]):
                text = page.extract_text() or ""
                total_text += text
        return len(total_text.strip()) < 100
    except Exception:
        return True  # Assume image-based on any error


def _extract_with_pdfplumber(pdf_path: str, max_pages: int = 50) -> str:
    """Extract text from text-layer PDF. Returns empty string if failed."""
    try:
        import pdfplumber
        lines = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:max_pages]:
                text = page.extract_text()
                if text:
                    for line in text.splitlines():
                        line = line.strip()
                        if len(line) > 3:
                            lines.append(line)
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"  pdfplumber failed: {e}")
        return ""


def _extract_with_ocr(pdf_path: str, max_pages: int = 50) -> str:
    """Extract text from image-based PDF using OCR."""
    try:
        from pdf2image import convert_from_path
        import pytesseract

        logger.info(f"  Running OCR on {os.path.basename(pdf_path)}...")
        images = convert_from_path(pdf_path, first_page=1, last_page=max_pages, dpi=150)

        lines = []
        for i, image in enumerate(images):
            text = pytesseract.image_to_string(image, config='--psm 6')
            if text:
                for line in text.splitlines():
                    line = line.strip()
                    if len(line) > 3:
                        lines.append(line)

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"  OCR failed: {e}")
        return ""


def extract_pdf(pdf_path: str) -> str:
    """Extract text from PDF using best method. Returns text or empty string."""
    logger.info(f"Extracting: {os.path.basename(pdf_path)}")

    # First try: pdfplumber (fast for text-layer PDFs)
    text = _extract_with_pdfplumber(pdf_path)

    # If empty or very short, try OCR (for image-based PDFs)
    if len(text.strip()) < 200:
        logger.info(f"  Text extraction yielded {len(text)} chars, trying OCR...")
        text = _extract_with_ocr(pdf_path)

    return text


def process_all_pdfs():
    """Process all PDFs in all project directories."""
    if not os.path.exists(PROJECTS_DIR):
        logger.error(f"Projects directory not found: {PROJECTS_DIR}")
        return 1

    pdf_count = 0
    success_count = 0
    fail_count = 0

    # Find all project directories
    project_dirs = [d for d in os.listdir(PROJECTS_DIR)
                    if os.path.isdir(os.path.join(PROJECTS_DIR, d))]

    logger.info(f"Found {len(project_dirs)} project directories")

    for project_slug in sorted(project_dirs):
        project_path = os.path.join(PROJECTS_DIR, project_slug)

        # Find all PDFs in this project
        pdf_patterns = [
            os.path.join(project_path, "variance_*.pdf"),
            os.path.join(project_path, "verify_*.pdf"),
            os.path.join(project_path, "compression_*.pdf"),
            os.path.join(project_path, "*.pdf"),  # Catch any others
        ]

        pdfs = set()
        for pattern in pdf_patterns:
            pdfs.update(glob.glob(pattern))

        if not pdfs:
            continue

        logger.info(f"\n[{project_slug}] {len(pdfs)} PDF(s) found")

        for pdf_path in sorted(pdfs):
            pdf_count += 1
            txt_path = pdf_path.replace('.pdf', '.txt')

            # Skip if already extracted
            if os.path.exists(txt_path) and os.path.getsize(txt_path) > 100:
                logger.info(f"  ✓ Already extracted: {os.path.basename(txt_path)}")
                success_count += 1
                continue

            # Extract text
            text = extract_pdf(pdf_path)

            if text and len(text.strip()) > 50:
                try:
                    with open(txt_path, 'w', encoding='utf-8') as f:
                        f.write(text)
                    logger.info(f"  ✓ Saved: {os.path.basename(txt_path)} ({len(text)} chars)")
                    success_count += 1
                except Exception as e:
                    logger.error(f"  ✗ Failed to write {txt_path}: {e}")
                    fail_count += 1
            else:
                logger.warning(f"  ✗ No text extracted from {os.path.basename(pdf_path)}")
                # Create empty marker file so we don't retry
                try:
                    with open(txt_path, 'w', encoding='utf-8') as f:
                        f.write("# No extractable text\n")
                except Exception:
                    pass
                fail_count += 1

    logger.info(f"\n{'='*50}")
    logger.info(f"PDF Extraction Complete:")
    logger.info(f"  Total PDFs: {pdf_count}")
    logger.info(f"  Successful: {success_count}")
    logger.info(f"  Failed/Empty: {fail_count}")

    return 0 if fail_count == 0 else 0  # Don't fail build on extraction errors


if __name__ == "__main__":
    sys.exit(process_all_pdfs())
