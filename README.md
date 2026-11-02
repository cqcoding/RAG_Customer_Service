# RAG Customer Service
## Cecília Quaresma - AI Engineer – Full-Stack para Aplicações com IA Generativa 

[![CI](https://github.com/cqcoding/RAG_Customer_Service/actions/workflows/ci.yml/badge.svg)](https://github.com/cqcoding/RAG_Customer_Service/actions/workflows/ci.yml)

## Overview

A customer service assistant for **Empório da Música**, a Brazilian musical
instrument store in Campo Grande (shown in the chat as "Music Emporium Store").
Customers ask questions in natural language, in Portuguese or English, and the
assistant answers using two kinds of store knowledge:

- **Store policies** (returns, warranty, shipping, payment) from a PDF,
  retrieved with RAG (Retrieval-Augmented Generation) over a Chroma vector store.
- **Store data** (products, prices, promotions, stock, orders) from six CSV
  tables, loaded into PostgreSQL and queried by an agent that writes SQL.

A LangGraph orchestrator decides which of the two sources each question needs,
runs the matching agents in parallel and combines their results into one
answer. The assistant keeps the conversation context, so follow-up questions
like *"e tem desconto?"* work.


---

## Main features

- **Hybrid knowledge**: RAG for unstructured text (the policy PDF) and
  text-to-SQL for structured data (the CSV tables), each where it works best.
- **Multi-agent routing** with LangGraph: a router splits each message into
  targeted sub-questions and fans them out to the relevant agents in parallel.
- **Conversation memory**: follow-ups are rewritten into standalone questions.
- **Safe SQL generation**: one `SELECT` only, run by a read-only database role,
  on a read-only connection, with a timeout and a row cap.
- **Privacy by design**: the database role the agent uses can't read
  customers' names, phones or e-mails at all (column-level grants), and the
  prompt forbids listing customers or orders in bulk.
- **Resilient LLM access** through OpenRouter: retries on rate limits and
  automatic fallback across five models.
- **Two interfaces**: a Streamlit chat and a FastAPI REST API.
- **Structured logging** of every routing decision, agent run and LLM call.
- **Tests at three levels**: mocked unit tests, tests against a real
  PostgreSQL, and opt-in behavior tests against the real LLM. Lint and tests
  run automatically on GitHub Actions for every pull request.
- **One-command Docker setup** that loads the data and starts everything.

---

## Quick start

You need an [OpenRouter](https://openrouter.ai) API key.

### Option A: everything in Docker 

```bash
cp .env.example .env          # then set OPENROUTER_API_KEY in .env
make docker-up                # = docker compose up -d --build
```

Open the chat at **http://localhost:8501** and the API docs at
**http://localhost:8000/docs**. The first start takes a few minutes because
the embedding model is downloaded once. See [docs/DOCKER.md](docs/DOCKER.md).

### Option B: run the app locally 

Requires Python 3.12 and Docker (only for PostgreSQL).

```bash
cp .env.example .env          # set OPENROUTER_API_KEY and DATABASE_URL
make setup                    # creates venv/ and installs requirements
source venv/bin/activate
python -c "import nltk; nltk.download('punkt_tab')"   # sentence tokenizer, once
make db-up                    # starts PostgreSQL in Docker
make load-db                  # CSVs -> PostgreSQL, policy PDF -> Chroma
streamlit run src/front-end/interface.py              # chat on http://localhost:8501
```

To also run the REST API: `python -m uvicorn src.api.main:app --reload --port 8000`.

If port 5432 is already used by another PostgreSQL on your machine, set
`POSTGRES_PORT=5433` in `.env` and use the same port in `DATABASE_URL`
(`postgresql://rag:rag@localhost:5433/store`).

### Running the tests

```bash
pytest                                              # unit, API and database tests
RUN_LLM_TESTS=1 pytest tests/test_llm_behavior.py -v   # real-LLM behavior tests (costs API calls)
ruff check                                          # lint (or: make lint)
```

To regenerate the example conversations in [docs/EXAMPLES.md](docs/EXAMPLES.md)
against the real system (needs the API key and loaded data): `make examples`.

See [docs/TESTS.md](docs/TESTS.md).

---


## Documentation

| Document | Contents |
|---|---|
| [docs/EXAMPLES.md](docs/EXAMPLES.md) | Real example conversations (catalog, store information, prices, a return request applying the policy to a real order, guardrails), with the SQL and policy pages behind each answer |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, request flow, data layer, RAG pipeline, LLMs, design decisions and their history, limitations |
| [docs/API.md](docs/API.md) | REST API reference with examples |
| [docs/DOCKER.md](docs/DOCKER.md) | Docker setup, services, volumes, configuration, troubleshooting |
| [docs/LOGGING.md](docs/LOGGING.md) | What is logged, log format, viewer and log endpoints |
| [docs/TESTS.md](docs/TESTS.md) | Test strategy, what each test file covers, how to run them |
| [docs/AI_USAGE.md](docs/AI_USAGE.md) | How AI was used to build this project, and the review workflow |
