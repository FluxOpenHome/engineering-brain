.PHONY: setup migrate api worker test lint web dev

setup:            ## install backend deps (uv) and web deps (npm)
	cd backend && uv sync --all-groups && uv pip install -e .
	cd web && npm install

migrate:
	cd backend && .venv/bin/eb migrate

api:
	cd backend && .venv/bin/eb serve --reload

worker:
	cd backend && .venv/bin/eb worker

test:
	cd backend && .venv/bin/ruff check src tests && .venv/bin/pytest -q

lint:
	cd backend && .venv/bin/ruff check src tests
	cd web && npm run lint

web:
	cd web && npm run dev
