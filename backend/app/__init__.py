"""
JobRadar Flask Application Factory
Creates and configures the Flask app with CORS, routes, and database.
"""
import os
from flask import Flask
from config import get_config, log_config_status


def _setup_cors(app):
    """Lightweight CORS support without flask-cors dependency."""
    frontend_url = app.config["FRONTEND_URL"]
    allowed_origins = [frontend_url, "http://localhost:5173", "http://localhost:3000"]

    @app.after_request
    def add_cors_headers(response):
        origin = response.headers.get("Access-Control-Allow-Origin")
        from flask import request as req
        req_origin = req.headers.get("Origin", "")
        if req_origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = req_origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    @app.before_request
    def handle_preflight():
        from flask import request as req
        if req.method == "OPTIONS":
            from flask import make_response
            resp = make_response()
            req_origin = req.headers.get("Origin", "")
            if req_origin in allowed_origins:
                resp.headers["Access-Control-Allow-Origin"] = req_origin
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return resp


def _setup_auth_gate(app):
    """Require a shared token on /api requests when APP_ACCESS_TOKEN is set.

    Disabled (no-op) when the env var is empty — so local/Docker use is
    frictionless. Health checks and CORS preflight are always allowed.
    """
    import hmac
    token = app.config.get("APP_ACCESS_TOKEN", "")
    if not token:
        return  # gate disabled

    open_paths = {"/api/health", "/api/health/"}

    @app.before_request
    def _require_token():
        from flask import request, jsonify
        if request.method == "OPTIONS":
            return None  # let CORS preflight through
        if request.path in open_paths:
            return None  # health probe is public (Fly checker)
        supplied = request.headers.get("X-App-Token", "")
        if not hmac.compare_digest(supplied, token):
            return jsonify({"error": "unauthorized"}), 401
        return None


def create_app(config_class=None):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Load configuration
    if config_class is None:
        config_class = get_config()
    app.config.from_object(config_class)

    # Heads-up log of which integrations are configured (non-fatal)
    log_config_status()
    
    # Ensure upload directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    
    # Configure CORS (uses flask-cors if available, otherwise built-in)
    try:
        from flask_cors import CORS
        frontend_url = app.config["FRONTEND_URL"]
        CORS(app, resources={
            r"/api/*": {
                "origins": [frontend_url, "http://localhost:5173", "http://localhost:3000"],
                "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization"],
            }
        })
    except ImportError:
        _setup_cors(app)

    # Optional shared-password gate (hosted/public deployments)
    _setup_auth_gate(app)

    # Initialize database
    from app.database import init_db
    init_db(app.config)
    
    # Register blueprints (API routes)
    from app.routes.health import health_bp
    from app.routes.profile import profile_bp
    from app.routes.jobs import jobs_bp
    from app.routes.blacklist import blacklist_bp
    from app.routes.settings import settings_bp
    from app.routes.admin import admin_bp
    from app.routes.email import email_bp

    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(profile_bp, url_prefix="/api")
    app.register_blueprint(jobs_bp, url_prefix="/api")
    app.register_blueprint(blacklist_bp, url_prefix="/api")
    app.register_blueprint(settings_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")
    app.register_blueprint(email_bp, url_prefix="/api")
    
    return app
