"""
Run example conversations through the real system and write docs/EXAMPLES.md.

Run with:  python -m src.utils.generate_examples      (or: make examples)

Needs what the app needs: OPENROUTER_API_KEY, PostgreSQL loaded and the
vector store built (make db-up && make load-db). Each run calls the real LLM,
so answers vary a little between runs: review the file before committing it.
"""
import time
from datetime import date
from pathlib import Path

from src.agents.orchestrator import run
from src.config import get_settings
from src.utils.create_db import get_vector_store
from src.utils.sql_database import run_readonly_query

OUTPUT = Path(__file__).resolve().parents[2] / "docs" / "EXAMPLES.md"

SCENARIOS = [
    {
        "title": "Catalog search with a price filter",
        "shows": "A catalog query answered from live data: the SQL agent filters "
                 "acoustic guitars by category, price, status and stock.",
        "turns": ["Quais opções de violões disponíveis custando até R$1000?"],
    },
    {
        "title": "General store information",
        "shows": "Answers from the policy document (RAG), and a follow-up question "
                 "that only makes sense with the conversation history.",
        "turns": ["Qual o endereço da loja?",
                  "E qual o horário de funcionamento?"],
    },
    {
        "title": "Price lookup and promotions",
        "shows": "A product price, then follow-ups resolved from the conversation "
                 "(\"ele\" = the Takamine GD20), and the active promotions with "
                 "discounted prices computed in SQL.",
        "turns": ["Quanto custa o Takamine GD20?",
                  "Ele tem algum desconto?",
                  "E quais produtos estão em promoção agora?"],
    },
    {
        "title": "Return request: store policy applied to a real order",
        "shows": "The non-trivial case: the assistant combines the return and "
                 "exchange rules from the policy with the order's real data "
                 "(status and dates from the database) and today's date.",
        "turns": ["Me arrependi da minha compra, posso devolver meu pedido?",
                  "É o pedido 7.",
                  "E se o produto tivesse vindo com defeito?"],
    },
    {
        "title": "Guardrails: personal data and off-topic questions",
        "shows": "Customers' personal data is never revealed (the database role "
                 "can't even read it), and questions unrelated to the store are "
                 "declined without answering them.",
        "turns": ["Qual o telefone do cliente que fez o pedido 3?",
                  "Qual a capital da França?"],
    },
]


def preflight() -> None:
    """Fail early, with a clear message, if the system isn't ready."""
    problems = []
    if not get_settings().openrouter_api_key:
        problems.append("OPENROUTER_API_KEY is not set (put it in .env).")
    try:
        run_readonly_query("SELECT 1 FROM products LIMIT 1")
    except Exception as e:
        problems.append(f"The store database isn't reachable ({type(e).__name__}): run `make db-up && make load-db`.")
    try:
        if get_vector_store()._collection.count() == 0:
            problems.append("The vector store is empty: run `make load-db`.")
    except Exception as e:
        problems.append(f"The vector store can't be opened ({type(e).__name__}: {e}).")
    if problems:
        raise SystemExit("Can't generate the examples:\n- " + "\n- ".join(problems))


def run_turn(message: str, history: list[dict]) -> dict:
    start = time.perf_counter()
    state = run(message, history)
    return {
        "message": message,
        "answer": state.get("final_answer", ""),
        "classifications": state.get("classifications") or [],
        "results": state.get("results") or [],
        "seconds": time.perf_counter() - start,
    }


def _details(turn: dict) -> list[str]:
    """How the answer was produced: route, SQL, policy sources, time."""
    lines = ["<details>", "<summary>How the assistant got this answer</summary>", ""]
    if not turn["classifications"]:
        lines.append("- **Route:** no agent (greeting, thanks or off-topic): the reply comes from the "
                     "assistant's strict no-facts prompt.")
    for c in turn["classifications"]:
        lines.append(f"- **Route:** `{c['source']}` with the sub-question *\"{c['query']}\"*")
    for r in turn["results"]:
        result = r["result"]
        if not isinstance(result, dict):
            lines.append(f"- **`{r['source']}` error:** {result}")
            continue
        status = result.get("status")
        if r["source"] == "store_database":
            if result.get("sql"):
                lines += ["- **SQL run against PostgreSQL** "
                          f"({result.get('row_count', 0)} row(s)):", "", "  ```sql",
                          *[f"  {line}" for line in result["sql"].splitlines()], "  ```"]
            elif status in ("not_answerable", "error"):
                lines.append(f"- **SQL agent:** {status}: {result.get('reason') or result.get('error')}")
        elif r["source"] == "question_answerer":
            sources = ", ".join(result.get("sources") or []) or "none"
            lines.append(f"- **Policy excerpts used:** {sources}")
    lines += [f"- **Time:** {turn['seconds']:.1f} s", "", "</details>"]
    return lines


def render(conversations: list[dict]) -> str:
    out = [
        "# Example conversations",
        "",
        "Real conversations with the assistant, covering catalog queries, store",
        "information, prices and promotions, a return request that applies the store",
        "policy to a real order, and the privacy and scope guardrails.",
        "",
        f"They were produced on **{date.today().isoformat()}** by running each message through",
        "the complete system (router, agents, PostgreSQL, vector store and LLM) with",
        "`python -m src.utils.generate_examples`. Nothing was edited by hand. Under each",
        "answer, *\"How the assistant got this answer\"* shows the route, the SQL that",
        "ran and the policy pages used. Answers depend on the current date, and their",
        "wording varies between runs.",
        "",
        "| # | Scenario | What it shows |",
        "|---|---|---|",
    ]
    for i, conv in enumerate(conversations, 1):
        out.append(f"| {i} | [{conv['title']}](#{i}-{_slug(conv['title'])}) | {conv['shows']} |")
    for i, conv in enumerate(conversations, 1):
        out += ["", "---", "", f"## {i}. {conv['title']}", "", f"*{conv['shows']}*", ""]
        for turn in conv["turns"]:
            out += [f"**Customer:** {turn['message']}", "", "**Assistant:**", ""]
            out += [f"> {line}" if line.strip() else ">" for line in turn["answer"].strip().splitlines()]
            out += [""] + _details(turn) + [""]
    return "\n".join(out).rstrip() + "\n"


def _slug(title: str) -> str:
    keep = "".join(ch for ch in title.lower() if ch.isalnum() or ch in " -")
    return keep.replace(" ", "-")


def main() -> None:
    preflight()
    conversations = []
    suspicious = []
    for scenario in SCENARIOS:
        print(f"\n== {scenario['title']}")
        history, turns = [], []
        for message in scenario["turns"]:
            print(f"  Customer: {message}")
            turn = run_turn(message, history)
            preview = " ".join(turn["answer"].split())[:120]
            print(f"  Assistant ({turn['seconds']:.1f} s): {preview}...")
            turns.append(turn)
            history += [{"role": "user", "content": message},
                        {"role": "assistant", "content": turn["answer"]}]
            if "não consegui processar" in turn["answer"] or any(
                    not isinstance(r["result"], dict) or r["result"].get("status") == "error"
                    for r in turn["results"]):
                suspicious.append(f"{scenario['title']}: \"{message}\"")
        conversations.append({**scenario, "turns": turns})

    OUTPUT.write_text(render(conversations), encoding="utf-8")
    print(f"\nWrote {OUTPUT}")
    if suspicious:
        print("\nWARNING: these turns hit an error or the fallback answer; check logs/ and run again:")
        for s in suspicious:
            print(f"  - {s}")


if __name__ == "__main__":
    main()
