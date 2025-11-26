from flask import Flask, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from datetime import datetime
import os
import atexit
import random
import time

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

from services.currency_service import fetch_currencies
from services.gold_service import fetch_golds
from services.silver_service import fetch_silvers

from routes.general_routes import api_bp

from models.db import get_db, put_db
from models.currency_models import init_db

# ==========================================
# FLASK APP
# ==========================================
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.register_blueprint(api_bp)

# ==========================================
# RANDOM JITTER FONKSİYONU
# ==========================================
def run_with_jitter(func):
    """
    Scraper çalışmadan önce 0-25 saniye arasında bekletir.
    Böylece Bigpara bizi bot sanmaz.
    """
    delay = random.randint(0, 25)
    logger.info(f"⏳ Jitter aktif → {delay} saniye gecikme")
    time.sleep(delay)
    return func()

# ==========================================
# SCHEDULER
# ==========================================
def init_scheduler():
    try:
        scheduler = BackgroundScheduler()

        # 🔥 10 Dakikada bir – Jitter ile birlikte
        scheduler.add_job(lambda: run_with_jitter(fetch_currencies),
                          "interval", minutes=10, id="currency_job")

        scheduler.add_job(lambda: run_with_jitter(fetch_golds),
                          "interval", minutes=10, id="gold_job")

        scheduler.add_job(lambda: run_with_jitter(fetch_silvers),
                          "interval", minutes=10, id="silver_job")

        scheduler.start()

        atexit.register(lambda: scheduler.shutdown())
        
        logger.info("🚀 Scheduler başlatıldı (Her 10 dakikada bir + jitter).")

    except Exception as e:
        logger.error(f"Scheduler hata: {e}")

# ==========================================
# STARTUP
# ==========================================
logger.info("🔧 KuraBak Backend başlıyor...")

init_db()

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
        "version": "2.1 (Scraping Edition + Jitter)",
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

@app.route("/api/update", methods=["POST", "GET"])
def manual_update():
    try:
        logger.info("⚡ Manuel güncelleme tetiklendi...")
        g = run_with_jitter(fetch_golds)
        c = run_with_jitter(fetch_currencies)
        s = run_with_jitter(fetch_silvers)

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
    app.run(host="0.0.0.0", port=port, debug=True)
