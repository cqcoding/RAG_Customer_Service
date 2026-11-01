.PHONY: help setup install test clean run db-up load-db docker-up docker-down docker-logs

help:
	@echo "RAG_Customer_Service - RAG System"
	@echo ""
	@echo "Available commands:"
	@echo "  make setup      - Create virtual environment and install dependencies"
	@echo "  make install    - Install dependencies in existing venv"
	@echo "  make test       - Run tests"
	@echo "  make db-up      - Start PostgreSQL (docker compose)"
	@echo "  make load-db    - Load CSVs into PostgreSQL and the PDF into Chroma"
	@echo "  make docker-up  - Build and run everything in Docker (chat on :8501, API on :8000)"
	@echo "  make docker-down - Stop the Docker stack (data volumes are kept)"
	@echo "  make docker-logs - Follow the Docker stack's logs"
	@echo "  make clean      - Remove virtual environment and cache files"
	@echo "  make help       - Show this help message"

setup:
	@echo "Creating virtual environment..."
	python3 -m venv venv
	@echo "Installing dependencies..."
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	@echo "Setup complete! Activate with: source venv/bin/activate"

install:
	@echo "Installing dependencies..."
	pip install --upgrade pip
	pip install -r requirements.txt
	@echo "Installation complete!"

test:
	@echo "Running tests..."
	pytest tests/ -v

db-up:
	docker compose up -d postgres

load-db:
	./venv/bin/python -m src.utils.create_sql_db
	./venv/bin/python -m src.utils.create_db

docker-up:
	docker compose up -d --build
	@echo "Chat: http://localhost:$${FRONTEND_PORT:-8501}  |  API docs: http://localhost:$${API_PORT:-8000}/docs"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

clean:
	@echo "Cleaning up..."
	rm -rf venv
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleanup complete!"
