from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Literal
import json
import time
import traceback

from src.agents.orchestrator import answer
from src.utils.logger import logger

app = FastAPI(
    title="RAG Customer Service API",
    description="REST API para RAG System com logging estruturado",
    version="1.0.0"
)

# ==================== Request/Response Models ====================

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class QueryRequest(BaseModel):
    query: str
    # Previous turns (oldest first) so follow-up questions keep their context.
    history: list[ChatTurn] = Field(default_factory=list)

class QueryResponse(BaseModel):
    query: str
    final_answer: str
    latency_ms: float
    status: str

class UploadResponse(BaseModel):
    filename: str
    status: str
    message: str

class LogEntry(BaseModel):
    timestamp: str
    event_type: str
    agent: str
    latency_ms: float

class StatsResponse(BaseModel):
    total_llm_calls: int
    avg_latency_ms: float
    calls_by_agent: dict

# ==================== Endpoints ====================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "RAG Customer Service",
        "version": "1.0.0"
    }

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """
    Executa uma query no sistema RAG.
    
    - **query**: Pergunta do usuário
    
    Retorna:
    - **final_answer**: Resposta sintetizada
    - **latency_ms**: Tempo total de execução
    """
    start_time = time.time()
    
    try:
        final_answer = answer(
            request.query,
            history=[t.model_dump() for t in request.history],
        )
        
        latency_ms = (time.time() - start_time) * 1000
        
        return QueryResponse(
            query=request.query,
            final_answer=final_answer,
            latency_ms=latency_ms,
            status="success"
        )
    
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        error_details = traceback.format_exc()
        
        # Log error com stack trace
        logger.log_error(
            error_type=type(e).__name__,
            message=str(e),
            context={
                "query": request.query,
                "latency_ms": latency_ms
            }
        )
        
        # Log LLM call como erro
        logger.log_llm_call(
            provider="orchestrator",
            model="workflow",
            prompt=request.query,
            response="",
            latency_ms=latency_ms,
            status="error",
            error=error_details[:200]  # Primeiros 200 chars do stack trace
        )
        
        raise HTTPException(
            status_code=500,
            detail=f"{type(e).__name__}: {str(e)}"
        )


@app.get("/logs/llm-calls")
async def get_llm_logs(limit: int = 100):
    """
    Retorna logs das últimas chamadas LLM.
    
    - **limit**: Número máximo de logs (default: 100)
    """
    log_file = Path("./logs/llm_calls.jsonl")
    
    if not log_file.exists():
        return {"logs": [], "total": 0}
    
    logs = []
    with open(log_file) as f:
        for line in f:
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    
    # Retorna últimos N logs
    return {
        "logs": logs[-limit:],
        "total": len(logs),
        "limit": limit
    }

@app.get("/logs/stats", response_model=StatsResponse)
async def get_stats():
    """
    Retorna estatísticas agregadas dos logs.
    """
    log_file = Path("./logs/llm_calls.jsonl")
    
    if not log_file.exists():
        return StatsResponse(
            total_llm_calls=0,
            avg_latency_ms=0.0,
            calls_by_agent={}
        )
    
    total_calls = 0
    total_latency = 0.0
    calls_by_agent = {}
    
    with open(log_file) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("event_type") == "llm_call":
                    total_calls += 1
                    total_latency += entry.get("latency_ms", 0)
                    agent = entry.get("agent", "unknown")
                    calls_by_agent[agent] = calls_by_agent.get(agent, 0) + 1
            except json.JSONDecodeError:
                continue
    
    avg_latency = total_latency / total_calls if total_calls > 0 else 0.0
    
    return StatsResponse(
        total_llm_calls=total_calls,
        avg_latency_ms=round(avg_latency, 2),
        calls_by_agent=calls_by_agent
    )

@app.get("/logs/routing-decisions")
async def get_routing_logs(limit: int = 50):
    """
    Retorna últimas decisões de roteamento.
    
    - **limit**: Número máximo de registros
    """
    log_file = Path("./logs/llm_calls.jsonl")
    
    if not log_file.exists():
        return {"decisions": [], "total": 0}
    
    decisions = []
    with open(log_file) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("event_type") == "routing_decision":
                    decisions.append(entry)
            except json.JSONDecodeError:
                continue
    
    return {
        "decisions": decisions[-limit:],
        "total": len(decisions),
        "limit": limit
    }

# ==================== Error Handlers ====================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handler global para exceções não tratadas."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor", "error": str(exc)}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
