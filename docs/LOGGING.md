# Sistema de Logging e Tracing

## Funcionalidades

1. **Todas as chamadas LLM**: prompt, response, latência, tokens
2. **Execução de agentes**: input, output, tempo de execução, status
3. **Decisões de roteamento**: qual query foi para quais agentes
4. **Síntese final**: agregação de resultados

## Arquitetura

### `src/utils/logger.py`
- **StructuredLogger**: Classe central para logging estruturado
- Escreve em dois formatos:
  - **llm_calls.jsonl**: Logs JSON estruturados (fácil parsing)
  - **trace.log**: Logs em texto legível (debugging rápido)

### `src/utils/tracing.py`
- **Tracer**: Context manager para timing automático
- **@trace_llm_call**: Decorator para envolver chamadas LLM

### `src/agents/orchestrator.py`
- Integrado logging em:
  - `classify_query`: Registra decisão de roteamento + chamada LLM
  - `data_extractor`, `sentiment_analyst`, `question_answerer`: Registram execução de agentes
  - `synthesize_results`: Registra síntese final + chamada LLM

## Logs Gerados

### llm_calls.jsonl (JSON Lines)
Cada linha é um JSON com estrutura:
```json
{
  "timestamp": "2026-02-12T10:30:45.123456",
  "event_type": "llm_call",
  "provider": "openrouter",
  "model": "free",
  "agent": "classifier",
  "status": "success",
  "latency_ms": 1250.5,
  "tokens": {},
  "prompt_length": 342,
  "response_length": 156,
  "prompt": "...",
  "response": "..."
}
```

### trace.log (Texto legível)
```
2026-02-12 10:30:45,123 - INFO - {"timestamp": "...", "event_type": "agent_execution", ...}
```

## Usando o Viewer

Script interativo para inspecionar logs:

```bash
python src/utils/view_logs.py
```

Opções:
1. **Visualizar logs de chamadas LLM**: Todas as chamadas LLM com provider/model/latência
2. **Visualizar execução de agentes**: Execução de cada agente com tempo
3. **Visualizar decisões de roteamento**: Quais agentes foram chamados para cada query
4. **Visualizar estatísticas**: Contagem e latência média por agente
5. **Visualizar todos os logs e estatísticas**: Exibe tudo

## Exemplo de Saída

```
================================================================================
LOGS DE CHAMADAS LLM
================================================================================

[2026-02-12T10:30:45.123456] openrouter - free
  Agent: classifier
  Status: success
  Latência: 1250.5ms
  Prompt (primeiros chars): Analyze this query and determine which agents...
  Response (primeiros chars): {"classifications": [{"source": "data_extractor",...

[2026-02-12T10:30:47.456789] openrouter - free
  Agent: data_extractor
  Status: success
  Latência: 850.2ms
  ...

================================================================================
DECISÕES DE ROTEAMENTO
================================================================================

[2026-02-12T10:30:45.123456]
  Query: What are the financial metrics?
  Agentes selecionados: data_extractor, sentiment_analyst
  Total de agentes: 2

================================================================================
ESTATÍSTICAS
================================================================================

Total de chamadas LLM: 5
Latência média: 950.34ms

Chamadas por agente:
  classifier: 1
  data_extractor: 1
  sentiment_analyst: 1
  question_answerer: 1
  synthesizer: 1
```

## Estrutura de Diretório

```
logs/
├── llm_calls.jsonl    # Logs JSON estruturados
└── trace.log          # Logs em texto
```

Criados automaticamente na primeira execução.
