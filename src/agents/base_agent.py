import re


# Helpers shared by the agents
class BaseAgent:
    @staticmethod
    def clean_json(text: str) -> str:
        """Strip an optional ```json ... ``` fence around a model's JSON reply."""
        text = text.strip()
        fenced_match = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text, re.IGNORECASE)
        if fenced_match:
            return fenced_match.group(1).strip()
        return text
