# Docker

Docker Compose can run the whole system (database, data loading, API and
chat) with one command. It's the easiest way to try the project or to hand
it to someone else. For day-to-day development, running the app from a
virtualenv with only PostgreSQL in Docker is usually faster (see
[Local development](#local-development-only-postgresql-in-docker)).

Files: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `Makefile`.

---

## Quick start

```bash
cp .env.example .env        # then set OPENROUTER_API_KEY in .env
make docker-up              # = docker compose up -d --build
```

| Service | URL |
|---|---|
| Chat (Streamlit) | http://localhost:8501 |
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| API docs (ReDoc) | http://localhost:8000/redoc |

The **first start takes a few minutes**: the image is built, and the
embedding model is downloaded once. To follow the progress:

```bash
docker compose logs -f init
```

Only the chat (without the API):

```bash
docker compose up -d --build frontend
```

---

## Services

```
postgres ──healthy──► init ──completed──► api        (port 8000)
                                 └──────► frontend   (port 8501)
```

| Service | Image | What it does |
|---|---|---|
| `postgres` | `postgres:16-alpine` | The store database. Has a health check (`pg_isready`), so the others wait until it accepts connections |
| `init` | the app image | **One-shot setup**: loads the CSVs into PostgreSQL and creates the read-only role (`create_sql_db`), then builds the vector store **if it's empty** (`create_db --if-empty`), then exits |
| `api` | the app image | FastAPI on port 8000. Starts only after `init` finished successfully |
| `frontend` | the app image | Streamlit on port 8501, with a health check. Starts only after `init`. It runs the agents itself, so it doesn't depend on `api` |

`api`, `frontend` and `init` share the same image (`rag-customer-service:latest`),
built from the `Dockerfile`. They share their configuration through a YAML
anchor (`x-app`) at the top of `docker-compose.yml`.

`init` runs on **every** `docker compose up`. Reloading the tables is fast and
keeps the database in sync with the CSVs. The vector store is only built the
first time.

---

## The image (`Dockerfile`)

1. `python:3.12-slim`, plus `gcc`.
2. `pip install -r requirements.txt`.
3. Downloads NLTK's `punkt_tab` sentence tokenizer into the image
   (`NLTK_DATA=/usr/local/share/nltk_data`). The build **fails** if this
   download fails, instead of producing an image that breaks later.
4. Copies the project. `.dockerignore` leaves out `.env`, `venv/`,
   `chroma_db/`, `logs/`, `tests/`, `docs/` and caches, so secrets and local
   state never end up in the image.
5. Sets `FASTEMBED_CACHE_PATH=/models`, where the embedding model is stored.

Behind an HTTP proxy that intercepts TLS, NLTK refuses to download by
default. Build with:

```bash
docker compose build --build-arg NLTK_ALLOW_PROXIED_URLOPEN=1
```

---

## Configuration

All settings come from **`.env`** (through `env_file`), so anything you set
there (`OPENROUTER_API_KEY`, `ROUTER_LLM_MODEL`, …) reaches the containers.
`.env` is optional for Compose, but without `OPENROUTER_API_KEY` every answer
is the fallback message.

Compose then overrides three values for the containers:

| Variable | Value in the containers | Why |
|---|---|---|
| `DATABASE_URL` | `postgresql://rag:rag@postgres:5432/store` | Inside Docker, the database is reached by its service name (`postgres`) on the internal network, on its internal port 5432. The `localhost` URL in your `.env` is for the local setup |
| `CHROMA_DB_PATH` | `/app/chroma_db` | The vector store volume |
| `FASTEMBED_CACHE_PATH` | `/models` | The model cache volume |

Docker-specific settings (put them in `.env`):

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_PORT` | `5432` | Port on **your machine** for PostgreSQL. Change it if another PostgreSQL already uses 5432 |
| `API_PORT` | `8000` | Port on your machine for the API |
| `FRONTEND_PORT` | `8501` | Port on your machine for the chat |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `rag` / `rag` / `store` | Database owner account and database name |

---

## Volumes: where the data lives

| Volume / mount | Path in container | Contents |
|---|---|---|
| `./data` (bind mount) | `/app/data` | CSVs and policy PDF. Edits apply on the next `up`, without rebuilding |
| `postgres-data` | `/var/lib/postgresql/data` | The database |
| `chroma-data` | `/app/chroma_db` | The vector store |
| `model-cache` | `/models` | The embedding model (downloaded once) |
| `app-logs` | `/app/logs` | `llm_calls.jsonl` and `trace.log` |

Docker's vector store and logs are **separate** from the local `chroma_db/`
and `logs/` folders. That's deliberate: if containers (which run as root)
wrote into your project folders, the files would be owned by root, and the
local setup could no longer write or delete them.

Named volumes survive `docker compose down`. They're only deleted by
`docker compose down -v`.

---

## Common tasks

| Task | Command |
|---|---|
| Start everything (and rebuild if code changed) | `make docker-up` |
| Stop everything (data is kept) | `make docker-down` |
| Follow all logs | `make docker-logs` |
| Follow one service | `docker compose logs -f frontend` |
| See status | `docker compose ps -a` |
| Rebuild the vector store (after changing the PDF) | `docker compose run --rm init python -m src.utils.create_db` |
| Reload the database (after changing a CSV) | `docker compose run --rm init python -m src.utils.create_sql_db`, or just `make docker-up` |
| Open a shell in a container | `docker compose exec api bash` |
| Read the app logs | `docker compose exec api tail -n 50 logs/llm_calls.jsonl` |
| Query the database | `docker compose exec postgres psql -U rag -d store` |
| Delete everything, including data volumes | `docker compose down -v` |

After changing **code**, rebuild: the code is copied into the image, so
changes don't apply until `make docker-up` runs again.

---

## Local development (only PostgreSQL in Docker)

```bash
make db-up          # docker compose up -d postgres
make load-db        # from the venv: CSVs -> PostgreSQL, PDF -> local ./chroma_db
streamlit run src/front-end/interface.py
```

In this mode, `.env`'s `DATABASE_URL` must use `localhost` and the
`POSTGRES_PORT` you chose, for example
`postgresql://rag:rag@localhost:5433/store` with `POSTGRES_PORT=5433`.

Don't run the local chat and the Docker `frontend` at the same time on the
same port (8501). Stop one, or set `FRONTEND_PORT`.

---

## Troubleshooting

**`Bind for 0.0.0.0:5432 failed: port is already allocated`**
Another PostgreSQL (installed on the machine, or another container) uses
port 5432. Set `POSTGRES_PORT=5433` in `.env` (and use 5433 in `DATABASE_URL`
for local runs), then `docker compose up -d --force-recreate postgres`. Check
the mapping with `docker compose ps postgres`: it should show
`0.0.0.0:5433->5432/tcp`. The same applies to 8000 and 8501 with `API_PORT`
and `FRONTEND_PORT`.

**`password authentication failed for user "rag"` (local runs)**
The script reached a different PostgreSQL than the Docker one, usually
because `DATABASE_URL` still points at port 5432 while the container is on
another port. Check `.env`, and also `echo $DATABASE_URL`: a variable
exported in the shell takes priority over `.env`.

**`password authentication failed for user "store_reader"`**
The read-only role doesn't exist yet. Run the loader (`make load-db` locally;
in Docker, `init` creates it).

**`api` or `frontend` don't start**
They wait for `init`. Check `docker compose logs init`. Usually the database
isn't reachable, or the model download failed (no internet access).

**Every answer is "Desculpe, não consegui processar sua mensagem agora…"**
The LLM calls are failing: check `OPENROUTER_API_KEY` in `.env`, then
`docker compose logs api` or the log file for the error.

**The first question is very slow**
Each process loads the embedding model on its first policy question.
`model-cache` avoids re-downloading it, but loading still takes a few
seconds.
