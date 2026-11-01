# REST API

The REST API exposes the assistant to other applications (a website chat
widget, WhatsApp integration, tests…) and gives access to the logs.

- Code: `src/api/main.py` (FastAPI)
- Base URL: `http://localhost:8000`
- Interactive docs: **http://localhost:8000/docs** (Swagger UI) and
  http://localhost:8000/redoc
- Postman collection: [`docs/postman_collection.json`](postman_collection.json)

---

## Starting the API

**With Docker** (see [DOCKER.md](DOCKER.md)), the API starts with the rest of the stack:

```bash
make docker-up
```

**Locally**, with PostgreSQL running and the data loaded (`make db-up` and
`make load-db`):

```bash
source venv/bin/activate
python -m uvicorn src.api.main:app --reload --port 8000
```

`--reload` restarts the server when code changes, which is useful during
development. `python -m src.api.main` also works, without auto-reload.

The first question after startup is slower: the embedding model is loaded
on first use.

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Is the API up? |
| `POST` | `/query` | Ask the assistant a question |
| `GET` | `/logs/llm-calls` | Latest log events |
| `GET` | `/logs/stats` | LLM call counts and average latency |
| `GET` | `/logs/routing-decisions` | Which agents handled each question |

---

### `GET /health`

Returns a fixed payload when the server is running. It doesn't check the
database or the LLM provider.

```json
{
  "status": "healthy",
  "service": "RAG Customer Service",
  "version": "1.0.0"
}
```

---

### `POST /query`

Runs the full workflow (router → agents → synthesizer) and returns the
answer.

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | The customer's message |
| `history` | list of `{role, content}` | no | Previous turns, oldest first. `role` is `"user"` or `"assistant"`. Send it to make follow-up questions work. Defaults to `[]` |

The API is **stateless**: it doesn't remember conversations. The client keeps
the history and sends it with each request. Only the last 6 messages are
used, each cut to 600 characters.

**Response**

| Field | Type | Description |
|---|---|---|
| `query` | string | The question, echoed |
| `final_answer` | string | The assistant's reply, in the language of the question |
| `latency_ms` | number | Total processing time |
| `status` | string | `"success"` |

**Example: a single question**

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Quais produtos estão em promoção?"}'
```

```json
{
  "query": "Quais produtos estão em promoção?",
  "final_answer": "Temos 4 produtos em promoção no momento:\n- Kalani KAL-700T Tenor Natural: de R$ 359,00 por R$ 323,10 (10% off)\n- Ohana CK-20 Concert Natural: de R$ 549,00 por R$ 439,20 (20% off)\n- Crafter HT-100 Folk Aço Natural: de R$ 2.399,00 por R$ 1.967,18 (18% off)\n- Taylor 110e Dreadnought Natural: de R$ 5.999,00 por R$ 5.519,08 (8% off)",
  "latency_ms": 4210.7,
  "status": "success"
}
```

(The wording of `final_answer` varies between runs; the facts come from the
database.)

**Example: a follow-up question**

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "E tem desconto?",
    "history": [
      {"role": "user", "content": "Quanto custa o Ohana CK-20?"},
      {"role": "assistant", "content": "O Ohana CK-20 Concert Natural custa R$ 549,00."}
    ]
  }'
```

The router turns *"E tem desconto?"* into *"Does the Ohana CK-20 have an
active promotion, and what's the discounted price?"* before querying the
database.

**Example: an order**

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Qual o status do pedido 8?"}'
```

Orders are looked up by order number or tracking code. The assistant never
returns customers' names, phones or e-mails, and doesn't list orders or
customers in bulk.

**Errors**

| Status | When | Body |
|---|---|---|
| `422` | Invalid body: missing `query`, or a `history` role other than `user`/`assistant` | FastAPI validation details |
| `500` | Unexpected failure in the workflow | `{"detail": "<ErrorType>: <message>"}` |

Problems inside the workflow usually **don't** produce a `500`. If the LLM
provider or the database is unavailable, the agents report the error
internally and `final_answer` contains a polite fallback message, with
`status: "success"`. Check the logs to tell the two cases apart.

---

### `GET /logs/llm-calls?limit=100`

Returns the latest events from `logs/llm_calls.jsonl`. Despite the name, this
includes **all event types** (`llm_call`, `routing_decision`,
`agent_execution`, `synthesis`, `error`), because they share one log file.
See [LOGGING.md](LOGGING.md) for each event's fields.

| Parameter | Default | Description |
|---|---|---|
| `limit` | 100 | Maximum number of events, the most recent ones |

```json
{
  "logs": [
    {
      "timestamp": "2026-11-01T14:03:12.481022",
      "event_type": "llm_call",
      "provider": "openrouter",
      "model": "google/gemini-2.5-flash-lite",
      "agent": "classifier",
      "status": "success",
      "latency_ms": 812.4,
      "tokens": {},
      "prompt_length": 46,
      "response_length": 131,
      "prompt": "Qual o status do pedido 8?",
      "response": "{\"classifications\": [{\"source\": \"store_database\", \"query\": \"Qual o status do pedido 8?\"}]}",
      "error": null
    }
  ],
  "total": 214,
  "limit": 100
}
```

---

### `GET /logs/stats`

Aggregates the `llm_call` events. Only the **router** (`classifier`) and the
**synthesizer** log their LLM calls, so those are the agents that appear.

```json
{
  "total_llm_calls": 42,
  "avg_latency_ms": 950.34,
  "calls_by_agent": {
    "classifier": 21,
    "synthesizer": 21
  }
}
```

---

### `GET /logs/routing-decisions?limit=50`

Returns the latest routing decisions: which agents were chosen for each
question. Useful to debug wrong answers, which often start with a wrong
route.

```json
{
  "decisions": [
    {
      "timestamp": "2026-11-01T14:03:12.480511",
      "event_type": "routing_decision",
      "user_query": "Meu pedido 5 chegou com defeito, posso trocar?",
      "agents_selected": ["store_database", "question_answerer"],
      "num_agents": 2
    }
  ],
  "total": 21,
  "limit": 50
}
```

---

## Postman collection

Import [`docs/postman_collection.json`](postman_collection.json) into Postman.
It uses one variable, `base_url` (default `http://localhost:8000`), and has
three folders:

1. **Health & Status**: health check.
2. **Queries**: a promotions question, an order status question, and a
   follow-up question with `history`.
3. **Logs & Monitoring**: the three log endpoints.

---

## Notes

- **No authentication.** The API is meant to run behind another service or
  on a private network. Don't expose it publicly as is: anyone could spend
  your OpenRouter credits and look up orders by number.
- **CORS** isn't configured. A browser front-end on another origin would
  need FastAPI's `CORSMiddleware`.
- **Docker vs. local logs.** In Docker, the API reads the logs in the
  `app-logs` volume; locally, it reads `./logs`.
