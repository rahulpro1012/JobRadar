"""
JobRadar — WSGI entry point for gunicorn (production / Docker).

Run with: gunicorn -w 1 --threads 4 -b 0.0.0.0:5000 wsgi:app

Mirrors the setup in run.py (dotenv, logging, urllib3 warning suppression)
since gunicorn imports this module directly instead of executing run.py.
"""
from dotenv import load_dotenv
load_dotenv()  # no-op in Docker (env comes from compose); used for bare-metal runs

import logging
logging.basicConfig(level=logging.INFO)

import urllib3
# Outbound fetchers use verify=False (network workaround); silence the warning spam.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app import create_app

app = create_app()
