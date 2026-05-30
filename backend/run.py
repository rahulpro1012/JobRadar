"""
JobRadar — Main entry point.
Run with: python run.py
Or with gunicorn: gunicorn 'app:create_app()'
"""
from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.DEBUG)

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)