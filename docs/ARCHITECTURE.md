# Arquitetura Geral

## Stack Tecnológico
- **Orquestração**: LangGraph (StateGraph com grafo compilado)
- **Embeddings**: FastEmbed (BAAI/bge-base-en-v1.5)
- **Vector Database**: ChromaDB com persistência local
- **LLM**: OpenRouter (modelos gratuitos - DeepSeek, Llama)
- **Frontend**: Streamlit
- **Backend**: Python puro + LangChain/LangGraph

---

## Vector Database e Persistência

### ChromaDB
- Escolhi por ser leve, com suporte a persistência local sem dependências externas
- Persiste em `./chroma_db` com coleção única `my_collection`
- Suporta adição incremental de documentos sem rebuild completo
- Metadados enriched de cada documento para melhor rastreabilidade

---

## Modelo de Embedding

### FastEmbed - BAAI/bge-base-en-v1.5
- Modelo open-source, rápido e eficiente em CPU
- Bom balanço entre precisão e performance
- Escolhido por oferecer ótimo custo-benefício sem dependência de APIs externas

---

## Estratégia de Chunking

### Hybrid Chunking
Estratégia mista: **sentence splitter + recursive character splitter**

**Decisão**: Testei chunking semântico puro, mas falhou com a variedade de estilos (PDFs técnicos + planilhas + textos narrativos). A abordagem híbrida ofereceu melhor equilíbrio.

**Pipeline**:
1. Divide por sentença (NLTK)
2. Faz merge recursivo em chunks de 600 chars com overlap de 80 chars
3. Resultado: chunks coesos com contexto suficiente para relatórios financeiros técnicos

**Vantagens**:
- Preserva semântica de frases completas
- Overlap garante contexto entre chunks
- Mais estável com variação de formatos

---

## Modelos LLM e Provider

### OpenRouter - versão inicial
- **Razão**: Modelos gratuitos de qualidade (DeepSeek, Llama, Solar) sem custo
- **Temperatura**: 0 (reduz alucinações e randomicidade, crítico para análise financeira)
- **Integração**: Cliente custom (`src/models/model_llm.py`) que wrappeia HTTP requests direto, oferece flexibilidade total
- **Problemas** : Em horários de pico, apresentava muitos problemas com Too Many CLient Requests (429).

## Gemini 3 Flash Preview
- **Razão**: Modelo com capacidade de raciocínio, 2 providers, latência razoável, caching, support tools, alto valor de quantidade de tokens
- **Custo**: Input $0.50 / M tokens Output $3 / M tokens
-**Comparativo**: ChatGPT-4o possuía tamanho de contexto 10x menor, sem capacidade de raciocínio, 10x menos tokens totais e 10x mais caro.

### Fallbacks Configurados

Sistema de fallback automático com 4 modelos em cascata (ver `FALLBACK_MODELS` em [`model_llm.py`](../src/models/model_llm.py)):

1. **minimax/minimax-m2.1**
   - Modelo de alta performance
   - Boa capacidade de raciocínio e contexto longo
   - Fallback primário por estabilidade e qualidade de resposta
   - Custo: Input $0.30 / M tokens Output $1.20 / M token

2. **deepseek/deepseek-v3.2**
   - Especializado em tarefas técnicas e análise
   - Excelente para extração estruturada de dados financeiros
   - Baixa latência e boa taxa de sucesso
   - Custo: Input $0.27 / M tokens Output $1 / M tokens

3. **upstage/solar-pro-3:free**
   - Modelo gratuito com boa capacidade multilingue
   - Robusto para análise de sentimento
   - Fallback confiável para horários de pico

4. **google/gemini-2.5-flash-lite**
   - Versão lite do Gemini com menor latência
   - Garante disponibilidade mesmo com rate limits
   - Último recurso antes de falha completa
   - Custo: Input $0.10 / M tokens Output $0.40 / M tokens

**Estratégia de retry**: Cada modelo tem 3 tentativas com backoff exponencial (2s → 4s → 8s) antes de passar para o próximo fallback.


---

## Orquestração de Agentes - LangGraph

### Arquitetura do Workflow

```
START → classify_query → route_to_agents → [data_extractor | sentiment_analyst | question_answerer] → synthesize_results → END
```
![ArchitectureImage](../architecture.png)

### Componentes

#### 1. **State Management**
```python
class RouterState(TypedDict):
    query: str                                      
    classifications: list[Classification]          
    results: Annotated[list[AgentOutput], operator.add]  
    final_answer: str                              
```


### Por que LangGraph?
- **State management explícito**: Fácil rastrear fluxo de dados
- **Paralelização**: Fan-out/fan-in sem boilerplate
- **Resilência**: Reducer automático para agregar outputs de múltiplas fontes

---

## Extração de Metadados

Cada arquivo é enriquecido com metadados antes de chunking:
- **HTML**: title, description, company info
- **PDF**: author, creation date, page numbers
- **TXT**: detecta padrões (data, valores monetários)

Metadados ficam anexados a cada chunk para melhor contexto em retrieval.

---

## Interface e UI

### Streamlit
- **Escolha**: Framework rápido para prototipar RAG sem frontend complexo
- **Funcionalidades**:
  - Input de pergunta em texto natural
  - Upload incremental de novos arquivos (.txt, .pdf, .html)
  - Indexação automática via `add_file_to_chroma_db()` (sem rebuild)
  - Spinner + feedback durante processing

### Fluxo User-Facing
1. User digita pergunta → enviada para `workflow.invoke()`
2. Orquestrador roteia, executa agentes em paralelo, sintetiza
3. Resultado exibido em tempo real
4. User pode fazer upload de novo arquivo → salvo em `/data` e indexado incrementalmente

---

## Fluxo de Dados - End-to-End

```
[User Input] 
    ↓
[Streamlit Interface] 
    ↓
[LangGraph Orchestrator]
    ├→ [Classify Query Node]
    │    └→ OpenRouter LLM (JSON extraction)
    ├→ [Parallel Agent Execution]
    │    ├→ [Data Extractor] → Chroma + retriever + extractor_agent
    │    ├→ [Sentiment Analyst] → Chroma + retriever + sentiment_agent
    │    └→ [QA Agent] → Chroma + retriever + qa_agent
    └→ [Synthesis Node]
        └→ OpenRouter LLM (agregação + resposta natural)
    ↓
[Final Answer Display]
```

### Incrementalidade
- `add_file_to_chroma_db()`: Append seguro para novos arquivos

---

## Referências

https://www.youtube.com/watch?v=Zx_nHeBxZjw
https://openrouter.ai/
https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant
https://docs.langchain.com/oss/python/langgraph/workflows-agents
https://docs.streamlit.io/develop/api-reference
https://docs.langchain.com/oss/python/langgraph/overview
https://www.youtube.com/watch?v=7MrAr3j5v58
https://docs.langchain.com/oss/python/integrations/splitters
https://docs.langchain.com/oss/python/integrations/vectorstores
https://docs.langchain.com/oss/python/langchain/rag
https://medium.com/@nay1228/embedding-models-a-comprehensive-guide-for-beginners-to-experts-0cfc11d449f1
https://openrouter.ai/docs/guides/routing/routers/free-models-router
https://openrouter.ai/docs/guides/routing/model-fallbacks
https://docs.pydantic.dev/latest/
https://fastapi.tiangolo.com/
