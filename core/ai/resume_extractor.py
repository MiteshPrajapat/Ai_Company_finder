"""
Extracts plain text from resume files (PDF, DOCX, TXT, MD) with robust fallback handling.
"""

import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from utils.logger import get_logger

logger = get_logger("resume_extractor")


class ResumeExtractor:
    """Extracts and normalizes text from resume files."""

    @staticmethod
    def extract_text(file_path: str) -> str:
        """
        Extracts plain text from a given resume file.
        Supports PDF, DOCX, TXT, MD.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Resume file not found: {file_path}")

        ext = path.suffix.lower()
        if ext == ".pdf":
            return ResumeExtractor._extract_pdf(path)
        elif ext in (".docx", ".doc"):
            return ResumeExtractor._extract_docx(path)
        elif ext in (".txt", ".md", ".rtf"):
            return ResumeExtractor._extract_plain_text(path)
        else:
            # Fallback to plain text read
            return ResumeExtractor._extract_plain_text(path)

    @staticmethod
    def _extract_pdf(path: Path) -> str:
        """Extracts text from PDF using pypdf or PyPDF2 with regex fallback."""
        text_parts = []
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            if text_parts:
                return ResumeExtractor._clean_text("\n".join(text_parts))
        except Exception as e:
            logger.warning(f"pypdf extraction failed for {path}: {e}")

        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(str(path))
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            if text_parts:
                return ResumeExtractor._clean_text("\n".join(text_parts))
        except Exception:
            pass

        # Fallback binary string extraction
        try:
            with open(path, "rb") as f:
                content = f.read().decode("latin-1", errors="ignore")
                matches = re.findall(r"\((.*?)\)T[jJ]", content)
                if matches:
                    return ResumeExtractor._clean_text(" ".join(matches))
        except Exception as e:
            logger.error(f"Fallback PDF extraction failed: {e}")

        return ResumeExtractor._clean_text("\n".join(text_parts))

    @staticmethod
    def _extract_docx(path: Path) -> str:
        """Extracts text from DOCX using python-docx or native ZIP XML parser."""
        try:
            import docx
            doc = docx.Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return ResumeExtractor._clean_text("\n".join(paragraphs))
        except Exception:
            pass

        # Native docx XML extraction without 3rd-party dependency
        try:
            with zipfile.ZipFile(path) as docx_zip:
                xml_content = docx_zip.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                texts = []
                for node in tree.iterfind(".//w:t", namespaces):
                    if node.text:
                        texts.append(node.text)
                return ResumeExtractor._clean_text(" ".join(texts))
        except Exception as e:
            logger.warning(f"DOCX native XML extraction failed for {path}: {e}")
            return ResumeExtractor._extract_plain_text(path)

    @staticmethod
    def _extract_plain_text(path: Path) -> str:
        """Extracts text from plain text formats."""
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                with open(path, "r", encoding=enc, errors="ignore") as f:
                    return ResumeExtractor._clean_text(f.read())
            except Exception:
                continue
        return ""

    @staticmethod
    def _clean_text(text: str) -> str:
        """Removes excessive whitespace and non-printable control characters."""
        if not text:
            return ""
        # Remove null bytes and non-printable chars except newlines and tabs
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
        # Normalize multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Normalize multiple spaces
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()
