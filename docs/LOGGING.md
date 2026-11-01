# Logging

Every question leaves a trail: which agents the router chose, what each agent
returned, each LLM call (model, latency, prompt, response) and the final
answer. This is the main tool for understanding a wrong answer or a slow one.

Files: `src/utils/logger.py`, `src/utils/view_logs.py`, plus the log
endpoints in `src/api/main.py`.

---

## Where logs go

`StructuredLogger` (`src/utils/logger.py`) writes **every event** as one line
of JSON to three places:

| Output | Format | Use |
|---|---|---|
| `logs/llm_calls.jsonl` | One JSON object per line | Machine-readable: read by the API endpoints and the viewer |
| `logs/trace.log` | Timestamp, level, then the same JSON | Human-readable, with timestamps |
| Console | Same as `trace.log` | Live view while the app runs (and in `docker compose logs`) |

`logs/` is created automatically in the current directory, and is
git-ignored. In Docker it is the `app-logs` volume (see [DOCKER.md](DOCKER.md)).

Despite its name, `llm_calls.jsonl` contains **all** event types, not only
LLM calls. Filter on `event_type`.

---

## Event types

A typical question produces this sequence:

```
routing_decision  →  llm_call (classifier)  →  agent_execution (×1 or 2)  →  synthesis  →  llm_call (synthesizer)
```

### `routing_decision`

Logged by the router after a successful classification.

```json
{
  "timestamp": "2026-11-01T14:03:12.480511",
  "event_type": "routing_decision",
  "user_query": "Meu pedido 5 chegou com defeito, posso trocar?",
  "agents_selected": ["store_database", "question_answerer"],
  "num_agents": 2
}
```

`agents_selected` is empty for small talk and off-topic messages.

### `llm_call`

Logged for the **router** (`agent: "classifier"`) and the **synthesizer**
(`agent: "synthesizer"`). The agents' own LLM calls aren't logged as
`llm_call`; their inputs and outputs appear in `agent_execution`.

```json
{
  "timestamp": "2026-11-01T14:03:12.481022",
  "event_type": "llm_call",
  "provider": "openrouter",
  "model": "google/gemini-2.5-flash-lite",
  "agent": "classifier",
  "status": "success",
  "latency_ms": 812.4,
  "tokens": {},
  "prompt_length": 134,
  "response_length": 131,
  "prompt": "Conversation so far:\nCustomer: Quanto custa o Ohana CK-20?\n…\nCurrent message: e tem desconto?",
  "response": "{\"classifications\": [{\"source\": \"store_database\", …}]}",
  "error": null
}
```

- `model` is the model that actually answered, so it shows when a fallback
  model was used.
- `prompt` and `response` are cut to 500 characters; `prompt_length` and
  `response_length` are the full sizes.
- For the router, `prompt` is the conversation excerpt plus the current
  message. For the synthesizer, it's the agents' results.
- `tokens` is always empty: OpenRouter's token counts aren't read yet.
- On failure, `status` is `"error"` and `error` holds the message.

### `agent_execution`

Logged for each agent run (`question_answerer`, `store_database`).

```json
{
  "timestamp": "2026-11-01T14:03:13.902877",
  "event_type": "agent_execution",
  "agent": "store_database",
  "status": "success",
  "latency_ms": 1421.3,
  "input": "Qual o status, data de entrega e itens do pedido 5?",
  "output": "{\"query\": \"Qual o status…\", \"status\": \"success\", \"sql\": \"SELECT o.status, …",
  "error": null
}
```

- `input` is the agent's sub-question, which may differ from the user's
  words (see [ARCHITECTURE.md §5.3](ARCHITECTURE.md#53-the-router-classify_query)).
- `output` is the agent's result as JSON, cut to 200 characters. For
  `store_database` it starts with the generated SQL, which is usually what you
  need when an answer is wrong.
- `status` is `"error"` when the agent reported an error (for example, the
  SQL failed twice) or crashed.

### `synthesis`

```json
{
  "timestamp": "2026-11-01T14:03:15.120034",
  "event_type": "synthesis",
  "user_query": "Meu pedido 5 chegou com defeito, posso trocar?",
  "results_aggregated": 2,
  "final_answer": "Seu pedido 5 (Crafter D-8 Dreadnought Natural) consta como entregue…",
  "latency_ms": 1217.6
}
```

`final_answer` is cut to 300 characters.

### `error`

Logged by the API when `/query` raises, with the full stack trace and the
request context.

```json
{
  "timestamp": "…",
  "event_type": "error",
  "error_type": "OperationalError",
  "message": "connection failed: …",
  "stack_trace": "Traceback (most recent call last): …",
  "context": {"query": "…", "latency_ms": 5012.3}
}
```

---

## Reading the logs

### Interactive viewer

```bash
python src/utils/view_logs.py
```

Run it from the project root (it reads `./logs`). Options:

1. **LLM calls**: model, agent, status, latency, and the start of the prompt
   and response of each call.
2. **Agent executions**: the `agent_execution` lines from `trace.log`.
3. **Routing decisions**: question → agents chosen.
4. **Statistics**: number of LLM calls, average latency, calls per agent.
5. **Everything** above.

### API endpoints

`GET /logs/llm-calls`, `GET /logs/routing-decisions` and `GET /logs/stats`
return the same information as JSON. See [API.md](API.md#get-logsllm-callslimit100).

### Command line

```bash
# Last routing decisions
grep '"routing_decision"' logs/llm_calls.jsonl | tail -n 5

# SQL generated for recent questions (requires jq)
grep '"store_database"' logs/llm_calls.jsonl | jq -r '.input + "  →  " + .output' | tail -n 5

# Failed events
grep '"status": "error"' logs/llm_calls.jsonl | tail -n 5
```

---

## Debugging a wrong answer

1. **Was it routed correctly?** Check the `routing_decision`. A store data
   question sent only to `question_answerer` (or the reverse) explains most
   wrong answers. Fix it in the router prompt (`ROUTER_PROMPT`).
2. **Was the sub-question right?** Check the `agent_execution` `input`. For
   follow-ups, the router must have resolved references ("esse", "e o
   preço?") correctly.
3. **Was the data right?** For `store_database`, look at the SQL in
   `output`, and run it yourself in `psql`. Wrong SQL usually means a column
   comment in `schema.sql` is missing or unclear.
4. **Was the policy found?** For `question_answerer`, the `output` shows the
   answer and the sources. If it says it couldn't find the information, the
   retrieval missed the right chunk.
5. **Did the synthesizer change the facts?** Compare the agents' outputs
   with the `synthesis` `final_answer`.

---

## Privacy

The logs contain **customers' questions and the assistant's answers**,
including order details. Keep `logs/` out of git (it already is), restrict
access to it, and delete old logs. For production, consider logging prompt
lengths only, not prompt text.

---

## Not used yet: `src/utils/tracing.py`

`tracing.py` defines a `Tracer` context manager and a `@trace_llm_call`
decorator for automatic timing, but nothing in the code uses them yet. All
current logging goes through `StructuredLogger` directly.
