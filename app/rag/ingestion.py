import io
import re
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import pypdf
import docx

class DocumentParser:
    """
    Extracts text and heading structure from PDF, DOCX, and TXT documents.
    Preserves section headings to provide rich contextual metadata for chunking.
    """

    @classmethod
    def parse_txt(cls, text_content: str) -> List[Dict[str, str]]:
        """Parses plain text, splitting into sections based on markdown/caps headings."""
        lines = text_content.replace("\r\n", "\n").split("\n")
        sections: List[Dict[str, str]] = []
        current_heading = "General"
        current_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            # Detect Markdown headings (# Header) or All-Caps headings (SECTION NAME)
            if stripped.startswith("#") or (len(stripped) > 3 and stripped.isupper() and len(stripped.split()) <= 6):
                if current_lines:
                    content = "\n".join(current_lines).strip()
                    if content:
                        sections.append({"heading": current_heading, "content": content})
                    current_lines = []
                current_heading = stripped.lstrip("#").strip()
            else:
                if stripped:
                    current_lines.append(stripped)

        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append({"heading": current_heading, "content": content})

        if not sections and text_content.strip():
            sections.append({"heading": "General", "content": text_content.strip()})

        return sections

    @classmethod
    def parse_pdf(cls, file_bytes: bytes) -> List[Dict[str, str]]:
        """Extracts text from PDF bytes and identifies structural headings."""
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        full_text = []
        for page_idx, page in enumerate(reader.pages):
            txt = page.extract_text()
            if txt:
                full_text.append(txt)
        combined_text = "\n\n".join(full_text)
        return cls.parse_txt(combined_text)

    @classmethod
    def parse_docx(cls, file_bytes: bytes) -> List[Dict[str, str]]:
        """Extracts text from DOCX bytes, mapping paragraph styles to headings."""
        doc = docx.Document(io.BytesIO(file_bytes))
        sections: List[Dict[str, str]] = []
        current_heading = "General"
        current_lines: List[str] = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Heading styles in python-docx
            if para.style.name.startswith("Heading") or (len(text) < 60 and text.isupper()):
                if current_lines:
                    content = "\n".join(current_lines).strip()
                    if content:
                        sections.append({"heading": current_heading, "content": content})
                    current_lines = []
                current_heading = text
            else:
                current_lines.append(text)

        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append({"heading": current_heading, "content": content})

        return sections if sections else [{"heading": "General", "content": "Empty document"}]


class SemanticChunker:
    """
    Splits section text into bounded semantic chunks (100-250 words),
    preserving section titles and paragraph boundaries.
    """

    def __init__(self, target_chunk_words: int = 150, overlap_words: int = 25):
        self.target_chunk_words = target_chunk_words
        self.overlap_words = overlap_words

    def chunk_sections(
        self,
        sections: List[Dict[str, str]],
        document_id: str,
        document_title: str
    ) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        chunk_idx = 0

        for sec in sections:
            heading = sec["heading"]
            text = sec["content"]
            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

            current_chunk_words: List[str] = []
            
            # Sentence-bounded paragraph splitting
            units: List[List[str]] = []
            for para in paragraphs:
                if len(para.split()) > self.target_chunk_words:
                    sentences = re.split(r"(?<=[.!?])\s+", para)
                    for s in sentences:
                        if s.strip():
                            units.append(s.strip().split())
                else:
                    units.append(para.split())

            for unit_words in units:
                if len(current_chunk_words) + len(unit_words) <= self.target_chunk_words:
                    current_chunk_words.extend(unit_words)
                else:
                    if current_chunk_words:
                        chunk_text = " ".join(current_chunk_words)
                        chunk_id = f"{document_id}_chk_{chunk_idx:03d}"
                        chunks.append({
                            "chunk_id": chunk_id,
                            "chunk_index": chunk_idx,
                            "document_id": document_id,
                            "document_title": document_title,
                            "heading": heading,
                            "content": chunk_text,
                            "word_count": len(current_chunk_words)
                        })
                        chunk_idx += 1
                        # Retain overlap words
                        overlap = current_chunk_words[-self.overlap_words:] if len(current_chunk_words) > self.overlap_words else []
                        current_chunk_words = overlap + unit_words
                    else:
                        current_chunk_words = unit_words

            if current_chunk_words:
                chunk_text = " ".join(current_chunk_words)
                chunk_id = f"{document_id}_chk_{chunk_idx:03d}"
                chunks.append({
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_idx,
                    "document_id": document_id,
                    "document_title": document_title,
                    "heading": heading,
                    "content": chunk_text,
                    "word_count": len(current_chunk_words)
                })
                chunk_idx += 1

        return chunks


def compute_content_hash(raw_bytes: bytes) -> str:
    """Computes SHA-256 fingerprint of file bytes to prevent duplicate ingestion."""
    return hashlib.sha256(raw_bytes).hexdigest()

