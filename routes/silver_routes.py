from flask import Blueprint
from services.silver_service import fetch_silvers

silver_bp = Blueprint("silver", __name__)

@silver_bp.route("/silvers/update", methods=["GET"])
def update_silvers():
    ok = fetch_silvers()
    return {"success": ok}
