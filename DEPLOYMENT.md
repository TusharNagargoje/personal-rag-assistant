# Deployment

## Local Docker Compose

1. Copy `.env.example` to `.env` and set a unique `SECRET_KEY` (32+ random characters).
2. Set `GEMINI_API_KEY` to a Gemini API key if you want generated answers. The application can still return retrieved source excerpts without a key.
3. Run `docker compose -f infra/docker-compose.yml up --build`.
4. Open `http://localhost:3000`; API health is at `http://localhost:8000/health`.

## Render API and Vercel web

1. Push this repository to GitHub and create a Render Blueprint from `render.yaml`. The blueprint provisions the API and PostgreSQL. Confirm the current plan and persistence limits in Render before production use.
2. Configure the API environment: a generated `SECRET_KEY`, `ENVIRONMENT=production`, `DATABASE_URL`, `GEMINI_API_KEY` (optional), `QDRANT_URL`, `QDRANT_API_KEY`, and `CORS_ORIGINS` containing the exact Vercel origin.
3. Create a Vercel project from the repository root. `vercel.json` installs and builds the Next.js app from `frontend/`.
4. Set `NEXT_PUBLIC_API_URL` to the deployed API origin (for example `https://your-api.onrender.com`) and deploy.
5. Verify `/health`, register an account, upload `data/sample/knowledge_base.md`, wait for `indexed`, then ask what RAG does and inspect the citation.

Google OAuth is not currently wired. Email/password is the supported login flow. Qdrant Cloud is recommended for durable vector storage; the local filesystem path is for Docker/self-hosting. No live URLs are published because this repository has not been connected to deployment accounts.

## Railway

`railway.json` gives a start command for the API. Create a PostgreSQL and Qdrant service, set the same environment variables listed above, and configure the service root/build context so Python dependencies install from `backend/requirements.txt`. Deploy the frontend separately to Vercel.
