import json
import time
from src.agents.qa_agent import run_financial_qa
from src.models.model_llm import OpenRouterLLM
from src.utils.logger import logger
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from typing import Annotated, Literal, TypedDict
import operator

load_dotenv()



class AgentInput(TypedDict):
    """Simple input state for each subagent."""
    query: str


class AgentOutput(TypedDict):
    """Output from each subagent."""
    source: str
    result: str


class Classification(TypedDict):
    """A single routing decision: which agent to call with what query."""
    source: Literal["data_extractor", "sentiment_analyst", "question_answerer"]
    query: str


class RouterState(TypedDict):
    query: str
    classifications: list[Classification]
    results: Annotated[list[AgentOutput], operator.add]  # Reducer collects parallel results
    final_answer: str

# def data_extractor(state: RouterState) -> dict:
#     """Call the extractor agent to get financial metrics."""
#     query = state["query"]
#     start_time = time.time()
#     try:
#         result = extract_financial_metrics(query)  # Call the actual extractor agent
#         latency_ms = (time.time() - start_time) * 1000
#         logger.log_agent_execution(
#             agent_name="data_extractor",
#             input_query=query,
#             output=result,
#             latency_ms=latency_ms,
#             status="success"
#         )
#         return {"results": [{"source": "data_extractor", "result": result}]}
#     except Exception as e:
#         latency_ms = (time.time() - start_time) * 1000
#         logger.log_agent_execution(
#             agent_name="data_extractor",
#             input_query=query,
#             output="",
#             latency_ms=latency_ms,
#             status="error",
#             error=str(e)
#         )
#         return {"results": [{"source": "data_extractor", "result": f"Error: {str(e)}"}]}

# def sentiment_analyst(state: RouterState) -> dict:
#     """Call the sentiment analysis agent."""
#     query = state["query"]
#     start_time = time.time()
#     try:
#         result = analyze_sentiment_from_query(query)  # Call the actual sentiment analysis agent
#         latency_ms = (time.time() - start_time) * 1000
#         logger.log_agent_execution(
#             agent_name="sentiment_analyst",
#             input_query=query,
#             output=result,
#             latency_ms=latency_ms,
#             status="success"
#         )
#         return {"results": [{"source": "sentiment_analyst", "result": result}]}
#     except Exception as e:
#         latency_ms = (time.time() - start_time) * 1000
#         logger.log_agent_execution(
#             agent_name="sentiment_analyst",
#             input_query=query,
#             output="",
#             latency_ms=latency_ms,
#             status="error",
#             error=str(e)
#         )
#         return {"results": [{"source": "sentiment_analyst", "result": f"Error: {str(e)}"}]}

def question_answerer(state: RouterState) -> dict:
    """Call the question answering agent."""
    query = state["query"]
    start_time = time.time()
    try:
        result = run_financial_qa(query)  # Call the actual QA agent
        latency_ms = (time.time() - start_time) * 1000
        logger.log_agent_execution(
            agent_name="question_answerer",
            input_query=query,
            output=result,
            latency_ms=latency_ms,
            status="success"
        )
        return {"results": [{"source": "question_answerer", "result": result}]}
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.log_agent_execution(
            agent_name="question_answerer",
            input_query=query,
            output="",
            latency_ms=latency_ms,
            status="error",
            error=str(e)
        )
        return {"results": [{"source": "question_answerer", "result": f"Error: {str(e)}"}]}

router_llm = OpenRouterLLM()

class ClassificationResult(BaseModel):  
    """Result of classifying a user query into agent-specific sub-questions."""
    classifications: list[Classification] = Field(
        description="List of agents to invoke with their targeted sub-questions"
    )

def classify_query(state: RouterState) -> dict:
    """Classify query and determine which agents to invoke."""
    start_time = time.time()

    try:
        result = router_llm.invoke([
            {
                "role": "system",
                "content": """Analyze this query and determine which agents to consult.
For each relevant agent, generate a targeted sub-question optimized for that agent.

Available agents:
- Data Extractor: For financial metrics
- Sentiment Analyst: For sentiment analysis
- Question Answerer: For answering specific queries

Return ONLY JSON with this exact schema and no extra text:
{"classifications": [{"source": "data_extractor|sentiment_analyst|question_answerer", "query": "..."}]}

Return ONLY the agents that are relevant to the query. Each agent should have
a targeted sub-question optimized for that specific agent.

Example for "What are the financial metrics?":
- Data Extractor: "What financial metrics should I retrieve?"
- Sentiment Analyst: "What is the sentiment of the financial report?"
- Question Answerer: "What questions can I answer regarding the financial data?" """
            },
            {"role": "user", "content": state["query"]}
        ])

        latency_ms = (time.time() - start_time) * 1000

        payload = json.loads(result["content"])
        parsed = ClassificationResult.model_validate(payload)

        # Log routing decision
        logger.log_routing_decision(
            query=state["query"],
            classifications=parsed.classifications
        )

        # Log LLM call
        logger.log_llm_call(
            provider="openrouter",
            model="free",
            prompt=state["query"],
            response=result["content"],
            latency_ms=latency_ms,
            agent="classifier",
            status="success"
        )

        return {"classifications": parsed.classifications}
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.log_llm_call(
            provider="openrouter",
            model="free",
            prompt=state["query"],
            response="",
            latency_ms=latency_ms,
            agent="classifier",
            status="error",
            error=str(e)
        )
        return {"classifications": []}

def route_to_agents(state: RouterState) -> list[Send]:
    """Fan out to agents based on classifications."""
    # Send the full state to each agent with updated query from classification
    return [
        Send(c["source"], {**state, "query": c["query"]})  
        for c in state["classifications"]
    ]

def synthesize_results(state: RouterState) -> dict:
    """Combine results from all agents into a coherent answer."""
    if not state["results"]:
        return {"final_answer": "No results found from any knowledge source."}

    start_time = time.time()
    
    # Format results for synthesis
    formatted = [
        f"**From {r['source'].title()}:**\n{r['result']}"
        for r in state["results"]
    ]

    try:
        synthesis_response = router_llm.invoke([
            {
                "role": "system",
                "content": f"""Synthesize these search results to answer the original question: "{state['query']}"

- Combine information from multiple sources without redundancy
- Highlight the most relevant and actionable information
- Note any discrepancies between sources
- Keep the response concise and well-organized"""
            },
            {"role": "user", "content": "\n\n".join(formatted)}
        ])

        latency_ms = (time.time() - start_time) * 1000
        final_answer = synthesis_response["content"]

        # Log synthesis
        logger.log_synthesis(
            query=state["query"],
            num_results=len(state["results"]),
            final_answer=final_answer,
            latency_ms=latency_ms
        )

        # Log LLM synthesis call
        logger.log_llm_call(
            provider="openrouter",
            model="free",
            prompt="\n\n".join(formatted),
            response=final_answer,
            latency_ms=latency_ms,
            agent="synthesizer",
            status="success"
        )

        return {"final_answer": final_answer}
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        error_message = f"LLM unavailable: {e}"
        logger.log_llm_call(
            provider="openrouter",
            model="free",
            prompt="\n\n".join(formatted),
            response="",
            latency_ms=latency_ms,
            agent="synthesizer",
            status="error",
            error=str(e)
        )
        logger.log_synthesis(
            query=state["query"],
            num_results=len(state["results"]),
            final_answer=error_message,
            latency_ms=latency_ms
        )
        return {"final_answer": error_message}


workflow = (
    StateGraph(RouterState)
    .add_node("classify", classify_query)
    .add_node("data_extractor", data_extractor)
    .add_node("sentiment_analyst", sentiment_analyst)
    .add_node("question_answerer", question_answerer)
    .add_node("synthesize", synthesize_results)
    .add_edge(START, "classify")
    .add_conditional_edges("classify", route_to_agents, ["data_extractor", "sentiment_analyst", "question_answerer"])
    .add_edge("data_extractor", "synthesize")
    .add_edge("sentiment_analyst", "synthesize")
    .add_edge("question_answerer", "synthesize")
    .add_edge("synthesize", END)
    .compile()
)