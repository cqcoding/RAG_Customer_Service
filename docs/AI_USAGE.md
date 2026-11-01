# How AI was used in this project

This project was built with the help of an AI coding assistant: **Claude**,
by Anthropic, used through **Claude Code**. This document explains what
the AI did, what I did, and the workflow that kept me in control of the code.

In short: the AI worked as a **pair programmer for diagnosis, fixes, tests
and improvements**. I set the starting point and the direction, ran the
system myself, reviewed every change, and integrated it by hand. I didn't
trust its output blindly, and I didn't ask it to build the project from
scratch.

---

## 1. Starting point: my own base project

The project didn't start from an empty folder or from AI-generated code. It
started from **a previous personal project of mine, a RAG financial
analyst**: a LangGraph orchestrator with agents for metric extraction,
sentiment analysis and Q&A over financial filings, with an OpenRouter client
with model fallback, structured logging, a FastAPI API, a Streamlit
interface and Docker setup.

I adapted that base to this challenge manually: the repository structure and
branches (`setup`, `database`, `agents`, `tests`, `docs`), the challenge data,
the configuration, the choice of LLM models (including the cost and
capability comparison in [ARCHITECTURE.md §9](ARCHITECTURE.md#9-llms-and-the-openrouter-client)),
and many smaller necessities along the way.

---

## 2. The workflow

Each improvement went through the same loop:

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 1. I run the system on my machine, and see an output, error or gap  │
 │ 2. I describe it to the AI, with the real output, and the branch     │
 │ 3. The AI reads the code, explains the cause, and proposes a fix     │
 │ 4. The AI implements it and tests it in its own environment          │
 │ 5. The AI hands it over as a git patch, saying what it couldn't test │
 │ 6. I review it, apply it by hand, and run it myself                  │
 │ 7. I commit, push and merge myself, then back to step 1              │
 └──────────────────────────────────────────────────────────────────────┘
```

### Step 1–2: real outputs, not descriptions

I shared what actually happened: terminal output, stack traces, failing test
reports. For example, the first problem I brought was the output of the
vector store build, which showed `Docs: 14` and `Chunks: 107` and made me
suspect that my six CSV files weren't being handled properly.

### Step 3: understanding before changing

For each problem, the AI first explained the cause, so I could judge the fix.
In the CSV case, it showed that the files were loaded as raw text and cut in
the middle of rows, with an example of a broken chunk. When there were
several possible solutions, it presented options with trade-offs, and **I
chose**. For example, between joining the tables before embedding them, or
moving them into a database queried with SQL, I chose the PostgreSQL option
because it fit my architecture better.

### Step 4: tested before handed over

The AI worked in an isolated cloud environment with its own copy of the
repository. There it ran the unit tests, a real PostgreSQL loaded with the
challenge data, the API, the Streamlit app in a real browser, and real
Docker builds. It also wrote tests for its own changes.

Some things it couldn't run there: the real LLM (no API key in that
environment) and the embedding model download (blocked by the environment's
network). In those cases it used mocks or fake embeddings, and **said
explicitly what remained untested**, so I knew what I had to verify myself.

### Step 5–7: I integrate, by hand

- **The AI had no access to my GitHub repository and no access to my machine.**
  Every change reached my code only because I applied it.
- Changes came as **git patches**, one per topic, small enough to review.
- I applied them with `git apply`, ran them on my machine, and committed,
  pushed and merged them myself, sometimes adjusting them first. For example, I
  removed many explanatory comments, deleted helper scripts and files I didn't
  need, and changed details of the UI.
- When the AI's patch didn't match my branch (because I had changed `main`
  in the meantime), it didn't force anything: it compared its version with
  my branch, kept my changes, and rebuilt the patch on top of them.

---

## 3. Who decided what

**Decisions I made:**

- Using my financial-analyst project as the base.
- Moving the CSV data to PostgreSQL with a SQL agent, among the options
  presented.
- Which improvements to make, and in what order.
- **Not** enforcing customer authentication for now.
- Removing the upload endpoint.
- The LLM models and the fallback strategy.
- What goes into each branch, and when to merge.
- The final review of every change.

**Work done with the AI's help:**

- Diagnosing problems from real outputs.
- Implementing the SQL agent, the schema, the loader and the SQL safety layers.
- Conversation memory, the faster router, bug fixes and cleanup.
- Building customer authentication, then removing it cleanly when I asked.
- Tests at three levels, including the retry and fallback logic.
- The Docker setup.
- Writing and updating this documentation from the code.

Two examples of me changing direction during the work:

- **Authentication.** The AI started implementing customer authentication
  with PostgreSQL row-level security. Mid-way, I decided it wasn't needed at
  this stage and asked to drop it. It was removed, and the design is recorded
  in [ARCHITECTURE.md §12.2](ARCHITECTURE.md#122-customer-authentication-built-then-deliberately-removed)
  in case it's needed later.
- **Upload endpoint.** While the documentation was being written, I decided
  the project doesn't need file uploads, and the endpoint and its leftovers
  were removed.

---

## 4. Verification: not trusting blindly

AI-written code can look right and still be wrong. These are the practices
that made the difference:

- **I ran everything myself.** Every patch was applied and run on my machine,
  and the behavior tests with the real LLM ran on my machine.
- **Tests as the contract.** Every change came with tests, and the test
  suite has a level that only I could run (the real LLM). That level caught a
  real bug: asked *"Qual a capital da França?"*, the assistant answered
  *"A capital da França é Paris"* before declining. I reported the failing
  test, and the fix (a strict prompt when no agent runs) came with a unit
  test.
- **Facts, not wording.** The behavior tests check numbers, codes and leaks,
  not sentences, so they stay meaningful even though the model's wording
  varies.
- **Explicit limits.** The AI was expected to say what it couldn't verify,
  instead of claiming success. Its reports listed what had been tested,
  where, and what was left to me.
- **Small, reviewable changes**, delivered as patches I could read before
  applying.

---

## 5. Examples from the process

### Problems I found by running the system

| What I saw | Cause | Fix |
|---|---|---|
| `Docs: 14, Chunks: 107`: were my CSVs processed? | CSVs loaded as raw text, cut mid-row, headers lost | First one document per row, then PostgreSQL + SQL agent |
| `Bind for 0.0.0.0:5432 failed: port is already allocated` | Another PostgreSQL on my machine | Configurable `POSTGRES_PORT` |
| `password authentication failed for user "rag"` | `DATABASE_URL` still pointed at the other PostgreSQL | Configuration fix, documented in troubleshooting |
| `git apply` failed on `main` | I had changed `main` since the patch was made | Patch rebuilt on top of my `main` |
| `ModuleNotFoundError: No module named 'src'` in all tests | I had deleted `tests/conftest.py`, which set up the import path | `pythonpath = .` in `pytest.ini` |
| Behavior test: "Paris" in an off-topic answer | The synthesizer filled the gap with general knowledge | Strict no-results prompt + unit test |

### Problems the AI found by reading the code

While working on the problems above, the AI also reported issues I hadn't hit
yet. Each one was explained, then fixed with a test where possible:

| Issue | Effect |
|---|---|
| The orchestrator referenced agents that no longer existed | The app crashed on import |
| The logger sliced dicts as if they were strings | Every successful agent run was logged and returned as an error |
| A prompt variable in the Q&A agent was never defined | Policy questions could never succeed |
| The router didn't handle ```` ```json ```` fences | Fenced replies silently routed nowhere |
| `requirements.txt` was missing four packages | The Docker image would crash on import |
| The vector store build appended instead of rebuilding | Each rebuild duplicated every chunk |
| The log viewer assumed every log line was an LLM call | Option 1 of the viewer crashed |
| `.env.example` suggested settings the code never reads | One of them would have broken the vector store |

---

## 6. What this means for the code

- The architecture and the data decisions are mine, built on my own previous
  project.
- A significant part of the implementation of the changes since then (the
  SQL agent and its safety layers, conversation memory, the Docker setup, the
  tests, and this documentation) was written with the AI, then reviewed,
  applied, run and in places modified by me.
- Every change in the repository passed through my review and my machine
  before being committed.
