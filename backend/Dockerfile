# JobRadar backend — Flask API served by gunicorn
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Build deps for any packages without manylinux wheels (e.g. Levenshtein)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Runtime data dirs (mounted as volumes in docker-compose for persistence)
#   /app/data    -> SQLite DB (SQLITE_DB_PATH)
#   /app/uploads -> uploaded resume (UPLOAD_FOLDER, default BASE_DIR/uploads)
RUN mkdir -p /app/data /app/uploads

EXPOSE 5000

# Health: hit the existing /api/health endpoint with stdlib (no curl in slim)
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:5000/api/health', timeout=5).status==200 else 1)"

# 1 worker keeps SQLite + the background refresh/email-scan threads consistent;
# threads handle concurrent poll requests. Schema auto-inits on app import.
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:5000", "--timeout", "120", "wsgi:app"]
