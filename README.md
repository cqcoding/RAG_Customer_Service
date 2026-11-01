# RAG Customer Service

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

```
"Meu pedido 5 chegou com defeito, posso trocar?"
        │
        ├─► store_database     → order 5: delivered, Crafter D-8 Dreadnought Natural
        └─► question_answerer  → policy 4.2: defective products can be exchanged within 30 days
        │
        ▼
"Seu pedido 5 (Crafter D-8 Dreadnought Natural) consta como entregue. Pela nossa
 política, produtos com defeito de fabricação podem ser trocados em até 30 dias…"
```

---

## Main features

- **Hybrid knowledge**: RAG for unstructured text (the policy PDF) and
  text-to-SQL for structured data (the CSV tables), each where it works best.
- **Multi-agent routing** with LangGraph: a router splits each message into
  targeted sub-questions and fans them out to the relevant agents in parallel.
- **Conversation memory**: follow-ups are rewritten into standalone questions.
- **Safe SQL generation**: one `SELECT` only, run by a read-only database role,
  on a read-only connection, with a timeout and a row cap.
- **Privacy rules**: customers' personal data (name, phone, e-mail) is never
  returned, and customers or orders can't be listed in bulk.
- **Resilient LLM access** through OpenRouter: retries on rate limits and
  automatic fallback across five models.
- **Two interfaces**: a Streamlit chat and a FastAPI REST API.
- **Structured logging** of every routing decision, agent run and LLM call.
- **Tests at three levels**: mocked unit tests, tests against a real
  PostgreSQL, and opt-in behavior tests against the real LLM.
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
pytest                                              # unit + database tests
RUN_LLM_TESTS=1 pytest tests/test_llm_behavior.py -v   # real-LLM behavior tests (costs API calls)
```

See [docs/TESTS.md](docs/TESTS.md).

---

## Project structure

```
├── data/                         Store data: 6 CSV tables + políticas_da_loja.pdf
├── docs/                         Documentation and Postman collection
├── src/
│   ├── agents/
│   │   ├── orchestrator.py       LangGraph workflow: router, agents fan-out, synthesizer, memory
│   │   ├── qa_agent.py           Policy agent: RAG over the PDF
│   │   ├── sql_agent.py          Store data agent: writes and runs SQL
│   │   └── base_agent.py         Shared LLM + retriever setup, JSON cleanup
│   ├── api/main.py               FastAPI REST API
│   ├── front-end/interface.py    Streamlit chat
│   ├── models/model_llm.py       OpenRouter client with retries and model fallback
│   ├── config.py                 Settings (from environment / .env)
│   └── utils/
│       ├── create_sql_db.py      Loads the CSVs into PostgreSQL, creates the read-only role
│       ├── sql/schema.sql        Tables, keys and column comments (also the SQL agent's documentation)
│       ├── sql_database.py       Read-only query execution and schema description
│       ├── create_db.py          Builds the Chroma vector store from the PDF
│       ├── retriever.py          Chroma retriever (MMR)
│       ├── logger.py             Structured JSON logging
│       └── view_logs.py          Interactive log viewer
├── tests/                        Unit, database and LLM behavior tests
├── Dockerfile, docker-compose.yml
├── Makefile                      Shortcuts: setup, db-up, load-db, docker-up, test, …
└── .env.example                  All settings, with defaults
```

---

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it works: components, request flow, data layer, RAG pipeline, LLMs, design decisions and their history, limitations |
| [docs/API.md](docs/API.md) | REST API reference with examples |
| [docs/DOCKER.md](docs/DOCKER.md) | Docker setup, services, volumes, configuration, troubleshooting |
| [docs/LOGGING.md](docs/LOGGING.md) | What is logged, log format, viewer and log endpoints |
| [docs/TESTS.md](docs/TESTS.md) | Test strategy, what each test file covers, how to run them |
| [docs/AI_USAGE.md](docs/AI_USAGE.md) | How AI was used to build this project, and the review workflow |

---

## The data

| Source | Contents |
|---|---|
| `categories.csv` | 9 product categories (Guitarras, Violões, Ukuleles, …) |
| `products.csv` | 65 products with price, stock, status (`active`, `discontinued`, `coming_soon`) and JSON specs |
| `promotions.csv` | 25 promotions, 4 of them active |
| `customers.csv` | 50 customers (name, phone, e-mail, city) |
| `orders.csv` | 20 orders with status, payment method, tracking code and notes |
| `order_items.csv` | 22 order lines linking orders and products |
| `políticas_da_loja.pdf` | Store policy manual, 8 pages, 10 sections: about the store, opening hours, payment methods, returns and exchanges, shipping, promotions, WhatsApp service, warranty, privacy, final provisions |

`customers.csv` contains personal data. It is fine for this challenge dataset,
but real customer data should not be committed to git.
