import math
import hashlib
from typing import List, Optional
from app.core.config import settings
from app.core.logging import logger

_local_model_instance = None


class BaseEmbeddings:
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> List[float]:
        raise NotImplementedError


class FastFallbackEmbeddings(BaseEmbeddings):
    """
    Lightweight deterministic bag-of-words / character n-gram cosine embedding
    used when offline or if heavy deep learning libraries are downloading.
    Guarantees zero-friction instant startup anywhere.
    """
    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def _hash_embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dimension
        words = text.lower().split()
        if not words:
            return vec
        for word in words:
            # Python's built-in hash is randomized between processes, which made
            # fallback vectors impossible to query after a server restart.
            digest = hashlib.blake2b(word.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest, "big") % self.dimension
            vec[idx] += 1.0
        # Normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_embed(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._hash_embed(text)


class SentenceTransformerEmbeddings(BaseEmbeddings):
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self._model = None
        self._fallback = FastFallbackEmbeddings(dimension=settings.EMBEDDING_DIMENSION)

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading SentenceTransformer: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
            except Exception as e:
                logger.warning(f"Could not load SentenceTransformer '{self.model_name}' ({e}). Using FastFallbackEmbeddings.")
                self._model = False
        return self._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        if model:
            try:
                embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                return [list(map(float, vec)) for vec in embeddings]
            except Exception as e:
                logger.error(f"Embedding generation error: {e}")
        return self._fallback.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        model = self._get_model()
        if model:
            try:
                embedding = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
                return list(map(float, embedding))
            except Exception as e:
                logger.error(f"Query embedding error: {e}")
        return self._fallback.embed_query(text)


class GeminiEmbeddings(BaseEmbeddings):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.fallback = SentenceTransformerEmbeddings()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not self.api_key:
            return self.fallback.embed_documents(texts)
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            results = []
            for t in texts:
                res = genai.embed_content(
                    model="models/text-embedding-004",
                    content=t,
                    task_type="retrieval_document"
                )
                results.append(res["embedding"])
            return results
        except Exception as e:
            logger.warning(f"Gemini embedding error ({e}), falling back to local embeddings.")
            return self.fallback.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        if not self.api_key:
            return self.fallback.embed_query(text)
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            res = genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="retrieval_query"
            )
            return res["embedding"]
        except Exception as e:
            logger.warning(f"Gemini query embedding error: {e}")
            return self.fallback.embed_query(text)


class OpenAIEmbeddings(BaseEmbeddings):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.fallback = SentenceTransformerEmbeddings()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not self.api_key:
            return self.fallback.embed_documents(texts)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
            return [d.embedding for d in resp.data]
        except Exception as e:
            logger.warning(f"OpenAI embedding error ({e}), falling back.")
            return self.fallback.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        if not self.api_key:
            return self.fallback.embed_query(text)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            resp = client.embeddings.create(model="text-embedding-3-small", input=text)
            return resp.data[0].embedding
        except Exception as e:
            logger.warning(f"OpenAI query embedding error: {e}")
            return self.fallback.embed_query(text)


def get_embedding_provider(provider_name: Optional[str] = None, api_key: Optional[str] = None) -> BaseEmbeddings:
    name = (provider_name or settings.EMBEDDING_PROVIDER).lower()
    if name == "gemini":
        return GeminiEmbeddings(api_key=api_key)
    elif name == "openai":
        return OpenAIEmbeddings(api_key=api_key)
    return SentenceTransformerEmbeddings(model_name=settings.EMBEDDING_MODEL_NAME)
