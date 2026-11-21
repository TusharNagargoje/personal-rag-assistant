# Architecture

```mermaid
flowchart LR
  Browser[Next.js client] -->|Bearer token / SSE| API[FastAPI]
  API --> Auth[JWT authentication]
  API --> DB[(PostgreSQL or SQLite)]
  API --> Jobs[FastAPI background ingestion]
  Jobs --> Parse[Format parsers and chunker]
  Jobs --> Embed[Local or provider embeddings]
  Embed --> Qdrant[(Qdrant)]
  API --> Retrieve[Dense + BM25 + RRF retrieval]
  Retrieve --> Qdrant
  Retrieve --> LLM[Gemini / Groq / OpenAI / Ollama]
  LLM -->|grounded stream and source metadata| Browser
```

The API stores ownership, chat history, and chunk metadata in SQL. Qdrant stores vectors and their source payloads. BM25 is rebuilt from SQL-backed chunks when documents are ingested. Ingestion uses FastAPI background tasks, so a separate worker queue is not required for the local setup. The local Qdrant path is persistent; the in-memory fallback is a degraded mode and is not suitable for multi-process production use.
