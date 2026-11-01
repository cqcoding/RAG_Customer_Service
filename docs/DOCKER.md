# Docker & Docker Compose Setup Guide

### 1. Preparar Variáveis de Ambiente

```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite .env e adicione sua chave OpenRouter
# OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxx
```

Obtenha chave gratuita em: https://openrouter.ai

### 2. Setup Inicial

```bash
bash setup_docker.sh
```

Ou manual:

```bash
# Build das imagens
docker-compose build

# Iniciar containers
docker-compose up -d
```

### 3. Verificar Status

```bash
docker-compose ps
```

Você deve ver 3 containers rodando:
- **api** (porta 8000)
- **frontend** (porta 8501)
- **chroma** (porta 8003)

### 4.Serviços

| Serviço | URL | Descrição |
|---------|-----|-----------|
| **API REST** | http://localhost:8000 | Base da API |
| **Swagger Docs** | http://localhost:8000/docs | Documentação interativa |
| **ReDoc** | http://localhost:8000/redoc | Documentação alternativa |
| **Streamlit** | http://localhost:8501 | Interface web |

---

## Estrutura de Volumes

Dados persistem em:
- `./data` - Arquivos upload
- `./chroma_db` - Banco vetorial
- `./logs` - Logs da aplicação

Esses diretórios são criados automaticamente.

---

## Comandos Úteis

### Iniciar containers
```bash
docker-compose up -d
```

### Parar containers
```bash
docker-compose down
```

### Ver logs da API
```bash
docker-compose logs -f api
```

### Ver logs do Frontend
```bash
docker-compose logs -f frontend
```

### Executar comando dentro do container
```bash
docker-compose exec api bash
```

### Rebuild após mudar código
```bash
docker-compose up -d --build
```

### Deletar tudo (volumes, networks, etc)
```bash
docker-compose down -v
```
