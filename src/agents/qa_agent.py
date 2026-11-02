"""
Policy agent: retrieves the store policy excerpts relevant to a question.

It returns the excerpts themselves, not an LLM-written answer, like the SQL
agent returns rows: the orchestrator's synthesizer writes the final reply from
the raw sources. That saves one LLM call per policy question and avoids
summarizing a summary.
"""
import json
from functools import lru_cache
from pathlib import Path

from src.utils.retriever import get_retriever


@lru_cache(maxsize=1)
def _retriever():
    # Created on first use: loading the embedding model is slow, and importing
    # this module (e.g. in tests or the API) shouldn't pay for it.
    return get_retriever()


def run_policy_qa(query: str) -> dict:
    """
    Return {"query", "status", "excerpts": [{"source", "page", "text"}], "sources"}.
    status is "success", "not_found" (nothing retrieved) or "error".
    """
    try:
        docs = _retriever().invoke(query)
    except Exception as e:
        return {"query": query, "status": "error", "error": f"{type(e).__name__}: {e}"}

    if not docs:
        return {"query": query, "status": "not_found", "excerpts": [], "sources": []}

    excerpts = []
    for doc in docs:
        page = doc.metadata.get("page")
        excerpts.append({
            "source": Path(doc.metadata.get("source", "unknown")).name,
            # PyPDF pages are 0-based; people count from 1.
            "page": page + 1 if isinstance(page, int) else None,
            "text": doc.page_content,
        })
    sources = sorted({f"{e['source']}, p. {e['page']}" if e["page"] else e["source"] for e in excerpts})
    return {"query": query, "status": "success", "excerpts": excerpts, "sources": sources}


if __name__ == "__main__":
    for q in ["Qual o prazo para devolução de um produto?",
              "Como funciona a garantia dos instrumentos?",
              "Quais são as formas de pagamento aceitas?"]:
        print(f"\n{'=' * 60}\nQuery: {q}\n{'=' * 60}")
        print(json.dumps(run_policy_qa(q), indent=2, ensure_ascii=False))
