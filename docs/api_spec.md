# API overview

Interactive OpenAPI documentation is available at `/docs` in development.

| Route | Purpose |
|---|---|
| `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `GET /api/v1/auth/me` | Email/password account and JWT operations |
| `GET/POST /api/v1/collections/` | List or create owned workspaces |
| `POST /api/v1/documents/upload`, `/url`, `/youtube` | Start ingestion jobs |
| `GET /api/v1/documents/`, `GET /api/v1/documents/{id}`, `DELETE /api/v1/documents/{id}` | List, inspect, and remove owned documents |
| `GET/POST /api/v1/chat/sessions` | List and create conversations |
| `GET/PATCH/DELETE /api/v1/chat/sessions/{id}` | Read, rename/pin, or delete a conversation |
| `POST /api/v1/chat/sessions/{id}/messages` | Ask a grounded question; response is SSE by default |
| `POST /api/v1/feedback` | Save answer rating and optional comment |
| `GET /api/v1/analytics` | Basic per-user usage counts |

All application routes except registration/login and health endpoints require `Authorization: Bearer <access_token>`. The chat stream emits JSON `token`, `done` (including citations), and `error` events, followed by `[DONE]`.
