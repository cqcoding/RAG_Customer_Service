from src.models.model_llm import OpenRouterLLM
from src.agents.base_agent import BaseAgent
from langchain_core.prompts import PromptTemplate
import json

from functools import lru_cache

MODEL_NAME = OpenRouterLLM.DEFAULT_MODEL


@lru_cache(maxsize=1)
def get_agent() -> BaseAgent:
    return BaseAgent(model_name=MODEL_NAME)


def question_answering_with_retrieval(query: str) -> dict:
    retriever = get_agent().retriever
    docs = retriever.invoke(query)

    if not docs:
        return {
            "reasoning": "No relevant documents found in the database.",
            "final_answer": "I couldn't find that information in the provided documents.",
            "sources": []
        }
    context = "\n\n".join([
        f"Document {i+1} (Source: {doc.metadata.get('source', 'Unknown')}):\n{doc.page_content}"
        for i, doc in enumerate(docs)
    ])


    prompt_template = """You are the customer service assistant of a Brazilian music store.
Answer the question about store policies based EXCLUSIVELY on the provided context.

CRITICAL RULES:
1. Use ONLY information explicitly stated in the documents
2. DO NOT use your training data or external knowledge
3. If the exact answer isn't in the documents, say "I couldn't find that information in the provided documents"
4. Always cite specific document sources
5. Quote exact numbers, deadlines and conditions from the documents

CONTEXT:
{context}

QUESTION:
{query}

EXPECTED RESPONSE FORMAT (JSON):
{{
    "reasoning": "Step-by-step explanation of how you found the answer in the documents",
    "final_answer": "Direct answer with specific numbers and sources",
    "sources": ["List of document sources used"]
}}
"""

    prompt = prompt_template.format(context=context, query=query)
    messages = [{"role": "user", "content": prompt}]
    llm = OpenRouterLLM(temperature=0)
    response = llm.invoke(messages)
    
    raw = BaseAgent.clean_json(response["content"])
    result = json.loads(raw)
    result["model_used"] = response.get("model_used", "unknown")
    
    return result

def run_policy_qa(query: str) -> dict:
    try:
        parsed = question_answering_with_retrieval(query)

        return {
            "query": query,
            "reasoning": parsed.get("reasoning", ""),
            "final_answer": parsed.get("final_answer", ""),
            "sources": parsed.get("sources", []),
            "status": "success"
        }
    except json.JSONDecodeError as e:
        return {
            "query": query,
            "error": f"Failed to parse JSON: {str(e)}",
            "status": "error"
        }
    except Exception as e:
        return {
            "query": query,
            "error": str(e),
            "status": "error"
        }


if __name__ == "__main__":
    test_queries = [
        "Qual o prazo para devolução de um produto?",
        "Como funciona a garantia dos instrumentos?",
        "Quais são as formas de pagamento aceitas?"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        
        result = run_policy_qa(query)
        print(json.dumps(result, indent=2, ensure_ascii=False))