from src.models.model_llm import OpenRouterLLM
from src.agents.base_agent import BaseFinancialAgent
from langchain_core.prompts import PromptTemplate
import json

MODEL_NAME = OpenRouterLLM.DEFAULT_MODEL
agent = BaseFinancialAgent(model_name=MODEL_NAME)

def question_answering_with_retrieval(query: str) -> str:
    retriever = agent.retriever 
    docs = retriever.invoke(query)

    if not docs:
        return json.dumps({
            "reasoning": "No relevant documents found in the database.",
            "final_answer": "I couldn't find that information in the provided documents.",
            "sources": []
        })
    context = "\n\n".join([
        f"Document {i+1} (Source: {doc.metadata.get('source', 'Unknown')}):\n{doc.page_content}"
        for i, doc in enumerate(docs)
    ])


    prompt_template = """You are a senior financial analyst. 
    Answer the question based EXCLUSIVELY on the provided context.

CRITICAL RULES:
1. Use ONLY information explicitly stated in the documents
2. DO NOT use your training data or external knowledge
3. If the exact answer isn't in the documents, say "I couldn't find that information in the provided documents"
4. Always cite specific document sources
5. Quote exact numbers from the documents

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

    messages = [{"role": "user", "content": prompt}]
    llm = OpenRouterLLM(temperature=0)
    response = llm.invoke(messages)
    
    raw = BaseFinancialAgent.clean_json(response["content"])
    result = json.loads(raw)
    result["model_used"] = response.get("model_used", "unknown")
    
    return result

def run_financial_qa(query: str) -> dict:
    try:
        result_json = question_answering_with_retrieval(query)
        parsed = json.loads(result_json)
        
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
            "raw_response": result_json if 'result_json' in locals() else "N/A",
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
        "What was Tesla's revenue in Q4 2023?",
        "What are the main risks mentioned in Tesla's latest report?",
        "How does Tesla's 2023 performance compare to 2022?"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        
        result = run_financial_qa(query)
        print(json.dumps(result, indent=2, ensure_ascii=False))