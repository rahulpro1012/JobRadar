"""Profile API routes — resume upload and profile management."""
import json
from flask import Blueprint, request, jsonify, current_app
from app.database import execute_query, get_connection

profile_bp = Blueprint("profile", __name__)


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
    """
    Upload a resume file (PDF/DOCX) and parse it into a structured profile.
    The actual parsing logic will be implemented in Phase 2.
    """
    if "resume" not in request.files:
        return jsonify({"error": "No resume file provided"}), 400
    
    file = request.files["resume"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    
    # Check file extension
    allowed = current_app.config["ALLOWED_EXTENSIONS"]
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        return jsonify({"error": f"File type .{ext} not allowed. Use PDF or DOCX."}), 400
    
    # Save file
    import os
    upload_path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"resume.{ext}")
    file.save(upload_path)
    
    # Parse resume into structured profile
    from app.services.resume_parser import parse_resume
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
    
    # Upsert profile (replace existing or insert new)
    with get_connection() as conn:
        conn.execute("DELETE FROM profiles")  # Single-user app: one profile
        conn.execute("""
            INSERT INTO profiles (
                name, primary_role, role_variants, experience_years,
                experience_level, core_skills, secondary_skills, tools,
                domain_keywords, education, location, resume_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile_data["name"],
            profile_data["primary_role"],
            profile_data["role_variants"],
            profile_data["experience_years"],
            profile_data["experience_level"],
            profile_data["core_skills"],
            profile_data["secondary_skills"],
            profile_data["tools"],
            profile_data["domain_keywords"],
            profile_data["education"],
            profile_data["location"],
            profile_data["resume_text"],
        ))
        conn.commit()
    
    # Fetch and return the saved profile
    profile = execute_query(
        "SELECT * FROM profiles ORDER BY id DESC LIMIT 1",
        fetch_one=True
    )
    return jsonify({"message": "Resume uploaded and parsed successfully", "profile": profile}), 201


@profile_bp.route("/profile", methods=["PUT"])
def update_profile():
    """Manually update profile fields (e.g., change location, add skills)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Build dynamic UPDATE query from provided fields
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
