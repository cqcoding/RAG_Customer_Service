from src.utils.retriever import get_retriever
from src.models.model_llm import OpenRouterLLM
import re


# Functions common to all agents
class BaseAgent:
    def __init__(self, model_name: str):
        self.llm = OpenRouterLLM(
            temperature=0,
            model=model_name
        )
        self.retriever = get_retriever()

    @staticmethod
    def clean_json(text: str) -> str:
        """Strip an optional ```json ... ``` fence around a model's JSON reply."""
        text = text.strip()
        fenced_match = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text, re.IGNORECASE)
        if fenced_match:
            return fenced_match.group(1).strip()
        return text
