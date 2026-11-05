import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.db import get_connection, get_db
from app.rag.ingestion import DocumentParser, SemanticChunker, compute_content_hash
from app.rag.embeddings import SemanticVectorizer

class DocumentManager:
    """
    Manages document ingestion, chunking, semantic embedding, FTS indexing,
    and clinician lifecycle (Draft -> Approved -> Archived).
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.chunker = SemanticChunker(target_chunk_words=120, overlap_words=20)

    def ingest_document(
        self,
        title: str,
        filename: str,
        file_bytes: bytes,
        file_type: str,
        category: str,
        author: str,
        patient_id: Optional[str] = None,
        auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Parses, chunks, hashes, and indexes a PDF/DOCX/TXT document.
        Detects duplicates via SHA-256 hash.
        """
        source_hash = compute_content_hash(file_bytes)
        
        # Check duplicate
        conn = get_connection(self.db_path)
        existing = conn.execute("SELECT id, title, version, approval_status FROM documents WHERE source_hash = ?", (source_hash,)).fetchone()
        if existing:
            conn.close()
            return {
                "status": "duplicate",
                "message": f"Document already exists as '{existing['title']}' (ID: {existing['id']}, Status: {existing['approval_status']})",
                "document_id": existing["id"],
                "version": existing["version"],
                "approval_status": existing["approval_status"]
            }
        conn.close()

        # Parse sections based on file type
        ext = file_type.lower().lstrip(".")
        if ext == "pdf":
            sections = DocumentParser.parse_pdf(file_bytes)
        elif ext in ["docx", "doc"]:
            sections = DocumentParser.parse_docx(file_bytes)
        else:
            text_str = file_bytes.decode("utf-8", errors="replace")
            sections = DocumentParser.parse_txt(text_str)

        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        chunks = self.chunker.chunk_sections(sections, document_id=doc_id, document_title=title)

        status = "approved" if auto_approve else "draft"

        with get_db(self.db_path) as conn:
            # 1. Insert document metadata
            conn.execute("""
                INSERT INTO documents (id, title, filename, file_type, category, source_hash, version, approval_status, author, patient_id)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """, (doc_id, title, filename, ext, category, source_hash, status, author, patient_id))

            # 2. Insert chunks and populate embeddings & FTS
            for chk in chunks:
                emb = SemanticVectorizer.encode(chk["content"])
                conn.execute("""
                    INSERT INTO document_chunks (id, document_id, chunk_index, heading, content, embedding_json, patient_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    chk["chunk_id"],
                    doc_id,
                    chk["chunk_index"],
                    chk["heading"],
                    chk["content"],
                    json.dumps(emb),
                    patient_id
                ))

                conn.execute("""
                    INSERT INTO document_chunks_fts (chunk_id, heading, content)
                    VALUES (?, ?, ?)
                """, (chk["chunk_id"], chk["heading"], chk["content"]))

        return {
            "status": "success",
            "document_id": doc_id,
            "title": title,
            "version": 1,
            "chunk_count": len(chunks),
            "approval_status": status,
            "patient_id": patient_id
        }

    def approve_document(self, doc_id: str) -> Dict[str, Any]:
        with get_db(self.db_path) as conn:
            conn.execute("""
                UPDATE documents
                SET approval_status = 'approved', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (doc_id,))
        return {"status": "success", "document_id": doc_id, "approval_status": "approved"}

    def deactivate_document(self, doc_id: str) -> Dict[str, Any]:
        with get_db(self.db_path) as conn:
            conn.execute("""
                UPDATE documents
                SET approval_status = 'archived', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (doc_id,))
        return {"status": "success", "document_id": doc_id, "approval_status": "archived"}

    def delete_document(self, doc_id: str) -> Dict[str, Any]:
        with get_db(self.db_path) as conn:
            # Delete from FTS first
            chunks = conn.execute("SELECT id FROM document_chunks WHERE document_id = ?", (doc_id,)).fetchall()
            for c in chunks:
                conn.execute("DELETE FROM document_chunks_fts WHERE chunk_id = ?", (c["id"],))
            conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        return {"status": "success", "document_id": doc_id, "deleted": True}

    def list_documents(self, approval_status: Optional[str] = None, patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        query = """
            SELECT 
                d.id, d.title, d.filename, d.file_type, d.category, d.version, 
                d.approval_status, d.author, d.patient_id, d.created_at, d.updated_at,
                COUNT(c.id) as chunk_count
            FROM documents d
            LEFT JOIN document_chunks c ON d.id = c.document_id
            WHERE 1=1
        """
        params: List[Any] = []
        if approval_status:
            query += " AND d.approval_status = ?"
            params.append(approval_status)
        if patient_id is not None:
            query += " AND (d.patient_id IS NULL OR d.patient_id = ?)"
            params.append(patient_id)

        query += " GROUP BY d.id ORDER BY d.created_at DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            conn.close()
            return None
        chunks = conn.execute("SELECT id, chunk_index, heading, content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index ASC", (doc_id,)).fetchall()
        conn.close()
        res = dict(doc)
        res["chunks"] = [dict(c) for c in chunks]
        return res

document_manager = DocumentManager()

