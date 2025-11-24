from flask import Blueprint
from services.gold_service import fetch_golds

gold_bp = Blueprint("gold", __name__)

@gold_bp.route("/golds/update", methods=["GET"])
def update_golds():
    ok = fetch_golds()
    return {"success": ok}
