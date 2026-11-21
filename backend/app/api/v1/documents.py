import os
import shutil
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.core.guardrails import validate_file, sanitize_input
from app.db.session import get_db
from app.db.models import Document, Chunk, User, Collection
from app.schemas.document import (
    DocumentResponse,
    DocumentDetailResponse,
    ChunkResponse,
    IngestUrlRequest,
    IngestYoutubeRequest,
)
from app.api.deps import get_current_user
from app.ingestion.tasks import compute_file_hash, process_document_ingestion
from app.rag.vector_store import get_vector_store

router = APIRouter(prefix="/documents", tags=["Documents"])


async def _check_collection_access(collection_id: Optional[str], user: User, db: AsyncSession) -> None:
    if collection_id:
        result = await db.execute(select(Collection.id).where(Collection.id == collection_id, Collection.user_id == user.id))
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Collection not found")


@router.post("/upload", response_model=List[DocumentResponse], status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    collection_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Multi-file upload with background chunking and vector indexing."""
    await _check_collection_access(collection_id, current_user, db)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    created_docs: List[Document] = []

    for file in files:
        filename = sanitize_input(file.filename or "unknown_file")
        ext = os.path.splitext(filename)[1].lower()
        file_type = ext.replace(".", "")

        # Read into temp storage to compute hash and validate
        doc_uuid = str(uuid.uuid4())
        save_path = os.path.join(settings.UPLOAD_DIR, f"{doc_uuid}_{filename}")
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(save_path)
        is_valid, err_msg = validate_file(filename, file_size, max_mb=settings.MAX_UPLOAD_SIZE_MB)
        if not is_valid:
            if os.path.exists(save_path):
                os.remove(save_path)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)

        file_hash = compute_file_hash(save_path)

        # Duplicate check per user
        dup_res = await db.execute(
            select(Document).where(Document.file_hash == file_hash, Document.user_id == current_user.id)
        )
        existing_doc = dup_res.scalar_one_or_none()
        if existing_doc and existing_doc.status == "indexed":
            # Document already indexed; skip re-indexing
            created_docs.append(existing_doc)
            if os.path.exists(save_path):
                os.remove(save_path)
            continue

        new_doc = Document(
            id=doc_uuid,
            collection_id=collection_id,
            user_id=current_user.id,
            filename=filename,
            file_type=file_type,
            file_size_bytes=file_size,
            file_hash=file_hash,
            storage_path=save_path,
            status="pending",
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)
        created_docs.append(new_doc)

        # Trigger async ingestion
        background_tasks.add_task(
            process_document_ingestion,
            document_id=doc_uuid,
            file_path=save_path,
            file_type=file_type,
            collection_id=collection_id,
        )

    return created_docs


@router.post("/url", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_url(
    payload: IngestUrlRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingest web URL article."""
    doc_uuid = str(uuid.uuid4())
    await _check_collection_access(payload.collection_id, current_user, db)
    filename = payload.title or payload.url[:60]
    import hashlib
    file_hash = hashlib.sha256(payload.url.encode("utf-8")).hexdigest()

    new_doc = Document(
        id=doc_uuid,
        collection_id=payload.collection_id,
        user_id=current_user.id,
        filename=filename,
        file_type="url",
        source_url=payload.url,
        file_hash=file_hash,
        storage_path=payload.url,
        status="pending",
    )
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)

    background_tasks.add_task(
        process_document_ingestion,
        document_id=doc_uuid,
        file_path=payload.url,
        file_type="url",
        collection_id=payload.collection_id,
    )
    return new_doc


@router.post("/youtube", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_youtube(
    payload: IngestYoutubeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingest YouTube video subtitles transcript."""
    await _check_collection_access(payload.collection_id, current_user, db)
    doc_uuid = str(uuid.uuid4())
    filename = payload.title or f"YouTube Video ({payload.youtube_url[:30]})"
    import hashlib
    file_hash = hashlib.sha256(payload.youtube_url.encode("utf-8")).hexdigest()

    new_doc = Document(
        id=doc_uuid,
        collection_id=payload.collection_id,
        user_id=current_user.id,
        filename=filename,
        file_type="youtube",
        source_url=payload.youtube_url,
        file_hash=file_hash,
        storage_path=payload.youtube_url,
        status="pending",
    )
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)

    background_tasks.add_task(
        process_document_ingestion,
        document_id=doc_uuid,
        file_path=payload.youtube_url,
        file_type="youtube",
        collection_id=payload.collection_id,
    )
    return new_doc


@router.get("/", response_model=List[DocumentResponse])
async def list_documents(
    collection_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Document).where(Document.user_id == current_user.id)
    if collection_id:
        query = query.where(Document.collection_id == collection_id)
    query = query.order_by(Document.created_at.desc())

    res = await db.execute(query)
    return res.scalars().all()


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks_res = await db.execute(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index.asc())
    )
    chunks = chunks_res.scalars().all()

    return DocumentDetailResponse(
        id=doc.id,
        collection_id=doc.collection_id,
        user_id=doc.user_id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size_bytes=doc.file_size_bytes,
        file_hash=doc.file_hash,
        source_url=doc.source_url,
        status=doc.status,
        error_message=doc.error_message,
        chunk_count=doc.chunk_count,
        token_count=doc.token_count,
        created_at=doc.created_at,
        chunks=[ChunkResponse.model_validate(c) for c in chunks],
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Remove vector embeddings
    vector_store = get_vector_store()
    vector_store.delete_document(document_id)

    # Remove stored physical file if exists
    if doc.storage_path and os.path.exists(doc.storage_path) and not doc.storage_path.startswith("http"):
        try:
            os.remove(doc.storage_path)
        except Exception:
            pass

    await db.delete(doc)
    await db.commit()
    return None
