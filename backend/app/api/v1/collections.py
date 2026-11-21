from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.db.models import Collection, Document, User
from app.schemas.collection import CollectionCreate, CollectionUpdate, CollectionResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/collections", tags=["Collections"])


@router.get("/", response_model=List[CollectionResponse])
async def list_collections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Collection).where(Collection.user_id == current_user.id).order_by(Collection.created_at.desc())
    res = await db.execute(query)
    collections = res.scalars().all()

    output = []
    for c in collections:
        doc_count_res = await db.execute(select(func.count(Document.id)).where(Document.collection_id == c.id))
        doc_count = doc_count_res.scalar() or 0
        c_dict = {
            "id": c.id,
            "user_id": c.user_id,
            "name": c.name,
            "description": c.description,
            "color": c.color,
            "icon": c.icon,
            "document_count": doc_count,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        output.append(CollectionResponse(**c_dict))
    return output


@router.post("/", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    col_in: CollectionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    new_col = Collection(
        user_id=current_user.id,
        name=col_in.name,
        description=col_in.description,
        color=col_in.color or "#3B82F6",
        icon=col_in.icon or "folder",
    )
    db.add(new_col)
    await db.commit()
    await db.refresh(new_col)
    return CollectionResponse(
        id=new_col.id,
        user_id=new_col.user_id,
        name=new_col.name,
        description=new_col.description,
        color=new_col.color,
        icon=new_col.icon,
        document_count=0,
        created_at=new_col.created_at,
        updated_at=new_col.updated_at,
    )


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == current_user.id)
    )
    col = res.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    doc_count_res = await db.execute(select(func.count(Document.id)).where(Document.collection_id == col.id))
    doc_count = doc_count_res.scalar() or 0
    return CollectionResponse(
        id=col.id,
        user_id=col.user_id,
        name=col.name,
        description=col.description,
        color=col.color,
        icon=col.icon,
        document_count=doc_count,
        created_at=col.created_at,
        updated_at=col.updated_at,
    )


@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: str,
    col_in: CollectionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == current_user.id)
    )
    col = res.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    if col_in.name is not None:
        col.name = col_in.name
    if col_in.description is not None:
        col.description = col_in.description
    if col_in.color is not None:
        col.color = col_in.color
    if col_in.icon is not None:
        col.icon = col_in.icon

    db.add(col)
    await db.commit()
    await db.refresh(col)
    return col


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == current_user.id)
    )
    col = res.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    await db.delete(col)
    await db.commit()
    return None
