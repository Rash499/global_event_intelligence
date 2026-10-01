![alt text](image.png)


# Global Event Intelligence

An MVP AI-powered global news/event intelligence map.

## Architecture

News Sources (GDELT + RSS)
        |
        v
FastAPI ingestion service
        |
        +--> normalization/deduplication
        |
        +--> optional Ollama AI analysis
        |
        v
SQLite database (easy local setup)
        |
        v
REST API
        |
        v
React + TypeScript globe/dashboard frontend

This MVP deliberately uses SQLite first so it can run without PostgreSQL.
The database layer can later be upgraded to PostgreSQL/PostGIS.

## Requirements

- Python 3.11+
- Node.js 20+
- npm
- Internet connection for GDELT/RSS ingestion
- Optional: Ollama for local AI analysis

## 1. Backend

```bash
cd backend
python -m venv .venv
```

Windows PowerShell:
```powershell
.\venv\Scripts\Activate.ps1
```

Windows CMD:
```cmd
.venv\Scripts\activate
```

Linux/macOS:
```bash
source .venv/bin/activate
```

Install:
```bash
pip install -r requirements.txt
```

Start:
```bash
uvicorn app.main:app --reload --port 8000
```

API:
- http://localhost:8000
- http://localhost:8000/docs
- http://localhost:8000/api/health

The API creates `backend/data/events.db` automatically.

API routes are organized by responsibility under `backend/app/api/`:

- `health.py` - health check
- `events.py` - event queries, details, and demo seed data
- `countries.py` - country events and intelligence
- `statistics.py` - global statistics
- `ingestion.py` - news ingestion
- `routes.py` - combines the API routers

## 2. Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal, normally:
http://localhost:5173

The first screen provides sign-in and account registration. After signing in,
the event map and dashboard open. Saved sessions remain active for up to 30
days, and you can sign out from the app header.

## 3. Accounts and event interactions

Register with a display name, email address, and password of at least 8
characters. Only authenticated accounts can create likes or comments. Comment
authors are taken from the registered display name, and accounts can delete
only their own comments. Event and comment feeds remain readable without an
account.

Authentication endpoints:

- `POST /api/auth/register` - create an account and start a session
- `POST /api/auth/login` - sign in and start a session
- `GET /api/auth/me` - return the current account
- `POST /api/auth/logout` - revoke the current session

Passwords are stored as scrypt hashes; session tokens are stored as hashes.
Email verification and password recovery are not currently included.

Events are retained for seven days based on their event time. Expired events
and their likes, comments, and article links are purged when the backend starts
and then every minute while it is running. The event dashboard refreshes its
feed every minute so removed events disappear automatically.

## 4. Seed demo data

The backend has demo events so the UI works immediately.

```bash
curl -X POST http://localhost:8000/api/events/seed
```

On Windows PowerShell, you can instead open:
http://localhost:8000/docs
and execute `POST /api/events/seed`.

## 5. Collect real news

The frontend loads saved event history when it opens, then automatically runs
news collection once for that page load. When collection finishes, the event
feed refreshes automatically. You can also use the **Collect News** button to
run collection again at any time.

When collection creates events, the app shows a dismissible alert with the
number of new events detected. The alert closes automatically after eight
seconds. If no events are created, the collection status reports that no new
events were detected. Duplicate articles are skipped by the ingestion service.

To collect directly from the backend, run:

```bash
curl -X POST http://localhost:8000/api/ingestion/run
```

This collects available source articles, analyzes them, and stores newly
created event records.

You can also use Swagger:
http://localhost:8000/docs

## 6. Optional local AI with Ollama

Install Ollama separately, then pull a model, for example:

```bash
ollama pull llama3.2:3b
```

Start Ollama if it is not already running, then set:

Windows PowerShell:
```powershell
$env:OLLAMA_ENABLED="true"
```

Linux/macOS:
```bash
export OLLAMA_ENABLED=true
```

Restart FastAPI.

The ingestion service will ask the local model to classify/summarize candidate articles. If Ollama is unavailable, the application automatically falls back to deterministic analysis, so the MVP still works.

## 7. API examples

Latest events:
```text
GET /api/events/latest?limit=50
```

Filter:
```text
GET /api/events?category=natural_disaster&min_importance=7
```

Country:
```text
GET /api/countries/JP
```

Statistics:
```text
GET /api/statistics/global
```

Global Intelligence Assistant (Phase 3):
```text
POST /api/ai/query        {"question": "What happened in Japan recently?"}
GET  /api/ai/status
GET  /api/ai/suggestions
POST /api/ai/index        {"force": false, "limit": 300}
```

## 8. Global Intelligence Assistant (Phase 3)

The assistant answers questions strictly from indexed platform data. Every answer
carries numbered evidence records and source links that were verified against the
SQLite `events`/`articles` tables, so it cannot invent citations. If the model,
the embedding provider or the vector store is unavailable, the API returns a
structured status (`llm_unavailable`, `insufficient_data`, `out_of_scope`,
`ungrounded`) instead of failing, and Phases 1/2 keep working unchanged.

### 8.1 Setup

```bash
# 1. Chat model used for grounded answers
ollama pull llama3.2:3b

# 2. Embedding model used for retrieval
ollama pull nomic-embed-text
```

Optional semantic vector store (the default `auto` mode uses SQLite when Qdrant
is unreachable):

```bash
docker run -p 6333:6333 qdrant/qdrant
```

Enable the assistant in the backend environment:

```bash
# backend/.env
RAG_ENABLED=true
RAG_EMBEDDING_PROVIDER=ollama          # ollama | hashing (offline, no server needed)
RAG_VECTOR_STORE=auto                  # auto | sqlite | qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=global_event_intelligence

OLLAMA_CHAT_MODEL=llama3.2:3b          # falls back to OLLAMA_MODEL
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_REQUEST_TIMEOUT_SECONDS=180     # small local models can be slow
OLLAMA_MAX_TOKENS=512                  # bounds answer length/time on small models
```

Environment variables for local development and tests only:

```bash
RAG_EMBEDDING_PROVIDER=hashing         # deterministic offline embedder
RAG_VECTOR_STORE=sqlite                # built-in lexical/vector search index
```

### 8.2 Indexing

The index is incremental: documents are hashed, unchanged documents are skipped,
and changed documents are re-embedded. Indexing runs in the background:

- once shortly after backend startup (`RAG_INDEX_ON_STARTUP`, default `true`,
  delayed by `RAG_INDEX_STARTUP_DELAY_SECONDS`);
- after each successful news ingestion cycle;
- on demand with `POST /api/ai/index` or the **Re-index** button in the
  assistant UI.

### 8.3 Configuration reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `RAG_ENABLED` | `true` | Master switch for the assistant. |
| `RAG_EMBEDDING_PROVIDER` | `ollama` | `ollama` (semantic) or `hashing` (offline). |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model. |
| `RAG_EMBEDDING_DIMENSIONS` | `768` | Vector width. |
| `RAG_VECTOR_STORE` | `auto` | `auto`, `sqlite` or `qdrant`. |
| `QDRANT_URL` / `QDRANT_API_KEY` | `http://localhost:6333` | Qdrant connection. |
| `QDRANT_COLLECTION` | `global_event_intelligence` | Collection name. |
| `RAG_TOP_K` | `8` | Evidence records per answer. |
| `RAG_MAX_CONTEXT_DOCUMENTS` | `10` | Records placed in the prompt. |
| `RAG_MAX_CONTEXT_CHARACTERS` | `12000` | Prompt budget for evidence. |
| `RAG_VECTOR_WEIGHT` / `RAG_LEXICAL_WEIGHT` | `0.6` / `0.4` | Hybrid scoring mix. |
| `RAG_MIN_RELEVANCE` | `0.05` | Below this the answer is `insufficient_data`. |
| `RAG_INDEX_ON_STARTUP` | `true` | Index after backend start. |
| `RAG_INGESTION_INDEX_LIMIT` | `25` | Documents indexed after a news cycle. |
| `RAG_INDEX_STARTUP_PAUSE_SECONDS` | `2.0` | Pause between startup batches. |
| `RAG_AUTO_INDEX_ON_QUERY` | `true` | Top up the index when a query finds nothing. |
| `RAG_AUTO_INDEX_BACKGROUND` | `true` | Run that top-up off the request path. |
| `RAG_STATUS_CACHE_TTL_SECONDS` | `5.0` | `/api/ai/status` cache (the UI polls it). |
| `RAG_INDEX_BATCH_LIMIT` | `300` | Documents per indexing run. |

### 8.3.1 Performance notes

Indexing is deliberately kept off the critical path, because it shares the same
model server as the assistant:

- only one indexing run happens at a time (startup, ingestion and query top-ups
  are mutually exclusive);
- a news cycle indexes a small batch (`RAG_INGESTION_INDEX_LIMIT`) because only a
  few events are new, and the rest is picked up later;
- startup indexing pauses between batches and yields to the event loop;
- the pre-query top-up runs in the background, so an answer is never delayed by
  it;
- the optional Qdrant probe is cached (and fails fast on a closed port), the
  SQLite vector store keeps a decoded embedding matrix in memory, and
  `/api/ai/status` is briefly cached.

### 8.4 Using it

Open **Global Intelligence** in the app header (or `/` → assistant view). The
status chips show whether the assistant, the chat model, the embedding provider,
the vector store and the index are ready. Suggested questions include ones
derived from the current database contents.

```bash
curl -X POST http://localhost:8000/api/ai/query \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"What happened in Japan recently?\"}"
```

### 8.5 Tests

```bash
cd backend
python -m pytest tests -q
```

`tests/test_rag.py` never needs a running Ollama or Qdrant server: it uses the
offline hashing embedder, the SQLite vector store and an unreachable Ollama URL
to verify graceful degradation. Every test runs against a temporary database.
`tests/eval_dataset.json` holds the curated retrieval/scope evaluation set; the
report test prints scope accuracy and retrieval coverage.

## Project structure

```text
global-event-intelligence/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── ai.py
│   │   │   ├── countries.py
│   │   │   ├── events.py
│   │   │   ├── health.py
│   │   │   ├── ingestion.py
│   │   │   ├── routes.py
│   │   │   └── statistics.py
│   │   ├── rag/
│   │   │   ├── documents.py
│   │   │   ├── embeddings.py
│   │   │   ├── indexer.py
│   │   │   ├── llm.py
│   │   │   ├── models.py
│   │   │   ├── prompts.py
│   │   │   ├── query.py
│   │   │   ├── retriever.py
│   │   │   ├── schema.py
│   │   │   ├── service.py
│   │   │   └── vector_store.py
│   │   ├── ai/
│   │   ├── database/
│   │   ├── ingestion/
│   │   ├── processing/
│   │   └── main.py
│   ├── tests/
│   │   ├── eval_dataset.json
│   │   ├── test_intelligence.py
│   │   └── test_rag.py
│   ├── data/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── assistant/
│   │   ├── services/
│   │   ├── styles/
│   │   │   └── assistant/
│   │   ├── App.jsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## Notes

- News providers have their own terms, rate limits, and content licensing rules.
- Store metadata and source URLs rather than copying entire copyrighted articles.
- AI output is an analysis layer and should not be treated as verified fact without source review.


