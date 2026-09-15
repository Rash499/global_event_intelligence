# Global Event Intelligence — System Architecture & Run Guide

## 1. Project Overview

Global Event Intelligence is an AI-powered global news/event intelligence application.

The main goal is to:

- Collect recent news from multiple sources.
- Detect important events.
- Classify events into meaningful categories.
- Identify the country and geographic location of an event.
- Generate a concise AI summary.
- Assign importance and confidence scores.
- Store structured events in a database.
- Display events on an interactive 3D Earth.
- Allow users to select countries/events and view additional details in a dashboard.

The system is designed so that the React frontend does not communicate directly with the AI model. The FastAPI backend handles ingestion, processing, AI analysis, database storage, and API delivery.

---

# 2. High-Level System Architecture

```text
                         +-------------------------+
                         |      NEWS SOURCES       |
                         |                         |
                         |  GDELT                  |
                         |  RSS Feeds              |
                         |  News APIs (future)     |
                         +------------+------------+
                                      |
                                      v
                         +-------------------------+
                         |     NEWS COLLECTOR      |
                         |        FastAPI          |
                         +------------+------------+
                                      |
                                      v
                         +-------------------------+
                         |     DEDUPLICATION       |
                         |                         |
                         | Remove duplicate/       |
                         | repeated articles       |
                         +------------+------------+
                                      |
                                      v
                         +-------------------------+
                         |       AI EVENT AGENT    |
                         |                         |
                         |  Event Detection        |
                         |  Classification         |
                         |  Country Detection      |
                         |  Location Extraction    |
                         |  Summarization          |
                         |  Importance Scoring     |
                         |  Confidence Scoring     |
                         +------------+------------+
                                      |
                                      v
                         +-------------------------+
                         |       EVENT DATABASE    |
                         |          SQLite         |
                         +------------+------------+
                                      |
                                      v
                         +-------------------------+
                         |       FASTAPI REST      |
                         |           API           |
                         +------------+------------+
                                      |
                         +------------+------------+
                         |                         |
                         v                         v
              +--------------------+    +----------------------+
              |    3D EARTH        |    | COUNTRY DASHBOARD    |
              |   React + Globe    |    |                      |
              | Event markers      |    | Event timeline       |
              | Importance         |    | Categories           |
              | Filters            |    | Statistics            |
              +--------------------+    | AI summaries         |
                                        +----------------------+
```

---

# 3. Technology Stack

## Frontend

- React
- TypeScript
- Vite
- `globe.gl`
- Axios
- React Router

The 3D Earth uses `globe.gl` for the higher-level globe API and point interaction callbacks.

## Backend

- Python
- FastAPI
- Uvicorn
- HTTPX
- Feedparser
- Pydantic Settings

## Database

- SQLite

SQLite is suitable for the initial MVP and local development. A future production version can migrate to PostgreSQL/PostGIS.

## AI

- Ollama
- Local LLM such as `llama3.2:3b` for initial development

The AI should return structured event information rather than only free-form text.

## Development

- Git / GitHub
- Docker (optional)
- Python virtual environment
- Windows development environment
- Optional Linux VM for later deployment

---

# 4. Backend Structure

```text
backend/
|
+-- app/
|   +-- api/
|   |   +-- routes.py
|   |
|   +-- ai/
|   |   +-- ollama.py
|   |   +-- prompts.py
|   |   +-- schemas.py
|   |   +-- event_analyzer.py
|   |
|   +-- database/
|   |   +-- db.py
|   |
|   +-- ingestion/
|   |   +-- gdelt.py
|   |   +-- rss.py
|   |   +-- service.py
|   |
|   +-- processing/
|   |   +-- analyzer.py
|   |   +-- deduplication.py
|   |   +-- clustering.py
|   |
|   +-- config.py
|   +-- main.py
|
+-- data/
+-- requirements.txt
+-- .env.example
+-- Dockerfile
```

The AI/processing files above represent the modular architecture as the project evolves. The current MVP already contains the main `ai`, `database`, `ingestion`, and `processing` areas.

---

# 5. Frontend Structure

```text
frontend/
|
+-- src/
|   +-- components/
|   |   +-- Globe.tsx
|   |
|   +-- pages/
|   |   +-- EarthPage.tsx
|   |   +-- CountryDashboardPage.tsx
|   |
|   +-- country/
|   |   +-- dashboardTypes.ts
|   |
|   +-- services/
|   |   +-- api.ts
|   |
|   +-- types.ts
|   +-- App.tsx
|   +-- main.tsx
|   +-- styles.css
|
+-- package.json
+-- tsconfig.json
+-- vite.config.ts
```

---

# 6. News-to-Globe Data Flow

```text
Article
   |
   v
Collect article
   |
   v
Normalize article
   |
   v
Check for duplicates
   |
   v
AI analysis
   |
   +-- Is it important?
   +-- Category
   +-- Country
   +-- Country code
   +-- Location
   +-- Latitude
   +-- Longitude
   +-- Summary
   +-- Importance
   +-- Confidence
   |
   v
Create structured Event
   |
   v
Save to SQLite
   |
   v
FastAPI API
   |
   v
React
   |
   v
3D Earth marker
```

---

# 7. AI Event Output

The AI should produce structured data similar to:

```json
{
  "is_major_event": true,
  "event_title": "Major earthquake strikes Japan",
  "category": "natural_disaster",
  "country": "Japan",
  "country_code": "JP",
  "location": "Japan",
  "latitude": 35.6762,
  "longitude": 139.6503,
  "importance": 9,
  "confidence": 0.94,
  "summary": "A major earthquake struck Japan, causing significant disruption."
}
```

The exact schema can evolve as more features are added.

---

# 8. Initial Event Categories

Start with a manageable category system:

```text
Politics
Conflict / War
Natural Disaster
Crime / Security
Economy
Technology
Science
Health
Environment
International
```

Additional categories can be added later if needed.

---

# 9. Importance Scoring

Use a 1–10 importance scale:

```text
10     Critical / global impact
9      Major international or national event
8      Major national event
7      Significant event
4–6    Moderate event
1–3    Minor event
```

Suggested frontend grouping:

```text
9–10  Critical
7–8   Major
4–6   Significant
1–3   Minor
```

---

# 10. Country Dashboard

The Earth page should remain focused on global visualization.

When a country is selected:

```text
3D Earth
   |
   | Click country
   v
Country Dashboard
```

The dashboard can contain information that would make the main Earth page too crowded:

```text
Country Overview
    |
    v
Event Activity
    |
    v
Latest Events
    |
    v
Event Timeline
    |
    v
Categories
    |
    v
Importance Distribution
    |
    v
AI Summaries
    |
    v
Related Countries
    |
    v
Sources
```

---

# 11. Current Backend API

The MVP provides endpoints such as:

```text
GET  /api/health
GET  /api/events
GET  /api/events/latest
GET  /api/events/{event_id}
GET  /api/countries/{country_code}
GET  /api/statistics/global

POST /api/events/seed
POST /api/ingestion/run
```

Swagger/OpenAPI:

```text
http://127.0.0.1:8000/docs
```

---

# 12. Windows Backend Setup

## Prerequisites

Install:

- Python 3.x
- Node.js
- npm
- Git
- Ollama

Ollama is required when using local AI functionality.

## Create and activate the virtual environment

Open PowerShell:

```powershell
cd D:\global_event_intelligenceackend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

After activation, the terminal should show:

```text
(.venv) PS D:\global_event_intelligenceackend>
```

## Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Start FastAPI

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

Expected result:

```text
Uvicorn running on http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

---

# 13. Start Ollama

Install Ollama from its official website.

Verify:

```powershell
ollama --version
```

Download the initial model:

```powershell
ollama pull llama3.2:3b
```

Run the model:

```powershell
ollama run llama3.2:3b
```

Ollama normally exposes its local API at:

```text
http://localhost:11434
```

The FastAPI backend communicates with Ollama through this local API.

---

# 14. Start the Frontend

Open a second PowerShell terminal:

```powershell
cd D:\global_event_intelligencerontend
npm install
npm run dev
```

The frontend will normally be available at:

```text
http://localhost:5173
```

---

# 15. Run the Complete Application

During development, use:

## Terminal 1 — Backend

```powershell
cd D:\global_event_intelligenceackend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

## Terminal 2 — Frontend

```powershell
cd D:\global_event_intelligencerontend
npm run dev
```

## Ollama

Make sure the model is available:

```powershell
ollama pull llama3.2:3b
```

Architecture while running:

```text
Browser
  |
  | http://localhost:5173
  v
React + 3D Earth
  |
  | REST API
  v
FastAPI
  |
  +---------> SQLite
  |
  +---------> Ollama
                  |
                  v
               Local LLM
```

---

# 16. Useful Development Checks

## Python

```powershell
python --version
```

## Python executable

```powershell
python -c "import sys; print(sys.executable)"
```

After activating `.venv`, it should point to:

```text
D:\global_event_intelligenceackend\.venv\Scripts\python.exe
```

## Uvicorn

```powershell
python -m uvicorn --version
```

## Node

```powershell
node --version
```

## npm

```powershell
npm --version
```

## Ollama

```powershell
ollama --version
```

---

# 17. Common Backend Problem

If you see:

```text
No module named uvicorn
```

the active Python environment does not have the backend dependencies installed.

Fix:

```powershell
cd D:\global_event_intelligenceackend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Also make sure the command is executed from:

```text
D:\global_event_intelligenceackend
```

because the FastAPI application is:

```text
backend/app/main.py
```

---

# 18. AI Development Roadmap

## Phase 1 — Current MVP

```text
News collection
      |
      v
Basic processing
      |
      v
SQLite
      |
      v
FastAPI
      |
      v
3D Earth
```

## Phase 2 — AI Analysis

Add:

```text
Article
   |
   v
Ollama
   |
   v
Structured JSON
   |
   v
Event
```

AI responsibilities:

- Important event detection
- Classification
- Country detection
- Geographic extraction
- Summary generation
- Importance scoring
- Confidence scoring

## Phase 3 — Event Intelligence

Add:

```text
Duplicate detection
        |
        v
Article similarity
        |
        v
Event clustering
        |
        v
One event from many articles
```

Example:

```text
Article 1 ─┐
Article 2 ─┤
Article 3 ─┼──> ONE EARTHQUAKE EVENT
Article 4 ─┘
```

## Phase 4 — Country Intelligence

Add:

- Country activity score
- Event timeline
- Category statistics
- AI country summary
- Related countries
- Cross-border events

## Phase 5 — Advanced Intelligence

Potential future features:

- Event evolution over time
- Breaking-event detection
- Source reliability
- Multi-source verification
- Semantic search
- Embeddings/vector database
- Historical event comparison
- Trend detection
- Regional risk analysis
- AI-generated global situation reports
- Alerts for high-impact events

---

# 19. Important Architectural Principle

Do not put the AI model directly in the React application.

Use:

```text
React
  |
  v
FastAPI
  |
  +----> AI / Ollama
  |
  +----> Database
```

Not:

```text
React
  |
  v
Ollama
```

The backend should control:

- AI prompts
- Secrets and configuration
- Model configuration
- Validation
- Database writes
- Event processing
- News-source management

The frontend should primarily visualize processed data.

---

# 20. Recommended Final Architecture

```text
                         GLOBAL EVENT INTELLIGENCE
                                  |
             +--------------------+--------------------+
             |                    |                    |
             v                    v                    v
          GDELT                 RSS               Future APIs
             |                    |                    |
             +--------------------+--------------------+
                                  |
                                  v
                         +-----------------+
                         | News Ingestion  |
                         +--------+--------+
                                  |
                                  v
                         +-----------------+
                         | Deduplication   |
                         +--------+--------+
                                  |
                                  v
                         +-----------------+
                         |   AI Agent      |
                         |    Ollama       |
                         +--------+--------+
                                  |
              +-------------------+-------------------+
              |                   |                   |
              v                   v                   v
          Category            Geography          Importance
              |                   |                   |
              +-------------------+-------------------+
                                  |
                                  v
                         +-----------------+
                         | Event Database  |
                         |     SQLite      |
                         +--------+--------+
                                  |
                                  v
                         +-----------------+
                         |     FastAPI     |
                         |      REST       |
                         +--------+--------+
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
             +--------------+           +----------------+
             |  React Earth |           |    Country     |
             |              |           |   Dashboard    |
             | Global view  |           |                |
             | Event map    |           | Detailed view  |
             | Filters      |           | Timeline       |
             | Markers      |           | Analytics      |
             +--------------+           | AI summaries   |
                                        +----------------+
```

---

# 21. Development Order

Build the system incrementally:

```text
1. Reliable news ingestion
          |
2. Clean article storage
          |
3. AI event extraction
          |
4. Validate AI JSON
          |
5. Store structured events
          |
6. Display events on Earth
          |
7. Build country dashboard
          |
8. Add deduplication/clustering
          |
9. Add confidence/source verification
          |
10. Add advanced intelligence
```

The overall objective is to evolve the project from a simple news map into an **event intelligence platform**, where multiple news articles are analyzed and transformed into structured events that can be explored globally and by country.
