from flask import Flask, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from datetime import datetime
import os
import atexit

# ==========================================
# LOGGING
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==========================================
# IMPORTS
# ==========================================
from config import Config

# Servisler (Veri çekmek için gerekli)
from services.currency_service import fetch_currencies
from services.gold_service import fetch_golds
from services.silver_service import fetch_silvers

# 🔥 YENİ: Tekli Route Dosyası
from routes.general_routes import api_bp

from models.db import get_db, put_db
from models.currency_models import init_db

# ==========================================
# FLASK APP
# ==========================================
app = Flask(__name__)
# CORS: Tüm domainlere izin ver (Mobil uygulama rahat erişsin)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# 🔥 Blueprint register (Sadece api_bp yeterli)
app.register_blueprint(api_bp)

# ==========================================
# SCHEDULER (Zamanlayıcı)
# ==========================================
def init_scheduler():
    try:
        scheduler = BackgroundScheduler()

        # 🔥 GÜNCELLEME SIKLIĞI: 1 Saat çok uzun. 5 Dakikada (300 sn) bir güncelliyoruz.
        # Böylece site bizi banlamaz ama veriler taze kalır.
        scheduler.add_job(fetch_currencies, "interval", minutes=5, id="currency_job")
        scheduler.add_job(fetch_golds, "interval", minutes=5, id="gold_job")
        scheduler.add_job(fetch_silvers, "interval", minutes=5, id="silver_job")

        scheduler.start()
        
        # Uygulama kapanırken scheduler'ı kapat
        atexit.register(lambda: scheduler.shutdown())
        
        logger.info("🚀 Scheduler başlatıldı (Her 5 dakikada bir güncelleyecek).")

    except Exception as e:
        logger.error(f"Scheduler hata: {e}")

# ==========================================
# STARTUP
# ==========================================
logger.info("🔧 KuraBak Backend başlıyor...")

# Veritabanı tablolarını başlat
init_db()

# Scheduler'ı başlat
# (Debug modunda çift çalışmaması için basit bir kontrol)
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    init_scheduler()

# ==========================================
# ENDPOINTS
# ==========================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "app": "KuraBak Backend",
        "status": "running",
        "version": "2.0 (Scraping Edition)",
        "endpoints": [
            "/api/gold/all", 
            "/api/currency/all", 
            "/api/silver/all"
        ],
        "timestamp": datetime.now().isoformat()
    })

@app.route("/health", methods=["GET"])
def health():
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM currencies")
        doviz = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM golds")
        altin = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM silvers")
        gumus = cur.fetchone()[0]

        cur.close()
        put_db(conn)

        return jsonify({
            "status": "healthy",
            "counts": {
                "doviz": doviz,
                "altin": altin,
                "gumus": gumus
            }
        }), 200

    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

# Manuel Tetikleme (Admin için)
@app.route("/api/update", methods=["POST", "GET"])
def manual_update():
    try:
        logger.info("Manuel güncelleme tetiklendi...")
        g = fetch_golds()
        c = fetch_currencies()
        s = fetch_silvers()
        return {
            "success": True, 
            "results": {"gold": g, "currency": c, "silver": s}
        }, 200
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

# ==========================================
# RUN SERVER
# ==========================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"🌍 Server aktif → Port: {port}")
    # Render'da debug=False olmalı, localde True olabilir
    app.run(host="0.0.0.0", port=port, debug=True)
