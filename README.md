# JobRadar

**AI-powered, self-hosted job-discovery dashboard.** It aggregates postings from 10+ sources, parses your resume to learn your profile, scores every job against it, and surfaces the top matches with per-job *“why apply / why skip”* reasoning. It can also scan your Gmail job-alert emails and fold those into the same pipeline.

Runs entirely on your machine — your resume, your API keys, your data. No accounts, no telemetry, no shared database.

```
┌──────────── your machine (docker compose) ────────────┐
│   frontend (React + nginx) :5173                       │
│        │  /api/* proxied                               │
│        ▼                                               │
│   backend (Flask + gunicorn) :5000 ──► SQLite (./data) │
│        │                                               │
│        └──► uploaded resume (./uploads)                │
└────────────────────────┬───────────────────────────────┘
                         ▼
   Groq · Jooble · Adzuna · SerpApi · SearxNG · Gmail (your keys)
   + keyless sources: Greenhouse, Lever, Ashby, Workable,
     SmartRecruiters, RemoteOK, Arbeitnow, HN “Who is hiring”
```

---

## Quick start (Docker)

**Prerequisites:** [Docker + Docker Compose](https://docs.docker.com/get-docker/), and a free [Groq API key](https://console.groq.com/keys) (the only hard requirement — everything else is optional and the app skips any source whose key is missing).

```bash
# 1. Clone
git clone https://github.com/rahulpro1012/JobRadar.git
cd JobRadar

# 2. Configure — copy the template and add your keys
cp .env.example .env
#   then edit .env  (at minimum, set GROQ_API_KEY)

# 3. Launch
docker compose up --build

# 4. Open the dashboard
#    http://localhost:5173
```

First build takes ~2–3 minutes (pulling base images + `npm ci`). After that, `docker compose up` starts in seconds.

**Then, in the browser:**
1. Click **Upload Resume** (top right) and pick your PDF/DOCX — the app parses it with AI into a profile.
2. Click **Refresh** — it fetches ~1,000 jobs across all sources, scores them against your profile, and runs AI reasoning on the top matches. Takes ~40–90s; progress shows live.
3. (Optional) Click **Scan Email** to import jobs from your Gmail job alerts (requires the Gmail setup below).

Your database lives in `./data/` and your uploaded resume in `./uploads/` on the host, so both survive restarts and `git pull`s.

---

## Getting the API keys

All free tier. You can start with **just Groq** and add the rest whenever — missing keys simply disable that one source (the backend logs which integrations are on at startup).

| Key | Required? | What it powers | Get it | Free tier |
|---|---|---|---|---|
| `GROQ_API_KEY` | **Yes** | Resume parsing, scoring, per-job reasoning | [console.groq.com/keys](https://console.groq.com/keys) | 14,400 req/day, 6k tokens/min |
| `JOOBLE_API_KEY` | Recommended | Naukri/Indeed/etc. aggregation | [jooble.org/api/about](https://jooble.org/api/about) | emailed within ~a day |
| `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | Recommended | Indian boards w/ salary data | [developer.adzuna.com/signup](https://developer.adzuna.com/signup) | ~250/day |
| `SERPAPI_API_KEY` | Recommended | Google Jobs | [serpapi.com/users/sign_up](https://serpapi.com/users/sign_up) | 100 searches/month |
| `SEARXNG_URL` | Optional | Naukri + LinkedIn web search | self-host [SearxNG](https://github.com/searxng/searxng) on Render | — |
| `GMAIL_*` | Optional | “Scan Email” feature | see below | — |

Keyless sources (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, RemoteOK, Arbeitnow, HN *Who is hiring*) always run — so even with only a Groq key you'll get hundreds of scored jobs per refresh.

### Optional: Gmail job-alert scanner

The **Scan Email** button imports postings from your job-alert emails and runs them through the same scoring + AI reasoning. It needs a Gmail **App Password** (not your normal password), stored only in `.env` — never in the database or sent to the browser.

1. Enable [2-Step Verification](https://myaccount.google.com/security).
2. Create an [App Password](https://myaccount.google.com/apppasswords) → App = *Mail*, Device = *Other* (“JobRadar”).
3. Put the 16-char password (spaces removed) in `.env`:
   ```
   GMAIL_ADDRESS=you@gmail.com
   GMAIL_APP_PASSWORD=abcd efgh ijkl mnop   →  abcdefghijklmnop
   ```
4. Restart, then in **Settings → Email** add the sender addresses/domains you want scanned (e.g. `linkedin.com`, `naukri.com`, a company's `*.jobs2web.com` alert address). **Only senders on that allowlist are ever read** — nothing else in your inbox is touched.

---

## Using the app

- **Upload / Update Resume** — re-upload anytime to re-parse your profile.
- **Refresh** — full fetch → score → AI-reason pipeline (async; jobs stay visible while it runs).
- **Scan Email** — on-demand Gmail import (background; jobs stay visible).
- **Filters** (left sidebar) — min match score, posted-within, source, and “from email alerts only”.
- **Dismiss** — hide jobs you're not interested in (with undo); toggle “Show dismissed” to review.
- **Settings**
  - **API Quota** — daily/monthly usage per source.
  - **Sources / Blacklist** — mute companies or sources.
  - **Email** — connection test + sender allowlist + scan window.
  - **Manage Jobs** — retention window (auto-deletes jobs older than N days, default 15) + manual purge controls.

---

## Configuration reference

Everything is set in `.env` (see [`.env.example`](./.env.example) for the annotated list). Notes:

- `SQLITE_DB_PATH` and `FRONTEND_URL` are set automatically by `docker-compose.yml` — no need to touch them.
- Leave `TURSO_*` empty unless you specifically want a hosted libSQL database instead of local SQLite.
- The frontend is built with `VITE_API_URL` empty on purpose: it calls relative `/api`, which nginx proxies to the backend. This keeps the browser on one origin (`:5173`) and avoids CORS entirely.

---

## Hosting it (personal cloud)

Want it running 24/7 instead of locally? See **[DEPLOY.md](./DEPLOY.md)** — backend on Fly.io (free persistent SQLite volume) + frontend on Vercel. That's a single-user, public instance; the Docker setup above remains the right choice for letting multiple people each run their own.

## Running without Docker (local dev)

```bash
# Backend
cd backend
python -m venv .venv && . .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
#   put your keys in backend/.env  (see backend/.env.example)
python run.py                                       # http://localhost:5000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                                         # http://localhost:5173, proxies /api → :5000
```

---

## Managing the deployment

```bash
# Update to latest
git pull && docker compose up --build

# Stop (data persists)
docker compose down

# Back up your data + keys
tar -czf jobradar-backup-$(date +%Y%m%d).tar.gz data/ uploads/ .env

# Full reset (wipe DB + resume, start clean)
docker compose down
rm -rf data/ uploads/
docker compose up --build
```

---

## Troubleshooting

**Backend won't start / `ModuleNotFoundError`** — rebuild without cache: `docker compose build --no-cache backend`.

**Refresh fails or AI fields are empty** — your `GROQ_API_KEY` is missing/invalid. Check the backend log on startup; it prints `Integrations enabled: …` and warns if Groq is unset. Logs: `docker compose logs -f backend`.

**Backend shows `unhealthy`** — `docker compose logs backend`. Usually a bad key or a port already in use (`:5000`).

**A source returns 0 jobs** — likely that key isn't set, or you've hit its free-tier quota (see **Settings → API Quota**). Other sources still work; one quiet source isn't a failure.

**SearxNG times out** — if you point `SEARXNG_URL` at a Render free instance, it sleeps after ~15 min idle; the first request warms it up. It's one source out of many — the rest are unaffected.

**`database is locked`** — only one backend process should run. The container uses gunicorn with a single worker for exactly this reason; don't run a second backend against the same `data/`.

---

## Architecture

- **Backend:** Flask (app-factory + blueprints) on gunicorn (1 worker + threads), SQLite (WAL), Groq `llama-3.1-8b-instant` for AI. Parallel fetching via `ThreadPoolExecutor`; async refresh runs in a background thread with DB-backed progress that the frontend polls.
- **Frontend:** React + Vite + Tailwind, served as a static bundle by nginx, which also proxies `/api` to the backend.
- **Storage:** SQLite at `./data/jobradar.db`, uploaded resume at `./uploads/` — both host-mounted volumes.
- **Schema:** auto-created and migrated on startup (`CREATE TABLE IF NOT EXISTS` + additive column checks) — no migration step to run.

### Selected API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | health check |
| `GET` | `/api/profile` | current parsed profile |
| `POST` | `/api/profile/upload` | upload & parse resume |
| `GET` | `/api/jobs?page=1&per_page=20&status=new` | list jobs (filters: `status`, `via_email`, `include_dismissed`, …) |
| `GET` | `/api/jobs/stats` | counts by status / source |
| `POST` | `/api/jobs/refresh-async` | start a refresh → `{job_id}` |
| `GET` | `/api/jobs/refresh-async/<id>` | poll refresh progress |
| `POST` | `/api/email/scan-async` | start a Gmail scan |
| `GET` | `/api/email/status` | email feature status (no secrets) |

---

## Limitations & notes

- **Single-user, no auth.** Each person runs their own instance. Don't expose it to the public internet as-is.
- **Outbound TLS verification is disabled** in the fetchers (a network workaround). Fine for local self-hosting; be aware if you harden this for a server.
- **Free-tier quotas** apply (Adzuna ~250/day, SerpApi 100/month, Groq 14,400/day). One or two refreshes a day stays well within them.
- **AI scoring is a signal, not a verdict** — it reflects how well a posting matches your parsed resume; always read the listing yourself before applying.

---

*Personal project, shared as-is. Built with Flask, React, and Groq. Licensed MIT.*
