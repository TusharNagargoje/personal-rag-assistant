import os
import hashlib
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
    prepared: list[dict] = []
    to_ingest: list[tuple[dict, Document]] = []
    created_docs: list[Document] = []
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    try:
        for file in files:
            filename = sanitize_input(file.filename or "unknown_file").replace("/", "_").replace("\\", "_")[:180]
            is_valid, err_msg = validate_file(filename, 0, max_mb=settings.MAX_UPLOAD_SIZE_MB)
            if not is_valid:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
            file_type = os.path.splitext(filename)[1].lower().lstrip(".")
            doc_id = str(uuid.uuid4())
            save_path = os.path.join(settings.UPLOAD_DIR, f"{doc_id}_{filename}")
            item = {
                "id": doc_id, "filename": filename, "file_type": file_type,
                "path": save_path, "size": 0, "hash": "",
            }
            prepared.append(item)
            file_size = 0
            with open(save_path, "wb") as output:
                while block := await file.read(1024 * 1024):
                    file_size += len(block)
                    if file_size > max_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB",
                        )
                    output.write(block)
            item["size"] = file_size
            item["hash"] = compute_file_hash(save_path)

        # Validate every file before creating rows or launching any background job.
        for item in prepared:
            duplicate = await db.scalar(
                select(Document).where(Document.file_hash == item["hash"], Document.user_id == current_user.id)
            )
            if duplicate and duplicate.status == "indexed":
                created_docs.append(duplicate)
                os.remove(item["path"])
                continue
            document = Document(
                id=item["id"], collection_id=collection_id, user_id=current_user.id,
                filename=item["filename"], file_type=item["file_type"],
                file_size_bytes=item["size"], file_hash=item["hash"],
                storage_path=item["path"], status="pending",
            )
            db.add(document)
            created_docs.append(document)
            to_ingest.append((item, document))
        await db.commit()
        for item, document in to_ingest:
            await db.refresh(document)
            background_tasks.add_task(
                process_document_ingestion, document_id=item["id"], file_path=item["path"],
                file_type=item["file_type"], collection_id=collection_id,
            )
        return created_docs
    except Exception:
        await db.rollback()
        for item in prepared:
            if os.path.exists(item["path"]):
                os.remove(item["path"])
        raise


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
