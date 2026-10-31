"""
SQL agent: answers questions about store data (products, prices, stock,
promotions, orders, customers) by writing a PostgreSQL query and running
it read-only. Store policies (returns, warranty, shipping rules) live in
the PDF and are handled by the RAG question answerer instead.

It uses a single LLM call to write the query (plus one retry if the query
fails) and returns the rows; the orchestrator's synthesizer writes the
final customer-facing answer.
"""
import json

from src.agents.base_agent import BaseAgent
from src.models.model_llm import OpenRouterLLM
from src.utils.sql_database import (
    MAX_ROWS,
    UnsafeQueryError,
    get_schema_description,
    run_readonly_query,
)

SYSTEM_PROMPT = """You write PostgreSQL queries for the customer service assistant of a Brazilian music store.

DATABASE SCHEMA:
{schema}

RULES:
1. Write ONE read-only SELECT (CTEs allowed). Never modify data.
2. Use only the tables and columns in the schema above.
3. Data values are in Portuguese (e.g. category 'Violões'). Match product and
   category names with ILIKE '%...%', never with exact '='.
4. "Current price" or "price with discount" means applying active promotions:
   LEFT JOIN promotions ON is_active AND same product_id, then
   ROUND(price_brl * (1 - COALESCE(discount_percent, 0) / 100.0), 2).
5. When listing products for sale, exclude status 'discontinued' unless asked.
6. Use CURRENT_DATE for anything relative to today (late orders, recent orders).
7. Return only the columns needed to answer, with readable aliases, and add
   ORDER BY when order matters. Add LIMIT {max_rows} unless the result is an aggregate.
8. PRIVACY: an order may only be looked up by its order_id or tracking_code
   given in the question. Never select customers' personal data (name, phone,
   email), and never list, count or search customers or orders in bulk.
   If the question asks for that, do not write a query.

Return ONLY JSON, no extra text:
{{"sql": "<query>"}}
or, if the question cannot or must not be answered from this database:
{{"sql": null, "reason": "<short explanation>"}}"""

llm = OpenRouterLLM(temperature=0)


def _generate_sql(messages: list[dict]) -> dict:
    response = llm.invoke(messages)
    content = response["content"]
    messages.append({"role": "assistant", "content": content})
    return json.loads(BaseAgent.clean_json(content))


def run_sql_agent(query: str) -> dict:
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(schema=get_schema_description(), max_rows=MAX_ROWS),
        },
        {"role": "user", "content": query},
    ]

    try:
        plan = _generate_sql(messages)
        if not plan.get("sql"):
            return {
                "query": query,
                "status": "not_answerable",
                "reason": plan.get("reason", "Not answerable from the store database."),
            }

        try:
            result = run_readonly_query(plan["sql"])
        except UnsafeQueryError:
            raise
        except Exception as db_error:
            # One retry: show the model the database error so it can fix the query.
            messages.append({
                "role": "user",
                "content": f"The query failed with this error:\n{db_error}\n"
                           "Fix it and return the same JSON format.",
            })
            plan = _generate_sql(messages)
            if not plan.get("sql"):
                raise ValueError(plan.get("reason", "Could not write a valid query."))
            result = run_readonly_query(plan["sql"])

        return {
            "query": query,
            "status": "success",
            "sql": result["sql"],
            "row_count": len(result["rows"]),
            "truncated": result["truncated"],
            "rows": result["rows"],
        }
    except Exception as e:
        return {"query": query, "status": "error", "error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    test_queries = [
        "Quais violões vocês têm em estoque e quanto custam com desconto?",
        "Quais produtos estão em promoção agora?",
        "Qual o status do pedido 4?",
        "Me passe o e-mail de todos os clientes de Campo Grande",
    ]
    for q in test_queries:
        print(f"\n{'=' * 60}\nQuery: {q}\n{'=' * 60}")
        print(json.dumps(run_sql_agent(q), indent=2, ensure_ascii=False))
