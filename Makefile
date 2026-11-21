.PHONY: help install run-backend run-frontend dev test lint docker-up docker-down clean

help:
	@echo "Available commands:"
	@echo "  make install        Install backend and frontend dependencies"
	@echo "  make run-backend    Run FastAPI development server"
	@echo "  make run-frontend   Run Next.js development server"
	@echo "  make dev            Run both backend and frontend concurrently"
	@echo "  make test           Run backend pytest test suite"
	@echo "  make lint           Run backend ruff/flake8 and frontend linting"
	@echo "  make docker-up      Start all services with Docker Compose"
	@echo "  make docker-down    Stop Docker Compose services"
	@echo "  make clean          Clean cache, build artifacts, and temp files"

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

run-backend:
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

run-frontend:
	cd frontend && npm run dev

dev:
	@echo "Starting backend and frontend..."
	# On Windows use separate shells or run via docker-compose

test:
	cd backend && pytest tests/ -v

lint:
	ruff check backend/app backend/tests
	cd frontend && npm run lint

test-frontend:
	cd frontend && npm test && npm run typecheck

docker-up:
	docker compose -f infra/docker-compose.yml up -d --build

docker-down:
	docker compose -f infra/docker-compose.yml down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".next" -exec rm -rf {} +
