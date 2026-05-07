"""Profile API routes — resume upload with AI parsing + regex fallback."""
import json
import logging
from flask import Blueprint, request, jsonify, current_app
from app.database import execute_query, get_connection

profile_bp = Blueprint("profile", __name__)
logger = logging.getLogger(__name__)


@profile_bp.route("/profile", methods=["GET"])
def get_profile():
    """Get the current parsed profile."""
    profile = execute_query(
        "SELECT * FROM profiles ORDER BY id DESC LIMIT 1",
        fetch_one=True
    )
    if not profile:
        return jsonify({"error": "No profile found. Please upload a resume."}), 404
    return jsonify(profile)


@profile_bp.route("/profile/upload", methods=["POST"])
def upload_resume():
    """Upload a resume file (PDF/DOCX) and parse it into a structured profile."""
    if "resume" not in request.files:
        return jsonify({"error": "No resume file provided"}), 400

    file = request.files["resume"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    allowed = current_app.config["ALLOWED_EXTENSIONS"]
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        return jsonify({"error": f"File type .{ext} not allowed. Use PDF or DOCX."}), 400

    import os
    upload_path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"resume.{ext}")
    file.save(upload_path)

    # ── Strategy: AI parse first, regex fallback ──
    from app.services.resume_parser import parse_resume, extract_text
    parse_method = "regex"

    # Try AI parsing (smarter, understands context, ranks skills)
    try:
        from app.services.ai_agent import ai_parse_resume, is_ai_enabled
        if is_ai_enabled():
            raw_text = extract_text(upload_path)
            ai_result = ai_parse_resume(raw_text)
            if ai_result:
                profile_data = ai_result
                # AI doesn't return resume_text, add it
                profile_data["resume_text"] = raw_text[:5000]
                parse_method = "ai"
    except Exception as e:
        logger.info(f"AI parse unavailable: {e}")

    # Fallback to regex parser
    if parse_method == "regex":
        try:
            profile_data = parse_resume(upload_path)
        except ValueError as e:
            return jsonify({"error": str(e)}), 422
        except Exception as e:
            return jsonify({"error": f"Failed to parse resume: {str(e)}"}), 500

    # Convert lists to JSON strings for storage
    for field in ["role_variants", "core_skills", "secondary_skills", "tools", "domain_keywords"]:
        if isinstance(profile_data.get(field), list):
            profile_data[field] = json.dumps(profile_data[field])

    # Upsert profile
    with get_connection() as conn:
        conn.execute("DELETE FROM profiles")
        conn.execute("""
            INSERT INTO profiles (
                name, primary_role, role_variants, experience_years,
                experience_level, core_skills, secondary_skills, tools,
                domain_keywords, education, location, resume_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile_data.get("name", ""),
            profile_data.get("primary_role", ""),
            profile_data.get("role_variants", "[]"),
            profile_data.get("experience_years", 0),
            profile_data.get("experience_level", ""),
            profile_data.get("core_skills", "[]"),
            profile_data.get("secondary_skills", "[]"),
            profile_data.get("tools", "[]"),
            profile_data.get("domain_keywords", "[]"),
            profile_data.get("education", ""),
            profile_data.get("location", ""),
            profile_data.get("resume_text", ""),
        ))
        conn.commit()

    profile = execute_query(
        "SELECT * FROM profiles ORDER BY id DESC LIMIT 1",
        fetch_one=True
    )
    return jsonify({
        "message": f"Resume parsed successfully ({parse_method})",
        "profile": profile,
        "parse_method": parse_method,
    }), 201


@profile_bp.route("/profile", methods=["PUT"])
def update_profile():
    """Manually update profile fields."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    allowed_fields = {
        "name", "primary_role", "role_variants", "experience_years",
        "experience_level", "core_skills", "secondary_skills", "tools",
        "domain_keywords", "education", "location"
    }

    updates = []
    values = []
    for field, value in data.items():
        if field in allowed_fields:
            if isinstance(value, (list, dict)):
                value = json.dumps(value)
            updates.append(f"{field} = ?")
            values.append(value)

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    updates.append("updated_at = CURRENT_TIMESTAMP")

    with get_connection() as conn:
        conn.execute(
            f"UPDATE profiles SET {', '.join(updates)} WHERE id = (SELECT MAX(id) FROM profiles)",
            values
        )
        conn.commit()

    profile = execute_query(
        "SELECT * FROM profiles ORDER BY id DESC LIMIT 1",
        fetch_one=True
    )
    return jsonify({"message": "Profile updated", "profile": profile})
