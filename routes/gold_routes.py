from flask import Blueprint, jsonify
from services.gold_service import fetch_golds
from models.db import get_db

gold_bp = Blueprint("gold", __name__)

# 1. Manuel Güncelleme Tetikleyicisi (Senin mevcut kodun)
# Tarayıcıdan girince: /golds/update -> Gider siteden yeni veri çeker
@gold_bp.route("/golds/update", methods=["GET"])
def update_golds():
    ok = fetch_golds()
    if ok:
        return {"success": True, "message": "Altın verileri güncellendi"}
    else:
        return {"success": False, "message": "Güncelleme başarısız"}, 500

# 2. Veri Okuma (Uygulamanın kullanacağı kısım)
# Uygulama isteği: /api/golds -> Veritabanındaki hazır veriyi verir
@gold_bp.route("/api/golds", methods=["GET"])
def get_gold_prices():
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT name, buying, selling, rate, change_percent, updated_at 
            FROM golds 
            ORDER BY name ASC
        """)
        rows = cur.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "name": row[0],
                "buying": row[1],
                "selling": row[2],
                "rate": row[3],
                "change_percent": row[4],
                "updated_at": str(row[5])
            })
            
        return jsonify({"success": True, "data": results}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cur.close()
