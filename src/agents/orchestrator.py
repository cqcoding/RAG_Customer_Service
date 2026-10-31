import json
import operator
import time
from typing import Annotated, Literal, Optional, TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel, Field

from src.agents.base_agent import BaseAgent
from src.agents.qa_agent import run_policy_qa
from src.agents.sql_agent import run_sql_agent
from src.config import get_settings
from src.models.model_llm import OpenRouterLLM
from src.utils.logger import logger

load_dotenv()

# How much of the conversation the router and synthesizer see.
MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_CHARS = 600


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class AgentOutput(TypedDict):
    """Output from each subagent."""
    source: str
    result: object


class Classification(TypedDict):
    """A single routing decision: which agent to call with what query."""
    source: Literal["question_answerer", "store_database"]
    query: str


class RouterState(TypedDict, total=False):
    query: str
    # Previous turns, oldest first, without the current query.
    history: list[ChatMessage]
    classifications: list[Classification]
    results: Annotated[list[AgentOutput], operator.add]  # Reducer collects parallel results
    final_answer: str


def _recent_history(state: RouterState) -> list[ChatMessage]:
    return [
        {"role": m["role"], "content": m["content"][:MAX_HISTORY_CHARS]}
        for m in (state.get("history") or [])[-MAX_HISTORY_MESSAGES:]
    ]


def _run_agent(name: str, query: str, fn) -> dict:
    """Run one agent, log it, and wrap its result for the reducer."""
    start_time = time.time()
    try:
        result = fn()
        failed = isinstance(result, dict) and result.get("status") == "error"
        logger.log_agent_execution(
            agent_name=name,
            input_query=query,
            output=json.dumps(result, ensure_ascii=False, default=str),
            latency_ms=(time.time() - start_time) * 1000,
            status="error" if failed else "success",
            error=result.get("error") if failed else None,
        )
        return {"results": [{"source": name, "result": result}]}
    except Exception as e:
        logger.log_agent_execution(
            agent_name=name,
            input_query=query,
            output="",
            latency_ms=(time.time() - start_time) * 1000,
            status="error",
            error=str(e),
        )
        return {"results": [{"source": name, "result": f"Error: {str(e)}"}]}


def question_answerer(state: RouterState) -> dict:
    """RAG over the store policy PDF."""
    return _run_agent("question_answerer", state["query"],
                      lambda: run_policy_qa(state["query"]))


def store_database(state: RouterState) -> dict:
    """SQL agent for products, prices, stock, promotions and orders."""
    return _run_agent("store_database", state["query"],
                      lambda: run_sql_agent(state["query"]))


settings = get_settings()
# Routing is a small classification task: a faster, cheaper model is enough.
router_llm = OpenRouterLLM(model=settings.router_llm_model)
synth_llm = OpenRouterLLM()


class ClassificationResult(BaseModel):
    """Result of classifying a user query into agent-specific sub-questions."""
    classifications: list[Classification] = Field(
        description="List of agents to invoke with their targeted sub-questions"
    )


ROUTER_PROMPT = """You route customer messages for a Brazilian music store.
For each relevant agent, generate a targeted sub-question optimized for that agent.
Keep sub-questions in the customer's language.

Available agents:
- question_answerer: store POLICIES from the policy document: returns and
  exchanges, warranty, shipping rules and deadlines, payment conditions,
  privacy, how the store works in general.
- store_database: live STORE DATA from the database: product catalog, prices,
  promotions/discounts, stock availability, product specs, categories, and
  orders by number (status, tracking code, delivery date, items).

Sub-questions must be SELF-CONTAINED: the agents do not see the conversation.
Resolve references to earlier messages ("ele", "esse modelo", "e o preço?",
"e o outro pedido?") into explicit product names, order numbers, etc.

Return ONLY JSON with this exact schema and no extra text:
{"classifications": [{"source": "question_answerer|store_database", "query": "..."}]}

Return ONLY the agents that are relevant. Use both when the message mixes
policy and data. Return {"classifications": []} for greetings, thanks, small
talk, or questions unrelated to the store.

Examples:
- "Qual o prazo para devolução?" -> question_answerer: "Qual o prazo para devolução?"
- "Tem o Yamaha C40 em estoque?" -> store_database: "O produto Yamaha C40 está em estoque e qual o preço atual?"
- "Meu pedido 5 chegou com defeito, posso trocar?" ->
    store_database: "Qual o status, data de entrega e itens do pedido 5?"
    question_answerer: "Qual a política de troca para produtos com defeito?"
- Conversation: customer asked about the "Yamaha C40". Message: "e tem desconto?" ->
    store_database: "O Yamaha C40 tem alguma promoção ativa e qual o preço com desconto?"
- "Obrigado!" -> {"classifications": []}"""


def _router_input(state: RouterState) -> str:
    history = _recent_history(state)
    if not history:
        return state["query"]
    lines = [f"{'Customer' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in history]
    return "Conversation so far:\n" + "\n".join(lines) + f"\n\nCurrent message: {state['query']}"


def classify_query(state: RouterState) -> dict:
    """Classify query and determine which agents to invoke."""
    start_time = time.time()
    router_input = _router_input(state)

    try:
        result = router_llm.invoke([
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": router_input},
        ])
        latency_ms = (time.time() - start_time) * 1000

        # Models often wrap JSON in ```json fences; strip them before parsing.
        payload = json.loads(BaseAgent.clean_json(result["content"]))
        parsed = ClassificationResult.model_validate(payload)

        logger.log_routing_decision(query=state["query"], classifications=parsed.classifications)
        logger.log_llm_call(
            provider="openrouter",
            model=result.get("model_used", router_llm.model),
            prompt=router_input,
            response=result["content"],
            latency_ms=latency_ms,
            agent="classifier",
            status="success"
        )
        return {"classifications": parsed.classifications}
    except Exception as e:
        logger.log_llm_call(
            provider="openrouter",
            model=router_llm.model,
            prompt=router_input,
            response="",
            latency_ms=(time.time() - start_time) * 1000,
            agent="classifier",
            status="error",
            error=str(e)
        )
        return {"classifications": []}


def route_to_agents(state: RouterState):
    """Fan out to agents based on classifications."""
    if not state.get("classifications"):
        # Small talk / unrelated / router failure: let the synthesizer reply.
        return "synthesize"
    # Each agent gets the full state with its own sub-question.
    return [
        Send(c["source"], {**state, "query": c["query"]})
        for c in state.get("classifications", [])
    ]


SYNTH_PROMPT = """You are the customer service assistant of a Brazilian music store.

Reply to the customer's latest message: "{query}"

- Answer in the same language as the customer's message
- Use ONLY the results below for facts; never invent prices, stock, order
  details or policies
- store_database results are rows from the store database: trust them for
  prices, stock and order data; format money as R$ 1.234,56
- question_answerer results come from the store policy document
- To check an order, the customer must give its order number or tracking code
- Never reveal customers' personal data (names, phones, e-mails)
- Combine information from multiple sources without redundancy
- Keep the response concise and well-organized; don't greet again mid-conversation"""

# Used when no agent ran (greetings, thanks, off-topic). Kept separate and
# strict: with nothing to ground on, models otherwise answer from general
# knowledge ("A capital da França é Paris...").
NO_RESULTS_PROMPT = """You are the customer service assistant of a Brazilian music store.
No store information was retrieved for the customer's latest message.

STRICT RULES:
- Do NOT answer the question and do NOT state any fact, not even well-known
  ones. You may only greet, thank, say goodbye, or decline.
- Greeting or thanks: reply warmly in one sentence and offer help.
- Anything else: say you can only help with the store, without answering it.
- Always mention you can help with products, prices, promotions, orders and
  store policies.
- Reply in the same language as the customer's message, in at most 2 sentences.

Examples:
Customer: "Qual a capital da França?"
Assistant: "Desculpe, só consigo ajudar com assuntos da loja: produtos, preços, promoções, pedidos e políticas. Posso ajudar com algo?"
Customer: "Who won the World Cup?"
Assistant: "Sorry, I can only help with store topics: products, prices, promotions, orders and policies. Anything I can help with?"
Customer: "Obrigado!"
Assistant: "Por nada! Se precisar, posso ajudar com produtos, preços, promoções, pedidos e políticas da loja."
"""

FALLBACK_ANSWER = (
    "Desculpe, não consegui processar sua mensagem agora. "
    "Posso ajudar com produtos, preços, promoções, pedidos e políticas da loja."
)


def synthesize_results(state: RouterState) -> dict:
    """Combine results from all agents into a coherent answer."""
    start_time = time.time()
    results = state.get("results") or []

    formatted = "\n\n".join(
        f"**From {r['source']}:**\n"
        + (r["result"] if isinstance(r["result"], str)
           else json.dumps(r["result"], ensure_ascii=False, default=str))
        for r in results
    ) or "(no results)"

    if results:
        messages = [
            {"role": "system", "content": SYNTH_PROMPT.format(query=state["query"])},
            *_recent_history(state),
            {"role": "user", "content": f"{state['query']}\n\nRESULTS:\n{formatted}"},
        ]
    else:
        messages = [
            {"role": "system", "content": NO_RESULTS_PROMPT},
            *_recent_history(state),
            {"role": "user", "content": state["query"]},
        ]

    try:
        response = synth_llm.invoke(messages)
        latency_ms = (time.time() - start_time) * 1000
        final_answer = response["content"]

        logger.log_synthesis(
            query=state["query"],
            num_results=len(results),
            final_answer=final_answer,
            latency_ms=latency_ms
        )
        logger.log_llm_call(
            provider="openrouter",
            model=response.get("model_used", synth_llm.model),
            prompt=formatted,
            response=final_answer,
            latency_ms=latency_ms,
            agent="synthesizer",
            status="success"
        )
        return {"final_answer": final_answer}
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.log_llm_call(
            provider="openrouter",
            model=synth_llm.model,
            prompt=formatted,
            response="",
            latency_ms=latency_ms,
            agent="synthesizer",
            status="error",
            error=str(e)
        )
        logger.log_synthesis(
            query=state["query"],
            num_results=len(results),
            final_answer=FALLBACK_ANSWER,
            latency_ms=latency_ms
        )
        return {"final_answer": FALLBACK_ANSWER}


workflow = (
    StateGraph(RouterState)
    .add_node("classify", classify_query)
    .add_node("question_answerer", question_answerer)
    .add_node("store_database", store_database)
    .add_node("synthesize", synthesize_results)
    .add_edge(START, "classify")
    .add_conditional_edges("classify", route_to_agents, ["question_answerer", "store_database", "synthesize"])
    .add_edge("question_answerer", "synthesize")
    .add_edge("store_database", "synthesize")
    .add_edge("synthesize", END)
    .compile()
)


def answer(query: str, history: Optional[list[ChatMessage]] = None) -> str:
    """Convenience entry point for the API and the front-end."""
    state = workflow.invoke({
        "query": query,
        "history": history or [],
        "classifications": [],
        "results": [],
        "final_answer": "",
    })
    return state.get("final_answer", "")
