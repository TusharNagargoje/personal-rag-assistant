import hashlib
import json
from typing import Optional
from sqlalchemy import select, update
from app.core.logging import logger
from app.db.session import async_session_factory
from app.db.models import Document, Chunk
from app.ingestion.parsers import parse_document
from app.ingestion.chunkers import chunk_parsed_pages
from app.rag.embeddings import get_embedding_provider
from app.rag.vector_store import get_vector_store
from app.rag.retrieval import bm25_retriever


def compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file for duplicate detection."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


async def process_document_ingestion(
    document_id: str,
    file_path: str,
    file_type: str,
    collection_id: Optional[str] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
):
    """
    Background worker that parses, chunks, embeds, and indexes a document.
    """
    logger.info(f"Starting background ingestion for document {document_id} ({file_type})")
    async with async_session_factory() as db:
        # Mark as processing
        await db.execute(
            update(Document).where(Document.id == document_id).values(status="processing")
        )
        await db.commit()

        try:
            # 1. Parse document into pages
            pages = parse_document(file_path=file_path, file_type=file_type)
            if not pages:
                raise ValueError("No extractable text content found in document.")

            # 2. Chunk pages
            chunks = chunk_parsed_pages(pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            if not chunks:
                raise ValueError("Document produced 0 text chunks after processing.")

            # 3. Retrieve document metadata (e.g. filename)
            doc_res = await db.execute(select(Document).where(Document.id == document_id))
            doc_obj = doc_res.scalar_one()
            filename = doc_obj.filename

            # 4. Generate embeddings
            embed_provider = get_embedding_provider()
            chunk_texts = [c.content for c in chunks]
            embeddings = embed_provider.embed_documents(chunk_texts)

            # 5. Save chunks to SQL DB and Vector Store
            chunk_db_objects = []
            chunk_ids = []
            doc_ids = []
            metadatas = []

            for idx, (chunk_data, emb) in enumerate(zip(chunks, embeddings)):
                cid = f"{document_id}_{idx}"
                chunk_ids.append(cid)
                doc_ids.append(document_id)

                meta = {
                    "filename": filename,
                    "page_number": chunk_data.page_number,
                    "section_name": chunk_data.section_name,
                    "chunk_index": idx,
                    **chunk_data.metadata,
                }
                metadatas.append(meta)

                chunk_db_obj = Chunk(
                    id=cid,
                    document_id=document_id,
                    collection_id=collection_id,
                    chunk_index=idx,
                    content=chunk_data.content,
                    page_number=chunk_data.page_number,
                    section_name=chunk_data.section_name,
                    metadata_json=json.dumps(meta),
                    vector_id=cid,
                )
                chunk_db_objects.append(chunk_db_obj)

            db.add_all(chunk_db_objects)

            # 6. Index into Vector Store
            vector_store = get_vector_store()
            vector_store.add_chunks(
                chunk_ids=chunk_ids,
                documents_ids=doc_ids,
                contents=chunk_texts,
                embeddings=embeddings,
                metadatas=metadatas,
                collection_id=collection_id,
            )

            # 7. Update BM25 In-Memory Index
            # Append new chunks to BM25 corpus
            await db.flush()
            existing_chunks_res = await db.execute(select(Chunk))
            all_chunks = existing_chunks_res.scalars().all()
            bm25_retriever.update_index(
                chunk_ids=[c.id for c in all_chunks],
                doc_ids=[c.document_id for c in all_chunks],
                texts=[c.content for c in all_chunks],
                metadatas=[json.loads(c.metadata_json or "{}") for c in all_chunks],
                collection_ids=[c.collection_id for c in all_chunks],
            )

            # 8. Mark document as indexed
            total_tokens = sum(c.metadata.get("estimated_tokens", 0) for c in chunks)
            await db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status="indexed",
                    chunk_count=len(chunks),
                    token_count=total_tokens,
                    error_message=None,
                )
            )
            await db.commit()
            logger.info(f"Document {document_id} indexed successfully ({len(chunks)} chunks).")

        except Exception as e:
            logger.error(f"Failed to ingest document {document_id}: {e}", exc_info=True)
            await db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status="failed", error_message=str(e)[:500])
            )
            await db.commit()
