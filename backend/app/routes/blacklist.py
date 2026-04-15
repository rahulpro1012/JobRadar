"""Blacklist API routes — CRUD for domain, company, and keyword blocking."""
from flask import Blueprint, request, jsonify
from app.database import execute_query, get_connection

blacklist_bp = Blueprint("blacklist", __name__)


@blacklist_bp.route("/blacklist", methods=["GET"])
def get_blacklist():
    """Get all blacklist entries, optionally filtered by type."""
    bl_type = request.args.get("type")  # domain, company, or keyword
    
    if bl_type and bl_type in ("domain", "company", "keyword"):
        entries = execute_query(
            "SELECT * FROM blacklist WHERE type = ? ORDER BY added_date DESC",
            (bl_type,),
            fetch_all=True
        )
    else:
        entries = execute_query(
            "SELECT * FROM blacklist ORDER BY type, added_date DESC",
            fetch_all=True
        )
    
    # Group by type for convenience
    grouped = {"domain": [], "company": [], "keyword": []}
    for entry in entries:
        grouped[entry["type"]].append(entry)
    
    return jsonify({
        "entries": entries,
        "grouped": grouped,
        "total": len(entries)
    })


@blacklist_bp.route("/blacklist", methods=["POST"])
def add_blacklist_entry():
    """Add a new blacklist entry."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    bl_type = data.get("type")
    value = data.get("value", "").strip().lower()
    
    if bl_type not in ("domain", "company", "keyword"):
        return jsonify({"error": "Type must be 'domain', 'company', or 'keyword'"}), 400
    
    if not value:
        return jsonify({"error": "Value cannot be empty"}), 400
    
    try:
        entry_id = execute_query(
            "INSERT INTO blacklist (type, value) VALUES (?, ?)",
            (bl_type, value)
        )
        return jsonify({
            "message": f"Blocked {bl_type}: {value}",
            "id": entry_id
        }), 201
    except Exception:
        return jsonify({"error": f"'{value}' is already in the {bl_type} blacklist"}), 409


@blacklist_bp.route("/blacklist/<int:entry_id>", methods=["DELETE"])
def remove_blacklist_entry(entry_id):
    """Remove a blacklist entry by ID."""
    entry = execute_query(
        "SELECT * FROM blacklist WHERE id = ?",
        (entry_id,),
        fetch_one=True
    )
    if not entry:
        return jsonify({"error": "Blacklist entry not found"}), 404
    
    execute_query("DELETE FROM blacklist WHERE id = ?", (entry_id,))
    return jsonify({
        "message": f"Removed {entry['type']} block: {entry['value']}",
        "id": entry_id
    })
