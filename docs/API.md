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


---

### `POST /query`

Runs the full workflow (router → agents → synthesizer) and returns the
answer.


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



---

### `GET /logs/stats`

Aggregates the `llm_call` events. Only the **router** (`classifier`) and the
**synthesizer** log their LLM calls, so those are the agents that appear.


---

### `GET /logs/routing-decisions?limit=50`

Returns the latest routing decisions: which agents were chosen for each
question. Useful to debug wrong answers, which often start with a wrong
route.


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
- **Concurrency.** Requests are answered in parallel: the endpoints doing
  blocking work are sync functions, which FastAPI runs in a thread pool.
- **CORS** isn't configured. A browser front-end on another origin would
  need FastAPI's `CORSMiddleware`.
- **Docker vs. local logs.** In Docker, the API reads the logs in the
  `app-logs` volume; locally, it reads `./logs`.
