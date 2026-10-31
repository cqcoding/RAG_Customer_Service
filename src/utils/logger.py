import logging
import json
import time
import traceback
from datetime import datetime
from typing import Optional, Any, Dict
from pathlib import Path

LOG_DIR = Path("./logs")
LOG_DIR.mkdir(exist_ok=True)

class StructuredLogger:
    """Logging estruturado para LLM calls e tracing."""
    
    def __init__(self, name: str = "rag_system"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # File handler - JSON estruturado
        json_handler = logging.FileHandler(LOG_DIR / "llm_calls.jsonl")
        json_handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(json_handler)
        
        # File handler - texto legível
        text_handler = logging.FileHandler(LOG_DIR / "trace.log")
        text_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(text_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(console_handler)
    
    def log_llm_call(
        self,
        provider: str,
        model: str,
        prompt: str,
        response: str,
        latency_ms: float,
        tokens_used: Optional[Dict[str, int]] = None,
        agent: Optional[str] = None,
        status: str = "success",
        error: Optional[str] = None
    ) -> None:
        """Loga uma chamada LLM com estrutura JSON."""
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "llm_call",
            "provider": provider,
            "model": model,
            "agent": agent or "orchestrator",
            "status": status,
            "latency_ms": round(latency_ms, 2),
            "tokens": tokens_used or {},
            "prompt_length": len(prompt),
            "response_length": len(response),
            "prompt": prompt[:500],  # Primeiros 500 chars
            "response": response[:500],  # Primeiros 500 chars
            "error": error  # Stack trace em caso de erro
        }
        
        self.logger.info(json.dumps(log_entry, ensure_ascii=False))
    
    def log_agent_execution(
        self,
        agent_name: str,
        input_query: str,
        output: str,
        latency_ms: float,
        status: str = "success",
        error: Optional[str] = None
    ) -> None:
        """Loga execução de um agente."""
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "agent_execution",
            "agent": agent_name,
            "status": status,
            "latency_ms": round(latency_ms, 2),
            "input": input_query[:200],
            "output": output[:200],
            "error": error
        }
        
        self.logger.info(json.dumps(log_entry, ensure_ascii=False))
    
    def log_routing_decision(
        self,
        query: str,
        classifications: list
    ) -> None:
        """Loga decisão de roteamento do classificador."""
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "routing_decision",
            "user_query": query[:200],
            "agents_selected": [c.get("source") for c in classifications],
            "num_agents": len(classifications)
        }
        
        self.logger.info(json.dumps(log_entry, ensure_ascii=False))
    
    def log_synthesis(
        self,
        query: str,
        num_results: int,
        final_answer: str,
        latency_ms: float
    ) -> None:
        """Loga síntese final."""
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "synthesis",
            "user_query": query[:200],
            "results_aggregated": num_results,
            "final_answer": final_answer[:300],
            "latency_ms": round(latency_ms, 2)
        }
        
        self.logger.info(json.dumps(log_entry, ensure_ascii=False))
    
    def log_error(
        self,
        error_type: str,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Loga erro com stack trace completo."""
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "error",
            "error_type": error_type,
            "message": message,
            "stack_trace": traceback.format_exc(),
            "context": context or {}
        }
        
        self.logger.error(json.dumps(log_entry, ensure_ascii=False))


# Instância global
logger = StructuredLogger()
