# RAG_Customer_Service

## Overview


## Main resources

## Architecture and Documentation

A LangGraph orchestrator (`src/agents/orchestrator.py`) classifies each
question and sends sub-questions, in parallel, to one or both agents. It
then synthesizes a single answer:

| Agent | Source | Answers |
|---|---|---|
| `question_answerer` (`src/agents/qa_agent.py`) | Store policy PDF, in Chroma (RAG) | Returns, warranty, shipping, payment rules |
| `store_database` (`src/agents/sql_agent.py`) | CSV tables, in PostgreSQL | Products, prices, promotions, stock, a customer's orders |

The SQL agent reads the table and column comments from
`src/utils/sql/schema.sql`, writes one `SELECT`, and runs it as the
SELECT-only `store_reader` role, on a read-only connection, with a statement
timeout and a row cap (`src/utils/sql_database.py`). If the query fails, it
retries once with the database error.

Conversation memory: the router sees the last few turns and rewrites
follow-ups ("e tem desconto?") into standalone questions for the agents.
Streamlit keeps the history per browser session; API clients send it in
`history`. The router uses a faster model (`ROUTER_LLM_MODEL`).


## Requirements


## Execution

```bash
cp .env.example .env          # set OPENROUTER_API_KEY
make setup                    # venv + dependencies
make db-up                    # start PostgreSQL (docker compose)
make load-db                  # CSVs -> PostgreSQL, policy PDF -> Chroma
make test                     # unit tests (mocked LLM; DB tests need Postgres)
RUN_LLM_TESTS=1 pytest tests/test_llm_behavior.py -v   # real-LLM edge/abuse tests
streamlit run src/front-end/interface.py
```

Rebuilding: both `create_sql_db` and `create_db` start from scratch on every
run, so re-running them is safe.

