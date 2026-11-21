import re
from typing import List, Dict, Any, Optional
from collections import defaultdict
from app.core.config import settings
from app.core.logging import logger
from app.rag.embeddings import get_embedding_provider
from app.rag.vector_store import get_vector_store, ScoredChunk


class BM25Retriever:
    """In-memory BM25 index built from current database/vector chunks."""
    def __init__(self):
        self.chunk_ids: List[str] = []
        self.doc_ids: List[str] = []
        self.collection_ids: List[Optional[str]] = []
        self.corpus: List[List[str]] = []
        self.raw_texts: List[str] = []
        self.metadatas: List[Dict[str, Any]] = []
        self._bm25 = None

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def update_index(
        self,
        chunk_ids: List[str],
        doc_ids: List[str],
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        collection_ids: Optional[List[Optional[str]]] = None,
    ):
        self.chunk_ids = chunk_ids
        self.doc_ids = doc_ids
        self.raw_texts = texts
        self.metadatas = metadatas
        self.collection_ids = collection_ids or [None] * len(chunk_ids)
        self.corpus = [self._tokenize(t) for t in texts]

        if self.corpus:
            try:
                from rank_bm25 import BM25Okapi
                self._bm25 = BM25Okapi(self.corpus)
            except Exception as e:
                logger.warning(f"Could not initialize BM25Okapi: {e}")
                self._bm25 = None

    def search(
        self,
        query: str,
        top_k: int = 5,
        collection_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
    ) -> List[ScoredChunk]:
        if not self._bm25 or not self.chunk_ids:
            return []

        tokens = self._tokenize(query)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)
        scored_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        results: List[ScoredChunk] = []
        for idx in scored_indices:
            if scores[idx] <= 0:
                continue
            if collection_id and self.collection_ids[idx] != collection_id:
                continue
            if document_ids and self.doc_ids[idx] not in document_ids:
                continue

            results.append(
                ScoredChunk(
                    chunk_id=self.chunk_ids[idx],
                    document_id=self.doc_ids[idx],
                    content=self.raw_texts[idx],
                    score=float(scores[idx]),
                    metadata=self.metadatas[idx],
                )
            )
            if len(results) >= top_k:
                break

        return results


bm25_retriever = BM25Retriever()


class CrossEncoderReranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None and settings.RAG_ENABLE_RERANKER:
            try:
                from sentence_transformers import CrossEncoder
                logger.info(f"Loading CrossEncoder: {self.model_name}")
                self._model = CrossEncoder(self.model_name)
            except Exception as e:
                logger.warning(f"CrossEncoder unavailable ({e}). Skipping neural rerank.")
                self._model = False
        return self._model

    def rerank(self, query: str, chunks: List[ScoredChunk], top_k: int) -> List[ScoredChunk]:
        if not chunks:
            return []
        model = self._get_model()
        if not model:
            # Fallback: keep original hybrid rank
            return chunks[:top_k]

        try:
            pairs = [[query, chunk.content] for chunk in chunks]
            scores = model.predict(pairs)
            for chunk, score in zip(chunks, scores):
                chunk.score = float(score)
            chunks.sort(key=lambda x: x.score, reverse=True)
            return chunks[:top_k]
        except Exception as e:
            logger.error(f"Reranking error: {e}")
            return chunks[:top_k]


cross_encoder = CrossEncoderReranker()


def reciprocal_rank_fusion(
    dense_results: List[ScoredChunk],
    sparse_results: List[ScoredChunk],
    k: int = 60,
    dense_weight: float = 0.7,
    sparse_weight: float = 0.3,
) -> List[ScoredChunk]:
    """Combine dense and sparse search rankings using Reciprocal Rank Fusion."""
    rrf_scores = defaultdict(float)
    chunk_map: Dict[str, ScoredChunk] = {}

    for rank, chunk in enumerate(dense_results):
        chunk_map[chunk.chunk_id] = chunk
        rrf_scores[chunk.chunk_id] += dense_weight * (1.0 / (k + rank + 1))

    for rank, chunk in enumerate(sparse_results):
        if chunk.chunk_id not in chunk_map:
            chunk_map[chunk.chunk_id] = chunk
        rrf_scores[chunk.chunk_id] += sparse_weight * (1.0 / (k + rank + 1))

    combined: List[ScoredChunk] = []
    for chunk_id, fused_score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
        chunk = chunk_map[chunk_id]
        chunk.score = fused_score
        combined.append(chunk)

    return combined


async def hybrid_retrieve(
    query: str,
    top_k: Optional[int] = None,
    collection_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    embeddings_provider: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[ScoredChunk]:
    """Orchestrate dense vector search, BM25 keyword search, RRF fusion, and cross-encoder reranking."""
    if document_ids is not None and not document_ids:
        return []
    k = top_k or settings.RAG_TOP_K
    vector_store = get_vector_store()
    embeddings = get_embedding_provider(embeddings_provider, api_key=api_key)

    # 1. Dense retrieval (fetch 2 * k candidates)
    query_vector = embeddings.embed_query(query)
    dense_results = vector_store.search(
        query_embedding=query_vector,
        top_k=k * 2,
        collection_id=collection_id,
        document_ids=document_ids,
    )
    dense_results = [item for item in dense_results if item.score >= settings.RAG_SIMILARITY_THRESHOLD]

    # 2. Sparse retrieval (BM25)
    sparse_results: List[ScoredChunk] = []
    if settings.RAG_ENABLE_HYBRID_SEARCH:
        sparse_results = bm25_retriever.search(
            query=query,
            top_k=k * 2,
            collection_id=collection_id,
            document_ids=document_ids,
        )

    # 3. Reciprocal Rank Fusion
    if sparse_results:
        fused = reciprocal_rank_fusion(
            dense_results=dense_results,
            sparse_results=sparse_results,
            dense_weight=settings.RAG_DENSE_WEIGHT,
            sparse_weight=settings.RAG_BM25_WEIGHT,
        )
    else:
        fused = dense_results

    # 4. Neural Reranking if enabled
    final_results = cross_encoder.rerank(query=query, chunks=fused, top_k=k)
    return final_results
