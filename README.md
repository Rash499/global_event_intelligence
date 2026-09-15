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
.venv\Scripts\Activate.ps1
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

## 2. Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal, normally:
http://localhost:5173

## 3. Seed demo data

The backend has demo events so the UI works immediately.

```bash
curl -X POST http://localhost:8000/api/events/seed
```

On Windows PowerShell, you can instead open:
http://localhost:8000/docs
and execute `POST /api/events/seed`.

## 4. Collect real news

Run:

```bash
curl -X POST http://localhost:8000/api/ingestion/run
```

This collects GDELT news and RSS feeds, normalizes articles, creates event records, and stores them.

You can also use Swagger:
http://localhost:8000/docs

## 5. Optional local AI with Ollama

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

## 6. API examples

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

## Project structure

```text
global-event-intelligence/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── ai/
│   │   ├── database/
│   │   ├── ingestion/
│   │   ├── processing/
│   │   └── main.py
│   ├── data/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── types/
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## Notes

- News providers have their own terms, rate limits, and content licensing rules.
- Store metadata and source URLs rather than copying entire copyrighted articles.
- AI output is an analysis layer and should not be treated as verified fact without source review.
