"""Gunicorn production configuration for Render deployment."""
import os

# Bind to the port Render provides, default 5000
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# Workers — Render free tier has limited CPU, keep it light
workers = 2
worker_class = "sync"
timeout = 120  # scraping can take a while

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Graceful restart
graceful_timeout = 30
