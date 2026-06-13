# Deploying JobRadar (personal hosted instance)

This hosts **one** instance for **yourself**: backend on **Fly.io** (free persistent SQLite volume), frontend on **Vercel**. It is single-profile and has **no login** — see [Security](#security) before sharing the URL.

> Just want to run it locally / share with friends so each has their own data?
> Use Docker instead — see the [README](./README.md). That's the right model for multiple people.

---

## 0. Prerequisites
- [flyctl](https://fly.io/docs/flyctl/install/) installed + a Fly.io account (`fly auth login`)
- A [Vercel](https://vercel.com) account (GitHub login is easiest)
- Your API keys ready (at minimum `GROQ_API_KEY` — see README for the rest)

---

## 1. Backend → Fly.io

```bash
cd backend

# Pick a unique app name first: edit `app = "..."` in fly.toml
# (Fly app names are global, so jobradar-backend is likely taken.)

# Register the app on Fly without deploying yet (uses the existing fly.toml)
fly launch --no-deploy --copy-config --name <your-app-name> --region sin

# Create the persistent volume the DB + resume live on (same region as the app)
fly volumes create jobradar_data --size 1 --region sin

# Set your secrets (API keys never go in fly.toml). Only include the ones you use:
fly secrets set \
  GROQ_API_KEY=gsk_xxx \
  JOOBLE_API_KEY=xxx \
  ADZUNA_APP_ID=xxx ADZUNA_APP_KEY=xxx \
  SERPAPI_API_KEY=xxx
  # optional: SEARXNG_URL=...  GMAIL_ADDRESS=...  GMAIL_APP_PASSWORD=...  GMAIL_LABEL=...

# Deploy
fly deploy

# Verify
curl https://<your-app-name>.fly.dev/api/health      # → {"status":"ok"} ish
```

Note your backend URL: `https://<your-app-name>.fly.dev`.

**`SQLITE_DB_PATH` and `UPLOAD_FOLDER` are already set to `/data/...` in `fly.toml`**, so the DB and uploaded resume persist on the volume across deploys.

---

## 2. Frontend → Vercel

1. **vercel.com → Add New → Project →** import `rahulpro1012/JobRadar`.
2. **Root Directory:** set to **`frontend`** (important — the repo root isn't the app).
3. Framework preset auto-detects **Vite** (the included `frontend/vercel.json` also pins it + adds SPA rewrites).
4. **Environment Variables** → add (Production):
   - `VITE_API_URL` = `https://<your-app-name>.fly.dev`  ← your Fly backend, **no trailing slash**
   - *(This is a build-time var — if you change it later, redeploy.)*
5. **Deploy.** Note the URL, e.g. `https://jobradar-xxx.vercel.app`.

---

## 3. Wire CORS (backend must allow the Vercel origin)

```bash
cd backend
fly secrets set FRONTEND_URL=https://jobradar-xxx.vercel.app    # triggers a redeploy
```

The backend only sends CORS headers to origins it knows; this tells it about your Vercel URL.

---

## 4. First use
Open the Vercel URL → **Upload Resume** → **Refresh**. First backend request may take a few seconds if the machine auto-stopped (cold start). Jobs/profile persist on the Fly volume.

---

## Security — turn on the access gate

This deployment is public. Without protection, anyone who finds the Vercel URL can trigger refreshes (burning *your* Groq/Adzuna/SerpApi quotas), upload a resume, and run email scans.

A built-in **shared-password gate** handles this. To enable it, set a secret on the backend:

```bash
cd backend
fly secrets set APP_ACCESS_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
# (or just pick your own password string)
```

Once set, every API call must carry that password. The frontend prompts for it once on first load (`window.prompt`), stores it in `localStorage`, and sends it as an `X-App-Token` header thereafter. `/api/health` stays open so Fly's health check keeps working.

Leaving `APP_ACCESS_TOKEN` **unset disables the gate** — which is what you want for local Docker use, so no password is needed there.

> This is a single shared password, not per-user accounts — right for a personal instance. For multi-user, friends should each run their own via Docker (see README).

---

## Updating

- **Frontend:** push to `main` → Vercel auto-redeploys.
- **Backend:** `cd backend && fly deploy` (or add a GitHub Action). The volume (DB + resume) is untouched by deploys.

## Cost & reliability notes

- `auto_stop_machines` keeps the backend near-zero cost by stopping it when idle. Trade-off: a long **background refresh can be cut short** if the machine stops mid-run. If that bites, set `min_machines_running = 1` in `fly.toml` (a single small always-on machine — usually a few $/mo or within Fly's allowance).
- SQLite on one volume + one machine is correct for single-user. Don't scale the backend to >1 machine — they'd each have a separate volume and diverge.

## Backups

```bash
# Pull the live SQLite DB off the Fly volume
fly ssh console -C "cat /data/jobradar.db" > jobradar-backup.db   # (or use `fly sftp get`)
```
