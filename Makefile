.PHONY: install dev test lint format serve docker-up docker-down eval clean

install:
	pip install -e ".[dev]"

dev: install
	cp -n .env.example .env 2>/dev/null || true

test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ -v --cov=synapse --cov-report=term-missing

lint:
	ruff check src/ tests/

format:
	ruff check src/ tests/ --fix
	ruff format src/ tests/

serve:
	uvicorn synapse.gateway.app:app --host 127.0.0.1 --port 8000 --reload

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

eval:
	synapse eval

load-test:
	python scripts/load_test.py -n 20 -c 5

notes:
	python scripts/generate_notes_pdf.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
