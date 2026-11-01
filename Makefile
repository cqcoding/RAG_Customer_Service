.PHONY: help setup install test clean run verify db-up load-db

help:
	@echo "RAG_Customer_Service - RAG System"
	@echo ""
	@echo "Available commands:"
	@echo "  make setup      - Create virtual environment and install dependencies"
	@echo "  make install    - Install dependencies in existing venv"
	@echo "  make test       - Run tests"
	@echo "  make verify     - Verify setup"
	@echo "  make db-up      - Start PostgreSQL (docker compose)"
	@echo "  make load-db    - Load CSVs into PostgreSQL and the PDF into Chroma"
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

verify:
	@echo "Verifying setup..."
	python verify_setup.py

db-up:
	docker compose up -d postgres

load-db:
	./venv/bin/python -m src.utils.create_sql_db
	./venv/bin/python -m src.utils.create_db

clean:
	@echo "Cleaning up..."
	rm -rf venv
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleanup complete!"
