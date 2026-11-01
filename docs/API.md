# REST API - Integration Guide

## Overview

API REST que expõe todas as funcionalidades do sistema RAG:
- Execução de queries
- Upload de arquivos
- Monitoramento e logs em tempo real

## Setup

### 1. Instalar dependências

```bash
pip install fastapi uvicorn python-multipart
```

### 2. Iniciar o servidor

```bash
# Desenvolvimento
python -m uvicorn src.api.main:app --reload --port 8000

# Ou usando:
python -m src.api.main
```

Servidor rodando em: `http://localhost:8000`

Documentação automática (Swagger UI): `http://localhost:8000/docs`

## Endpoints

### Health Check
```
GET /health
```
Verifica se a API está saudável.

**Response:**
```json
{
  "status": "healthy",
  "service": "RAG Customer Service",
  "version": "1.0.0"
}
```

---

### Execute Query
```
POST /query
```

Executa uma query no sistema RAG.

**Request:**
```json
{
  "query": "What are the financial metrics?"
}
```

**Response:**
```json
{
  "query": "What are the financial metrics?",
  "final_answer": "...",
  "latency_ms": 1250.5,
  "status": "success"
}
```

---

### Upload File
```
POST /upload
```

Faz upload de um arquivo para indexar.

**Request:**
```
Content-Type: multipart/form-data
file: <arquivo>
```

Tipos suportados: `.txt`, `.pdf`, `.html`, `.htm`

**Response:**
```json
{
  "filename": "documento.pdf",
  "status": "success",
  "message": "Arquivo 'documento.pdf' indexado com sucesso."
}
```

---

### Get LLM Calls Log
```
GET /logs/llm-calls?limit=20
```

Retorna as últimas chamadas LLM com detalhes completos.

**Query Parameters:**
- `limit` (int, default=100): Número máximo de logs

**Response:**
```json
{
  "logs": [
    {
      "timestamp": "2026-02-12T10:30:45.123456",
      "event_type": "llm_call",
      "provider": "openrouter",
      "model": "free",
      "agent": "classifier",
      "status": "success",
      "latency_ms": 1250.5,
      "prompt_length": 342,
      "response_length": 156,
      "prompt": "...",
      "response": "..."
    }
  ],
  "total": 42,
  "limit": 20
}
```

---

### Get Statistics
```
GET /logs/stats
```

Retorna estatísticas agregadas.

**Response:**
```json
{
  "total_llm_calls": 42,
  "avg_latency_ms": 950.34,
  "calls_by_agent": {
    "classifier": 10,
    "data_extractor": 10,
    "sentiment_analyst": 10,
    "question_answerer": 10,
    "synthesizer": 2
  }
}
```

---

### Get Routing Decisions
```
GET /logs/routing-decisions?limit=10
```

Retorna as últimas decisões de roteamento.

**Query Parameters:**
- `limit` (int, default=50): Número máximo de decisões

**Response:**
```json
{
  "decisions": [
    {
      "timestamp": "2026-02-12T10:30:45.123456",
      "event_type": "routing_decision",
      "user_query": "What are the financial metrics?",
      "agents_selected": ["data_extractor", "sentiment_analyst"],
      "num_agents": 2
    }
  ],
  "total": 5,
  "limit": 10
}
```

## Coleção Postman

### Variáveis de Ambiente

A coleção vem pré-configurada com:
- `base_url`: `http://localhost:8000`


### Exemplo de Uso

1. **Health Check**: Verifica se API está rodando
2. **Execute Query**: Envie uma pergunta
3. **Get Statistics**: Veja métricas de execução
4. **Get Routing Decisions**: Inspecione qual agente processou cada query

## Casos de Uso

### 1. Buscar informações financeiras
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the financial metrics for the last quarter?"}'
```

### 2. Fazer upload de novo arquivo
```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@documento.pdf"
```

### 3. Monitorar performance
```bash
curl http://localhost:8000/logs/stats
```

### 4. Debugar roteamento
```bash
curl http://localhost:8000/logs/routing-decisions?limit=5
```

## Docs Automática
FastAPI gera documentação interativa automática:

**Swagger UI (Recomendado)**:
```
http://localhost:8000/docs
```

**ReDoc**:
```
http://localhost:8000/redoc
```

