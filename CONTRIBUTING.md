# Contributing

Thanks for helping improve Personal RAG Assistant.

1. Fork the repository and create a focused branch from `main`.
2. Install Python 3.11 and Node.js 20, then follow the quick start in the README.
3. Add or update tests for behavior changes. Keep documents and queries scoped to the authenticated owner.
4. Run `pytest backend/tests`, `ruff check backend/app backend/tests`, `npm run typecheck`, and `npm run build` from `frontend`.
5. Use Conventional Commit subjects such as `feat: add document filters` or `fix: scope retrieval by owner`.
6. Open a pull request with a summary, test results, and screenshots for user interface changes.

Never commit `.env` files, API keys, personal documents, database files, or generated vector data. Report security issues privately to the repository owner rather than filing a public issue with exploit details.
