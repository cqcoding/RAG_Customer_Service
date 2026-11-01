import time
from typing import Callable, Any, Optional
from functools import wraps
from src.utils.logger import logger


class Tracer:
    """Context manager e decorator para tracing de execução."""
    
    def __init__(self, operation_name: str, agent_name: Optional[str] = None):
        self.operation_name = operation_name
        self.agent_name = agent_name
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        latency_ms = (self.end_time - self.start_time) * 1000
        
        status = "error" if exc_type else "success"
        error_msg = f"{exc_type.__name__}: {exc_val}" if exc_type else None
        
        if self.agent_name:
            logger.log_agent_execution(
                agent_name=self.agent_name,
                input_query=self.operation_name,
                output="",
                latency_ms=latency_ms,
                status=status,
                error=error_msg
            )
        
        return False  # Re-raise exception se houver


def trace_llm_call(func: Callable) -> Callable:
    """Decorator para traçar chamadas LLM com timing e logging."""
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            latency_ms = (time.time() - start_time) * 1000
            
            # Extrai provider e model do contexto
            provider = kwargs.get("provider", "openrouter")
            model = kwargs.get("model", "unknown")
            
            logger.log_llm_call(
                provider=provider,
                model=model,
                prompt=str(args[0]) if args else kwargs.get("prompt", ""),
                response=result.get("content", "") if isinstance(result, dict) else str(result),
                latency_ms=latency_ms,
                status="success"
            )
            
            return result
        
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.log_llm_call(
                provider=kwargs.get("provider", "openrouter"),
                model=kwargs.get("model", "unknown"),
                prompt=str(args[0]) if args else "",
                response="",
                latency_ms=latency_ms,
                status="error"
            )
            raise
    
    return wrapper
