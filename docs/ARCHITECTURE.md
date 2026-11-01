# Architecture

This document explains how the assistant works, why it is built this way, and
what its limits are. It is meant to be read top to bottom the first time, and
used as a reference afterwards.

- [1. The problem](#1-the-problem)
- [2. Technology stack](#2-technology-stack)
- [3. High-level overview](#3-high-level-overview)
- [4. Request flow, step by step](#4-request-flow-step-by-step)
- [5. The orchestrator (LangGraph)](#5-the-orchestrator-langgraph)
- [6. The policy agent (RAG)](#6-the-policy-agent-rag)
- [7. The store data agent (text-to-SQL)](#7-the-store-data-agent-text-to-sql)
- [8. Conversation memory](#8-conversation-memory)
- [9. LLMs and the OpenRouter client](#9-llms-and-the-openrouter-client)
- [10. Interfaces](#10-interfaces)
- [11. Configuration](#11-configuration)
- [12. Design decisions and how they evolved](#12-design-decisions-and-how-they-evolved)
- [13. Known limitations and next steps](#13-known-limitations-and-next-steps)
- [14. References](#14-references)

---

## 1. The problem

The store has two very different kinds of knowledge:

| | Store policies | Store data |
|---|---|---|
| **Format** | A PDF manual written in prose (10 sections) | Six CSV tables with ids and foreign keys |
| **Example questions** | "Qual o prazo para trocar um produto com defeito?" | "Quais violões estão em promoção e quanto custam com desconto?" / "Qual o status do pedido 8?" |
| **What answering needs** | Find the relevant paragraphs and paraphrase them | Filter, join tables and compute exact numbers (discounted prices, stock) |
| **Best technique** | Semantic search (RAG) | A database query (SQL) |

Many real questions need both: *"meu pedido 5 chegou com defeito, posso
trocar?"* needs the order from the database and the exchange rules from the
policy. The architecture is built around that split: one agent per kind of
knowledge, and an orchestrator that decides which ones a question needs and
merges their answers.

---

## 2. Technology stack

| Layer | Technology | Why |
|---|---|---|
| Orchestration | **LangGraph** (`StateGraph`) | Explicit state, parallel fan-out/fan-in with a reducer, easy to test node by node |
| LLM access | **OpenRouter**, through a small custom client (`src/models/model_llm.py`) | One API for many models, so fallback across providers is a list of names; the custom client gives full control over retries |
| Structured data | **PostgreSQL 16** + **psycopg 3** | Real joins, types and constraints; read-only roles and statement timeouts make LLM-written SQL safe to run |
| Vector store | **ChromaDB**, embedded with local persistence | Lightweight, no extra server, persists to a folder |
| Embeddings | **FastEmbed** with `BAAI/bge-base-en-v1.5` | Open-source, runs fast on CPU, no paid embedding API |
| Chunking | **NLTK** sentence splitter + LangChain `RecursiveCharacterTextSplitter` | See [6.2](#62-chunking) |
| Front-end | **Streamlit** | A working chat UI in a few dozen lines |
| API | **FastAPI** + **Uvicorn** | Typed request/response models and automatic Swagger docs |
| Settings | **pydantic-settings** + `.env` | One typed `Settings` class, overridable by environment variables |
| Packaging | **Docker** + **Docker Compose** | One command starts PostgreSQL, loads data and runs the app |
| Tests and CI | **pytest** / `unittest.mock`, **ruff**, **GitHub Actions** | Three levels (mocked, real database, real LLM); lint and tests run on every pull request |

---

## 3. High-level overview

```mermaid
flowchart LR
    U[Customer] --> UI[Streamlit chat<br/>or REST API]
    UI -->|message + history| R

    subgraph Orchestrator [LangGraph orchestrator]
        R[classify<br/>router LLM] -->|sub-questions| QA[question_answerer]
        R -->|sub-questions| SQL[store_database]
        R -->|no agent needed| S
        QA --> S[synthesize<br/>answer LLM]
        SQL --> S
    end

    QA <-->|similarity search| C[(Chroma<br/>policy PDF chunks)]
    SQL <-->|read-only SELECT| P[(PostgreSQL<br/>6 store tables)]
    S -->|final answer| UI
```

Offline, two scripts prepare the knowledge:

```
data/*.csv               ──  src/utils/create_sql_db.py  ──►  PostgreSQL (tables + read-only role)
data/políticas_da_loja.pdf ── src/utils/create_db.py     ──►  Chroma (embedded chunks)
```

---

## 4. Request flow, step by step

Example: the customer previously asked about the *Ohana CK-20*, and now writes
**"e tem desconto?"**.

1. **Interface.** Streamlit (or an API client) calls
   `orchestrator.answer(query, history)` with the message and the previous turns.
2. **classify.** The router LLM sees the last turns and the new message, and
   returns JSON:
   ```json
   {"classifications": [{"source": "store_database",
     "query": "O Ohana CK-20 tem promoção ativa e qual o preço com desconto?"}]}
   ```
   The vague follow-up became a self-contained sub-question.
3. **Fan-out.** `route_to_agents` sends one LangGraph `Send` per
   classification, so agents run in parallel, each with its own sub-question.
4. **store_database.** The SQL agent writes:
   ```sql
   SELECT p.name, p.price_brl, pr.discount_percent,
          ROUND(p.price_brl * (1 - COALESCE(pr.discount_percent, 0) / 100.0), 2) AS preco_final
   FROM products p
   LEFT JOIN promotions pr ON pr.product_id = p.product_id AND pr.is_active
   WHERE p.name ILIKE '%Ohana CK-20%'
   ```
   It runs read-only and returns the row:
   `Ohana CK-20 Concert Natural | 549.00 | 20 | 439.20`.
5. **synthesize.** The answer LLM gets the results as JSON plus the recent
   history, and writes the reply in the customer's language: *"Sim! O Ohana
   CK-20 Concert Natural está com 20% de desconto: sai de R$ 549,00 por
   R$ 439,20."*
6. **Logging.** The routing decision, each agent run and each LLM call are
   written to `logs/llm_calls.jsonl` (see [LOGGING.md](LOGGING.md)).

A typical request makes 3 LLM calls (router, SQL or RAG agent, synthesizer),
or 4 when both agents run.

---

## 5. The orchestrator (LangGraph)

File: `src/agents/orchestrator.py`.

### 5.1 The graph

```
START → classify ──┬─► question_answerer ─┐
                   ├─► store_database ────┼─► synthesize → END
                   └─► (no agents) ───────┘
```

### 5.2 State

```python
class RouterState(TypedDict, total=False):
    query: str                      # the current message (or an agent's sub-question)
    history: list[ChatMessage]      # previous turns, oldest first
    classifications: list[Classification]
    results: Annotated[list[AgentOutput], operator.add]   # reducer merges parallel results
    final_answer: str
```

`results` uses `operator.add` as a reducer: each agent returns a one-item list,
and LangGraph concatenates them when the parallel branches join. That is what
makes fan-out/fan-in work without extra code.

### 5.3 The router (`classify_query`)

- Uses a **smaller, faster model** (`ROUTER_LLM_MODEL`, default
  `google/gemini-2.5-flash-lite`), because routing is a simple classification
  task and it runs on every message.
- The prompt describes the two agents (policies vs. store data), asks for
  **self-contained sub-questions** (agents don't see the conversation), and
  includes examples, including a follow-up and a "thanks" that needs no agent.
- The reply is cleaned of Markdown fences (` ```json `) and validated with
  Pydantic, so only `question_answerer` and `store_database` are accepted.
- If the reply can't be parsed, or the message is small talk or off-topic,
  the classifications are empty and the graph goes **straight to the
  synthesizer**.

### 5.4 Running the agents (`_run_agent`)

Each agent node calls its agent through one helper that measures latency,
logs the run, and turns any exception into an `"Error: …"` result. One failing
agent therefore never breaks the request: the synthesizer still answers with
what it has.

### 5.5 The synthesizer (`synthesize_results`)

Two prompts:

- **With results**: answer only from the results; reply in the customer's
  language; format money as `R$ 1.234,56`; trust database rows for prices,
  stock and orders; ask for an order number when needed; never reveal
  customers' personal data; never invent anything.
- **Without results** (no agent ran): a strict prompt that may only greet,
  thank or decline, and must not state any fact. This exists because, with the
  general prompt, the model once answered *"A capital da França é Paris"*
  before declining (caught by the behavior tests, see [TESTS.md](TESTS.md)).

If the LLM call fails, a fixed, polite fallback message is returned.

---

## 6. The policy agent (RAG)

Files: `src/agents/qa_agent.py`, `src/utils/create_db.py`, `src/utils/retriever.py`.

### 6.1 Building the vector store

`python -m src.utils.create_db` (also run by `make load-db` and by Docker's
`init` service):

1. Loads every PDF in `data/` with `PyPDFLoader` (one document per page).
2. Adds metadata to each page: `file_type`, `document` (file name) and
   `doc_type: store_policy`, on top of PyPDF's own (`source`, `page`,
   `total_pages`, …). Metadata travels with every chunk, so answers can cite
   their source.
3. Splits the text into chunks (below).
4. **Deletes and recreates** the collection (`my_collection` in
   `CHROMA_DB_PATH`), then adds the chunks in batches of 25. Rebuilding from
   scratch makes the script safe to re-run: an earlier version appended,
   which duplicated every chunk on each run.

With `--if-empty`, it skips the build when the collection already has
chunks. Docker uses this so that restarts don't re-embed the PDF.

### 6.2 Chunking

A **hybrid** strategy: NLTK sentence splitting first, then a recursive
character splitter into chunks of **600 characters with 80 characters of
overlap**.

- Sentence splitting keeps sentences whole, so a rule is never cut in half.
- The 600-character cap keeps chunks focused, which makes retrieval precise.
- The overlap keeps context across chunk borders.

In the earlier project this code comes from, pure semantic chunking was tried
and proved unstable across very different document styles (technical PDFs,
spreadsheets, narrative text); the hybrid approach gave consistent chunks and
was kept. For the 8-page
policy PDF this produces about 30 to 35 chunks, about 440 characters on
average.

### 6.3 Embeddings

FastEmbed with `BAAI/bge-base-en-v1.5`: open-source, fast on CPU, no paid
API. The model name is a single setting (`EMBEDDING_MODEL`), used both to
build and to query the store, so the two can't drift apart. The model is
downloaded on first use (in Docker, into a cached volume).

Note: this model was trained mostly on English, while the policy and most
questions are in Portuguese. See [limitations](#13-known-limitations-and-next-steps).

### 6.4 Retrieval and answering

- The retriever uses **MMR** (maximal marginal relevance): it fetches the 25
  most similar chunks and keeps the **6** that are both relevant and
  different from each other, which avoids six near-identical chunks.
- The prompt tells the model to answer **exclusively** from the retrieved
  context, to cite sources, to quote exact deadlines and conditions, and to
  say it couldn't find the answer otherwise.
- The model replies with JSON: `reasoning`, `final_answer`, `sources`.
- If nothing is retrieved, the LLM isn't called at all.
- The retriever and embedding model are created on first use, not at import,
  so starting the API or running tests doesn't load the model.

---

## 7. The store data agent (text-to-SQL)

Files: `src/agents/sql_agent.py`, `src/utils/sql_database.py`,
`src/utils/sql/schema.sql`, `src/utils/create_sql_db.py`.

### 7.1 Why SQL instead of RAG for the CSVs

The CSVs are relational: an order has items, items point to products,
products to categories and promotions. Questions like *"what's the discounted
price?"* or *"what's in order 5?"* need joins and arithmetic. Similarity
search over rows can't join tables, can't compute, and can't guarantee that
every relevant row is returned. A database query does all of that exactly.
See [12.1](#121-from-embedding-the-csvs-to-postgresql) for how the project
got there.

### 7.2 The schema

`schema.sql` creates typed tables with primary keys, foreign keys and `CHECK`
constraints (for example, `orders.status` must be one of `pending`,
`confirmed`, `shipped`, `delivered`, `cancelled`).

| Table | Key columns |
|---|---|
| `categories` | `category_id`, `name`, `description` |
| `products` | `product_id`, `name`, `price_brl`, `category_id` → categories, `stock_quantity`, `status`, `specs` (JSONB), `created_at` |
| `promotions` | `promotion_id`, `product_id` → products, `discount_percent`, `is_active` |
| `customers` | `customer_id`, `name`, `phone`, `email`, `city` |
| `orders` | `order_id`, `customer_id` → customers, `order_date`, `status`, `total_brl`, `payment_method`, `tracking_code`, `estimated_delivery`, `notes` |
| `order_items` | (`order_id`, `product_id`) → orders, products; `quantity` |

**The `COMMENT ON` statements are the agent's documentation.** At runtime, the
agent reads tables, columns, types, keys and comments from PostgreSQL's
catalog and puts them in its prompt. So the comments explain what the data
means, for example:

- `tracking_code` is NULL until the order ships;
- only promotions with `is_active = TRUE` apply now;
- discounted price = `price_brl * (1 - discount_percent / 100.0)`;
- `payment_method` `credit_12x` means 12 installments;
- `specs` is JSONB, queried with `specs->>'key'`.

Changing a comment changes the agent's behavior, so comments should be
reviewed like prompts. The schema description is cached per process, so
restart the app after changing the schema.

### 7.3 Loading the data

`python -m src.utils.create_sql_db` runs `schema.sql` (which drops and
recreates every table), inserts the CSV rows in foreign-key order (empty
cells become `NULL`, `is_active` becomes a boolean), and creates or refreshes
the read-only role. It is safe to re-run.

### 7.4 How the agent answers

1. **One LLM call** with the schema and the rules returns either
   `{"sql": "SELECT …"}` or `{"sql": null, "reason": "…"}` when the question
   can't or mustn't be answered from the database.
2. The query runs (see the safety layers below).
3. If the **database** rejects it (a wrong column name, for example), the
   agent retries **once**, showing the model the exact database error. Unsafe
   queries are not retried.
4. The agent returns the rows (as JSON-friendly values) and the SQL. It does
   **not** write prose: the synthesizer does that, which saves an LLM call.

Rules in the prompt:

1. Exactly one read-only `SELECT` (CTEs allowed).
2. Only tables and columns from the schema.
3. Values are in Portuguese: match names with `ILIKE '%…%'`, never `=`.
4. "Current price" means applying active promotions (with the exact formula).
5. Exclude `discontinued` products unless asked.
6. Use `CURRENT_DATE` for anything relative to today.
7. Only the columns needed, readable aliases, `ORDER BY` when order matters,
   `LIMIT 50` unless the result is an aggregate.
8. **Privacy**: orders only by their `order_id` or `tracking_code`; never
   select customers' personal data; never list, count or search customers or
   orders in bulk. (Personal data is also impossible to read at the database
   level, see 7.5; this rule mainly prevents bulk listing.)

### 7.5 Safety layers for LLM-written SQL

The model writes SQL, so the system assumes that SQL may be wrong or
malicious (for example, after prompt injection), and limits what it can do:

| Layer | What it does | Where |
|---|---|---|
| Statement check | Only a single statement starting with `SELECT` or `WITH`; rejects `;`-separated statements | `validate_select()` |
| Read-only role | Connects as `store_reader`, which only has `SELECT` grants | `create_sql_db.setup_reader_role()` |
| Column-level grants | On `customers`, the role can only read `customer_id` and `city`: selecting `name`, `phone`, `email` (or `*`) fails with *permission denied*, whatever the prompt says. The schema description shown to the agent omits those columns, so it doesn't try | `READER_CUSTOMER_COLUMNS`, `_SCHEMA_QUERY` |
| Read-only connection | The transaction is read-only, so PostgreSQL rejects writes hidden in a `WITH` or a function like `query_to_xml` | `_connect_reader()` |
| Statement timeout | Each query is cancelled after 5 seconds | `STATEMENT_TIMEOUT_MS` |
| Row cap | At most 50 rows are returned, with a `truncated` flag | `MAX_ROWS` |

The first layer is a convenience; the real protection is in PostgreSQL itself
(layers 2 to 5), which can't be talked out of its permissions. The tests try
writes that get past the first layer, and reads of personal data, and check
that the database refuses them.

Only the loader uses the owner account (`DATABASE_URL`); the agent never
connects with it.

---

## 8. Conversation memory

- The **client keeps the history**: Streamlit in `st.session_state` (per
  browser tab), API clients in the `history` field of each request. The
  server is stateless, so it scales and restarts freely.
- The **router** sees the last **6** messages (each cut to **600**
  characters) and rewrites follow-ups into self-contained sub-questions. The
  agents never see the history: they get explicit questions, which keeps them
  simple and testable.
- The **synthesizer** also sees the recent history, so the reply continues
  the conversation naturally (no repeated greetings, consistent references).
- "Nova conversa" in the chat clears the history.

---

## 9. LLMs and the OpenRouter client

### 9.1 Models

| Role | Model | Setting |
|---|---|---|
| Router | `google/gemini-2.5-flash-lite` | `ROUTER_LLM_MODEL` |
| SQL agent, policy agent, synthesizer | `google/gemini-3-flash-preview` | `OpenRouterLLM.DEFAULT_MODEL` |

All calls use **temperature 0**, which reduces randomness and invented
details: important when answers involve prices and deadlines.

**How the main model was chosen.** The first version used OpenRouter's free
models (DeepSeek, Llama, Solar). They cost nothing, but at peak hours they
often failed with *429 Too Many Requests*. The project moved to **Gemini 3
Flash Preview**: reasoning capability, two providers on OpenRouter, reasonable
latency, caching, tool support and a large context window, at $0.50 per
million input tokens and $3 per million output tokens (OpenRouter prices at
the time of writing). In comparison, GPT-4o had a context window about 10×
smaller, no reasoning mode, and was about 10× more expensive.

### 9.2 Fallback chain

If a model fails, the client tries the next one (`FALLBACK_MODELS` in
`model_llm.py`):

| Order | Model | Why it's in the chain | Price per M tokens (in / out) |
|---|---|---|---|
| 1 | `minimax/minimax-m2.1` | High quality, good reasoning and long context; the most stable alternative | $0.30 / $1.20 |
| 2 | `deepseek/deepseek-v3.2` | Strong at technical and structured tasks (JSON, SQL), low latency | $0.27 / $1.00 |
| 3 | `upstage/solar-pro-3:free` | Free, good multilingual ability; keeps working at peak hours | free |
| 4 | `google/gemini-2.5-flash-lite` | Low latency, high availability; the last resort | $0.10 / $0.40 |

The router runs on the 4th model by default, with the same chain behind it.

### 9.3 Retries

For each model, up to **3 attempts**:

- **429 (rate limit)** or **timeout** (60 s): wait and retry with exponential
  backoff, 2 s then 4 s.
- **Any other HTTP error, an empty response, or invalid JSON**: move to the
  next model immediately.

If every model fails, the client raises `LLMUnavailableError`. The agents and the
orchestrator turn that into an error result and, at the end, a polite
fallback message, so the user never sees a stack trace. With
`enable_fallback=False`, only the given model is tried.

---

## 10. Interfaces

### Streamlit chat (`src/front-end/interface.py`)

A chat with message history per browser session, a spinner while the answer
is generated, and a "Nova conversa" button to start over. It calls the
orchestrator directly (it doesn't go through the API), so it runs on its own.

### REST API (`src/api/main.py`)

`POST /query` (with optional `history`), `GET /health`, and three log
endpoints. Full reference: [API.md](API.md).

The endpoints that do blocking work (`/query`, the log endpoints) are plain
`def` functions, not `async def`: FastAPI runs them in a thread pool, so
several questions are answered at the same time. An `async def` endpoint that
calls blocking code would stall the server's event loop, and the API would
answer one request at a time (a bug found in review, now covered by a test).

---

## 11. Configuration

All settings live in `src/config.py` and can be set in `.env` or as
environment variables (names are case-insensitive).

| Setting | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | none | Required for every LLM call |
| `ROUTER_LLM_MODEL` | `google/gemini-2.5-flash-lite` | Model used by the router |
| `DATABASE_URL` | `postgresql://rag:rag@localhost:5432/store` | Owner account: used by the loader only |
| `DATABASE_READER_USER` / `DATABASE_READER_PASSWORD` | `store_reader` / `store_reader` | Read-only role used by the SQL agent (same host and database as `DATABASE_URL`) |
| `CHROMA_DB_PATH` | `./chroma_db` | Vector store folder |
| `EMBEDDING_MODEL` | `BAAI/bge-base-en-v1.5` | FastEmbed model; rebuild the vector store after changing it |

Docker-only settings (`POSTGRES_*`, `API_PORT`, `FRONTEND_PORT`) are described
in [DOCKER.md](DOCKER.md).

---

## 12. Design decisions and how they evolved

The project started from the code of an earlier personal project, a **RAG
financial analyst** (agents for metric extraction, sentiment analysis and Q&A
over financial filings). The sections below record the main changes made to
turn it into this assistant, and why. How AI assistance was used in this
process is described in [AI_USAGE.md](AI_USAGE.md).

### 12.1 From embedding the CSVs to PostgreSQL

1. **First version:** the CSVs were loaded into Chroma with `TextLoader`,
   which turns each file into one block of text. The splitters then cut that
   text in the middle of rows, and the column headers were lost: 76 of 107
   chunks were fragments like `",9,active,"{""top"":""Spruce""…`, which
   neither search nor the LLM could interpret.
2. **Second version:** `CSVLoader`, with one document per row written as
   `column: value` lines, giving 191 clean row documents.
3. **Final version:** questions like *"what did this order contain?"* need
   data from 3 or 4 tables at once, which similarity search doesn't reliably
   return together. The tables moved to PostgreSQL with a text-to-SQL agent,
   and only the policy PDF stayed in Chroma.

### 12.2 Customer authentication: built, then deliberately removed

A version with real customer isolation was built: PostgreSQL **row-level
security** on `customers`, `orders` and `order_items`, keyed on a customer id
fixed when the connection opens, with identification by e-mail plus order
number. It was removed on purpose, because authentication is out of scope for
this stage. Privacy now relies on column-level grants (personal data can't be
read at all), the read-only role and the prompt rules (see
[limitations](#13-known-limitations-and-next-steps)). The design is
recorded here so it can be brought back.

### 12.3 Other changes

| Change | Reason |
|---|---|
| Finance agents (extractor, sentiment) replaced by the SQL agent | They didn't fit the domain |
| Router and synthesizer prompts rewritten for a store, in Portuguese, with examples | The old prompts were for financial reports |
| Router reply cleaned of ```` ```json ```` fences before parsing | Fenced replies made the router silently pick no agent ("No results found") |
| Smaller model for routing; removed a fixed 5-second wait in the UI | Latency |
| Conversation memory | Follow-up questions failed |
| Strict prompt when no agent runs | The model answered off-topic questions from general knowledge |
| Logger fed JSON strings instead of dicts | The logger slices its input, which raised on dicts and turned every success into an error |
| Embedding model loaded lazily | Importing the app shouldn't download or load a model |
| Vector store rebuilt instead of appended | Re-running the build duplicated every chunk |
| Docker: complete requirements, NLTK data in the image, model cache, `init` service | The image was missing packages, and the stack needed manual steps |
| Upload endpoint and HTML/TXT ingestion removed | Not needed for this project |
| `/query` changed from `async def` to `def` | The blocking workflow inside an `async` endpoint made the API answer one request at a time |
| Column-level grants on `customers` | Personal data protected by the database, not only by the prompt |
| Unused dependencies removed, every version pinned | Leftovers from the base project; reproducible installs in Docker and CI |
| `ruff`, GitHub Actions CI, API tests; unused `tracing.py` removed | Automated proof that `main` works; less dead code |

---

## 13. Known limitations and next steps

| Limitation | Impact | Possible next step |
|---|---|---|
| **No authentication** | Anyone who knows or guesses an order number can see that order's status, items and tracking code (personal data is safe: the database role can't read it) | Re-enable the row-level security design from [12.2](#122-customer-authentication-built-then-deliberately-removed), plus authentication and rate limiting on the API |
| **English embedding model** on Portuguese text | Weaker policy retrieval than possible | Switch `EMBEDDING_MODEL` to a multilingual FastEmbed model such as `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` or `intfloat/multilingual-e5-large`, rebuild Chroma, and compare answers |
| **LLM non-determinism** | Even at temperature 0, wording and occasionally behavior vary | Keep the real-LLM behavior tests and run them after every prompt or model change |
| **Latency** | 3 to 4 sequential LLM calls per question | Stream the final answer; skip the synthesizer when a single agent's output is already a good answer |
| **Logs contain customers' questions** | Privacy | Rotate and restrict access; avoid logging full prompts in production |
| **Cached schema description** | Schema changes need an app restart | Acceptable for a static schema |

---

## 14. References

- LangGraph: [overview](https://docs.langchain.com/oss/python/langgraph/overview), [workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- LangChain: [multi-agent subagents](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant), [RAG](https://docs.langchain.com/oss/python/langchain/rag), [text splitters](https://docs.langchain.com/oss/python/integrations/splitters), [vector stores](https://docs.langchain.com/oss/python/integrations/vectorstores)
- OpenRouter: [home](https://openrouter.ai/), [free models router](https://openrouter.ai/docs/guides/routing/routers/free-models-router), [model fallbacks](https://openrouter.ai/docs/guides/routing/model-fallbacks)
- [Streamlit API reference](https://docs.streamlit.io/develop/api-reference)
- [Pydantic](https://docs.pydantic.dev/latest/), [FastAPI](https://fastapi.tiangolo.com/)
- [Embedding models: a comprehensive guide](https://medium.com/@nay1228/embedding-models-a-comprehensive-guide-for-beginners-to-experts-0cfc11d449f1)
- PostgreSQL: [row security policies](https://www.postgresql.org/docs/16/ddl-rowsecurity.html), [comments](https://www.postgresql.org/docs/16/sql-comment.html)
- Videos: [1](https://www.youtube.com/watch?v=Zx_nHeBxZjw), [2](https://www.youtube.com/watch?v=7MrAr3j5v58)
