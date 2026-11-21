import os
import math
import uuid
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.core.logging import logger


class ScoredChunk:
    def __init__(self, chunk_id: str, document_id: str, content: str, score: float, metadata: Dict[str, Any]):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.content = content
        self.score = score
        self.metadata = metadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
        }


class VectorStoreBase:
    def add_chunks(
        self,
        chunk_ids: List[str],
        documents_ids: List[str],
        contents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        collection_id: Optional[str] = None,
    ):
        raise NotImplementedError

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        collection_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
    ) -> List[ScoredChunk]:
        raise NotImplementedError

    def delete_document(self, document_id: str):
        raise NotImplementedError


class LocalMemoryVectorStore(VectorStoreBase):
    """
    In-memory / file-persisted vector store. Runs out of the box with zero setup.
    """
    def __init__(self):
        # Store records: list of dicts {id, doc_id, text, vec, meta, collection_id}
        self.records: List[Dict[str, Any]] = []

    def add_chunks(
        self,
        chunk_ids: List[str],
        documents_ids: List[str],
        contents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        collection_id: Optional[str] = None,
    ):
        for cid, did, text, vec, meta in zip(chunk_ids, documents_ids, contents, embeddings, metadatas):
            # Remove any existing record with same chunk_id
            self.records = [r for r in self.records if r["id"] != cid]
            self.records.append({
                "id": cid,
                "doc_id": did,
                "text": text,
                "vec": vec,
                "meta": meta,
                "collection_id": collection_id,
            })

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        collection_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
    ) -> List[ScoredChunk]:
        scored: List[ScoredChunk] = []
        for r in self.records:
            if collection_id and r.get("collection_id") != collection_id:
                continue
            if document_ids and r.get("doc_id") not in document_ids:
                continue

            # Cosine similarity
            vec = r["vec"]
            dot = sum(a * b for a, b in zip(query_embedding, vec))
            norm_q = math.sqrt(sum(a * a for a, b in zip(query_embedding, query_embedding)))
            norm_v = math.sqrt(sum(b * b for b in vec))
            sim = dot / (norm_q * norm_v) if (norm_q > 0 and norm_v > 0) else 0.0

            scored.append(
                ScoredChunk(
                    chunk_id=r["id"],
                    document_id=r["doc_id"],
                    content=r["text"],
                    score=float(sim),
                    metadata=r["meta"],
                )
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def delete_document(self, document_id: str):
        self.records = [r for r in self.records if r.get("doc_id") != document_id]


class QdrantVectorStore(VectorStoreBase):
    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None):
        self.url = url or settings.QDRANT_URL
        self.api_key = api_key or settings.QDRANT_API_KEY
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.client = None
        self._fallback = LocalMemoryVectorStore()
        self._init_qdrant()

    def _init_qdrant(self):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            if self.url:
                self.client = QdrantClient(url=self.url, api_key=self.api_key, timeout=5)
            else:
                # Use local persistent path in data/vector_store
                qdrant_path = os.path.join(os.getcwd(), "data", "vector_store")
                self.client = QdrantClient(path=qdrant_path)

            # Ensure collection exists
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSION, distance=Distance.COSINE),
                )
            logger.info(f"Qdrant vector store connected: {self.collection_name}")
        except Exception as e:
            logger.warning(f"Could not connect to Qdrant ({e}). Using in-memory fallback vector store.")
            self.client = None

    def add_chunks(
        self,
        chunk_ids: List[str],
        documents_ids: List[str],
        contents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        collection_id: Optional[str] = None,
    ):
        if not self.client:
            return self._fallback.add_chunks(chunk_ids, documents_ids, contents, embeddings, metadatas, collection_id)
        try:
            from qdrant_client.models import PointStruct
            points = []
            for cid, did, text, vec, meta in zip(chunk_ids, documents_ids, contents, embeddings, metadatas):
                payload = {
                    "document_id": did,
                    "content": text,
                    "collection_id": collection_id,
                    **meta,
                }
                # Qdrant accepts integer or UUID point IDs; application chunk IDs are
                # readable composite strings, so map them to stable UUIDs.
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, cid))
                payload["chunk_id"] = cid
                points.append(PointStruct(id=point_id, vector=vec, payload=payload))
            self.client.upsert(collection_name=self.collection_name, points=points)
        except Exception as e:
            logger.error(f"Qdrant upsert failed ({e}). Fallback to local memory.")
            self._fallback.add_chunks(chunk_ids, documents_ids, contents, embeddings, metadatas, collection_id)

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        collection_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
    ) -> List[ScoredChunk]:
        if not self.client:
            return self._fallback.search(query_embedding, top_k, collection_id, document_ids)
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

            conditions = []
            if collection_id:
                conditions.append(FieldCondition(key="collection_id", match=MatchValue(value=collection_id)))
            if document_ids:
                conditions.append(FieldCondition(key="document_id", match=MatchAny(any=document_ids)))

            query_filter = Filter(must=conditions) if conditions else None

            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=top_k,
            )

            scored = []
            for r in results:
                payload = r.payload or {}
                content = payload.get("content", "")
                doc_id = payload.get("document_id", "")
                scored.append(
                    ScoredChunk(
                        chunk_id=payload.get("chunk_id", str(r.id)),
                        document_id=doc_id,
                        content=content,
                        score=float(r.score),
                        metadata=payload,
                    )
                )
            return scored
        except Exception as e:
            logger.error(f"Qdrant search error ({e}). Using local fallback.")
            return self._fallback.search(query_embedding, top_k, collection_id, document_ids)

    def delete_document(self, document_id: str):
        if not self.client:
            return self._fallback.delete_document(document_id)
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                ),
            )
        except Exception as e:
            logger.error(f"Qdrant delete error: {e}")
            self._fallback.delete_document(document_id)


_vector_store_instance: Optional[VectorStoreBase] = None


def get_vector_store() -> VectorStoreBase:
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = QdrantVectorStore()
    return _vector_store_instance
