# JobRadar — Personal Job Alert Dashboard

A full-stack job discovery dashboard that aggregates listings from Naukri, LinkedIn, Indeed, and company career pages. It parses your resume, scores jobs by relevance, and presents them in a clean UI with one-click apply links.

## Features

- **Smart Resume Parsing** — Extracts structured skill profiles from PDF/DOCX resumes
- **Multi-Source Aggregation** — Searches Naukri, LinkedIn, Indeed, RSS feeds, and company career pages
- **Relevance Scoring** — Every job gets a 0–100 match score (skills 40% + role 25% + experience 20% + recency 15%)
- **Multi-Level Blacklist** — Block domains, companies, or keywords you don't trust
- **Preference Learning** — Improves recommendations based on your Apply/Save/Skip actions
- **Deduplication** — Same job on 4 portals shows up once
- **Zero Cost** — Runs on 100% free-tier services

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + Tailwind CSS |
| Backend | Python Flask |
| Database | SQLite (dev) / Turso (prod) |
| Hosting | Vercel (frontend) + Render (backend) |

## Quick Start (Local Development)

### Prerequisites
- Python 3.10+
- Node.js 18+
- npm or yarn

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # Edit with your API keys
python run.py              # Starts on http://localhost:5000
```

### Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev                # Starts on http://localhost:5173
```

Open http://localhost:5173 — the Vite dev server proxies API calls to the Flask backend.

## Deployment (Free — $0/month)

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/jobradar.git
git push -u origin main
```

### 2. Deploy Frontend to Vercel
1. Go to [vercel.com](https://vercel.com) → Import Git Repository
2. Select your repo → Set **Root Directory** to `frontend`
3. Add environment variable: `VITE_API_URL` = `https://YOUR-APP.onrender.com`
4. Click Deploy

### 3. Deploy Backend to Render
1. Go to [render.com](https://render.com) → New Web Service
2. Connect your GitHub repo → Set **Root Directory** to `backend`
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `gunicorn 'app:create_app()'`
5. Add environment variables:
   - `TURSO_DATABASE_URL` — from Turso dashboard
   - `TURSO_AUTH_TOKEN` — from Turso dashboard
   - `GOOGLE_CSE_API_KEY` — from Google Cloud Console
   - `GOOGLE_CSE_CX` — from Programmable Search Engine
   - `BING_API_KEY` — from Azure Portal
   - `FRONTEND_URL` — your Vercel URL (for CORS)
6. Choose **Free** instance → Deploy

### 4. Create Turso Database
```bash
# Install Turso CLI
curl -sSfL https://get.tur.so/install.sh | bash

# Create database
turso db create jobradar
turso db show jobradar --url     # Copy the URL
turso db tokens create jobradar  # Copy the token
```

### 5. Keep-Alive Pings
1. Go to [cron-job.org](https://cron-job.org)
2. Create a cron job → URL: `https://YOUR-APP.onrender.com/api/health`
3. Schedule: every 14 minutes, active 8 AM – 10 PM IST

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/health | Health check (used by keep-alive) |
| POST | /api/profile/upload | Upload resume (PDF/DOCX) |
| GET | /api/profile | Get parsed profile |
| PUT | /api/profile | Update profile fields |
| GET | /api/jobs | List jobs (supports filters) |
| GET | /api/jobs/:id | Get single job |
| PATCH | /api/jobs/:id/status | Update status (save/apply/skip) |
| POST | /api/jobs/refresh | Trigger new job search |
| GET | /api/jobs/stats | Get summary statistics |
| GET | /api/blacklist | List all blacklist entries |
| POST | /api/blacklist | Add blacklist entry |
| DELETE | /api/blacklist/:id | Remove blacklist entry |
| GET | /api/settings/quota | API quota usage |
| GET | /api/settings/companies | Company registry |
| POST | /api/settings/companies | Add company |
| DELETE | /api/settings/companies/:id | Remove company |
| PATCH | /api/settings/companies/:id/toggle | Toggle company |
| GET | /api/preferences | View preference weights |
| POST | /api/preferences/reset | Reset preferences |

## Project Structure

```
jobradar/
├── frontend/                  # React + Vite + Tailwind
│   ├── src/
│   │   ├── components/        # Navbar, Sidebar, JobCard, etc.
│   │   ├── services/          # API client (axios)
│   │   ├── utils/             # Helpers (scoring, formatting)
│   │   ├── App.jsx            # Main dashboard
│   │   └── main.jsx           # Entry point
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
├── backend/                   # Python Flask API
│   ├── app/
│   │   ├── __init__.py        # App factory
│   │   ├── database.py        # DB layer (7 tables)
│   │   ├── routes/            # API endpoints
│   │   ├── services/          # Parser, fetcher, scorer (Phase 2-4)
│   │   ├── models/
│   │   └── utils/
│   ├── config.py
│   ├── run.py
│   ├── requirements.txt
│   └── gunicorn.conf.py
├── .gitignore
└── README.md
```

## Build Phases

- [x] **Phase 1** — Project scaffolding, database, API skeleton, React shell
- [ ] **Phase 2** — Resume parser + profile extraction
- [ ] **Phase 3** — Job fetcher (6 source layers + source router)
- [ ] **Phase 4** — Relevance scorer + deduplicator + blacklist engine
- [ ] **Phase 5** — Complete REST API integration
- [ ] **Phase 6** — React dashboard (polished UI)
- [ ] **Phase 7** — Preference learning, auto-refresh, deployment

## License

MIT
