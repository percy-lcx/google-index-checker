# GSC Indexation Status Checker

A FastAPI + React application that checks URL indexation status via the Google Search Console URL Inspection API. Tracks deindexing patterns over time.

## Setup

### 1. Google Cloud Credentials

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the **Google Search Console API**
3. Create **OAuth 2.0 credentials** (Desktop app type)
4. Download `credentials.json` to the project root

### 2. Environment

```bash
cp .env.example .env
# Edit .env with your GSC property URL
```

### 3. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

On first run, a browser window opens for Google OAuth authorization. The token is saved to `token.json` for subsequent runs.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Features

- Bulk URL indexation checking via GSC API
- Deindex transition detection and counting
- Real-time progress via SSE
- Sortable/filterable results dashboard
- Per-URL history timeline
- CSV export
- Daily quota tracking
- Auto-purge of results older than 90 days
