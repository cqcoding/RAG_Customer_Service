#!/bin/bash

# Script para iniciar a API REST do sistema RAG

echo "Starting Customer Service API..."
echo ""
echo "Base URL: http://localhost:8000"
echo "Swagger Docs: http://localhost:8000/docs"
echo "ReDoc: http://localhost:8000/redoc"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

python -m uvicorn src.api.main:app --reload --port 8000
