import requests
import json
import time
from requests.exceptions import HTTPError
from src.config import get_settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMUnavailableError(Exception):
    """Raised when every model in the fallback chain failed."""


class OpenRouterLLM:
    DEFAULT_MODEL = "google/gemini-3-flash-preview"
    FALLBACK_MODELS = [
        "minimax/minimax-m2.1",
        "deepseek/deepseek-v3.2",
        "upstage/solar-pro-3:free",
        "google/gemini-2.5-flash-lite"
    ]

    def __init__(self, model=None, temperature=0, enable_fallback=True):
        self.settings = get_settings()
        self.model = model or self.DEFAULT_MODEL
        self.temperature = temperature
        self.enable_fallback = enable_fallback

    def invoke(self, messages, max_retries: int = 3, initial_delay: int = 2):
        """
        Faz requisição à API com retry automático em caso de rate limit (429).
        Se enable_fallback=True, tenta outros modelos em caso de erro.
        """
        # Try default model first, then fallbacks if enabled
        models_to_try = [self.model] + (self.FALLBACK_MODELS if self.enable_fallback else [])
        
        for model in models_to_try:
            retry_delay = initial_delay
            
            for attempt in range(max_retries):
                try:
                    response = requests.post(
                        url=OPENROUTER_URL,
                        headers={
                            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "temperature": self.temperature,
                            "messages": messages,
                        },
                        timeout=60,
                    )
                    response.raise_for_status()
                    
                    # Check for empty response
                    if not response.text:
                        print(f"Resposta vazia de {model}")
                        break
                    
                    data = response.json()
                    
                    return {
                        "content": data["choices"][0]["message"]["content"],
                        "model_used": data.get("model", model),
                    }
                    
                except HTTPError as e:
                    if e.response.status_code == 429:
                        if attempt < max_retries - 1:
                            print(f"Rate limit (429) com {model}. Tentativa {attempt + 1}/{max_retries}. Aguardando {retry_delay}s...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                        else:
                            print(f"Limite de tentativas atingido com {model}.")
                            break
                    else:
                        print(f"Erro HTTP {e.response.status_code} com {model}: {e.response.text[:200]}")
                        break
                
                except json.JSONDecodeError as e:
                    print(f"Erro JSON com {model}: {e}. Response: {response.text[:200]}")
                    break
                
                except requests.exceptions.Timeout:
                    if attempt < max_retries - 1:
                        print(f"Timeout com {model}. Tentativa {attempt + 1}/{max_retries}. Aguardando {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        print(f"Timeout após {max_retries} tentativas com {model}.")
                        break
                
                except Exception as e:
                    print(f"Erro inesperado com {model}: {type(e).__name__}: {e}")
                    break
        
        raise LLMUnavailableError(f"Todos os modelos falharam após {len(models_to_try)} tentativas: {models_to_try}")