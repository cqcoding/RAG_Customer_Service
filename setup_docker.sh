#!/bin/bash

# Setup script para Docker Compose

echo "RAG Customer Service - Docker Setup"
echo ""

# Verificar se Docker está instalado
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Install at: https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Verificar se Docker Compose está instalado
if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose not found. Install at: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "Docker and Docker Compose found"
echo ""

# Criar arquivo .env se não existir
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "Edit .env and add your OPENROUTER_API_KEY"
    echo ""
fi

# Build das imagens
echo "Building Docker images..."
docker-compose build

echo ""
echo "Setup complete!"
echo ""
echo "To start the containers:"
echo "  docker-compose up -d"
echo ""
echo "To stop the containers:"
echo "  docker-compose down"
echo ""
echo "Services:"
echo "  - REST API: http://localhost:8000"
echo "  - Swagger Docs: http://localhost:8000/docs"
echo "  - Streamlit: http://localhost:8501"
echo ""
