# Deploying JobRadar (free personal cloud)

Hosts **one instance for yourself**, completely free, no credit card:

- **Backend** → Render (free web service)
- **Frontend** → Vercel
- **Database** → Turso (hosted SQLite) — *required*, because Render's free disk is ephemeral (it wipes on every spin-down/redeploy, so the DB can't live there)

It's single-profile with a **shared-password gate** ([Security](#security)).

> Want multiple people to each have their own data? That's the Docker model — see the [README](./README.md). A single hosted instance shares one profile/DB.
>
> *(A `backend/fly.toml` also exists for Fly.io — better performance via a real volume — but Fly requires a credit card, so this guide uses Render + Turso.)*

---

## 0. Prerequisites
- A [Render](https://render.com) account (GitHub login; **no credit card** for free web services)
- A [Vercel](https://vercel.com) account
- A [Turso](https://turso.tech) account + the [Turso CLI](https://docs.turso.tech/cli/installation) (no credit card)
- Your API keys ready (at least `GROQ_API_KEY`)

---

## 1. Database → Turso

```bash
turso auth signup                       # opens browser; GitHub login
turso db create jobradar                # create the database
turso db show jobradar --url            # → copy as TURSO_DATABASE_URL  (libsql://...)
turso db tokens create jobradar         # → copy as TURSO_AUTH_TOKEN
```

The app creates its schema automatically on first start — no manual table setup. Setting `TURSO_DATABASE_URL` is what switches the backend from local SQLite to Turso.

---

## 2. Backend → Render

**Option A — Blueprint (uses the included `render.yaml`):**
1. Render → **New → Blueprint** → connect `rahulpro1012/JobRadar`.
2. It detects `render.yaml` and creates the `jobradar-backend` Docker service.
3. Fill in the env vars it prompts for (the `sync:false` ones) — see the list below.

**Option B — manual:**
1. Render → **New → Web Service** → connect the repo.
2. **Runtime:** Docker · **Dockerfile path:** `backend/Dockerfile` · **Docker context:** `backend` · **Plan:** Free.
3. **Health check path:** `/api/health`.
4. Add environment variables (below).

**Environment variables to set (in the Render dashboard):**
| Key | Value |
|---|---|
| `FLASK_ENV` | `production` |
| `GROQ_API_KEY` | your Groq key |
| `TURSO_DATABASE_URL` | from step 1 (`libsql://...`) |
| `TURSO_AUTH_TOKEN` | from step 1 |
| `APP_ACCESS_TOKEN` | a password you choose (see [Security](#security)) |
| `JOOBLE_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `SERPAPI_API_KEY` | optional keys you have |
| `FRONTEND_URL` | set in step 4 (your Vercel URL) |
| *(optional)* `SEARXNG_URL`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `GMAIL_LABEL` | as needed |

Deploy, then verify:
```bash
curl https://<your-service>.onrender.com/api/health
```
Note the backend URL: `https://<your-service>.onrender.com`. (First hit after idle is slow — see notes.)

---

## 3. Frontend → Vercel
1. vercel.com → **Add New → Project** → import `rahulpro1012/JobRadar`.
2. **Root Directory:** `frontend` (important).
3. Framework auto-detects **Vite** (pinned by `frontend/vercel.json`).
4. **Environment Variables** → `VITE_API_URL` = `https://<your-service>.onrender.com` (no trailing slash; build-time, so redeploy if you change it).
5. Deploy → note the URL, e.g. `https://jobradar-xxx.vercel.app`.

---

## 4. Wire CORS
On Render, set `FRONTEND_URL=https://jobradar-xxx.vercel.app` and let it redeploy. The backend only sends CORS headers to origins it knows.

---

## 5. First use
Open the Vercel URL → enter your access password when prompted → **Upload Resume** → **Refresh**. The first backend call may take ~50s if Render had spun the service down (cold start). Jobs/profile now persist in Turso across restarts.

---

## Security

This instance is public. Set **`APP_ACCESS_TOKEN`** (any password) on Render to gate it:

```bash
# generate a strong one, or just pick a password
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

When set, every API call must carry it; the frontend prompts once and remembers it (`localStorage`, sent as `X-App-Token`). `/api/health` stays open for Render's checker. Without it, anyone with the URL can burn your Groq/Adzuna/SerpApi quotas and run email scans. (Leaving it unset disables the gate — which is what you want for local Docker.)

---

## Notes & limitations

- **Cold starts:** Render free spins the service down after ~15 min idle; the next request takes ~50s to wake. The frontend's 120s timeout already accounts for this. Optional: a free [cron-job.org](https://cron-job.org) ping to `/api/health` every ~14 min during the day keeps it warm.
- **In-flight refreshes:** if the service is recycled mid-refresh, that refresh is lost — just run it again. Data already written to Turso is safe.
- **Performance:** with Turso remote, each query is a network round-trip, so a refresh is somewhat slower than local SQLite. Fine for a personal tool at 1–3 refreshes/day. If it's ever too slow, ping me — embedded-replica mode is the upgrade path.
- **Single instance only:** don't scale the backend past 1 instance (the app is single-user; concurrent writers aren't the design).

## Updating
Push to `main` → Vercel auto-redeploys; Render auto-redeploys (if auto-deploy is on, else click Deploy). Turso data is untouched by redeploys.

## Backups
```bash
turso db shell jobradar ".dump" > jobradar-backup.sql
```
