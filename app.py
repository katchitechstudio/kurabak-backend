from flask import Flask, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from datetime import datetime
import os
import atexit
import random
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from config import Config
from services.currency_service import fetch_currencies
from services.gold_service import fetch_golds
from services.silver_service import fetch_silvers
from services.maintenance_service import weekly_maintenance
from routes.general_routes import api_bp
from models.db import get_db_cursor, init_connection_pool, close_all_connections
from models.currency_models import init_db, verify_database_health

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.register_blueprint(api_bp)

def run_with_jitter(func):
    delay = random.randint(0, 25)
    logger.info(f"⏳ Jitter aktif → {delay} saniye gecikme")
    time.sleep(delay)
    return func()

def init_scheduler():
    try:
        scheduler = BackgroundScheduler()

        # Haftalık bakım - Her Pazar sabahı 04:00
        scheduler.add_job(
            weekly_maintenance,
            trigger=CronTrigger(
                day_of_week='sun',
                hour=4,
                minute=0,
                second=0
            ),
            id="weekly_maintenance",
            name="Haftalık Bakım (Temizlik + Optimizasyon)",
            replace_existing=True
        )
        logger.info("📅 Haftalık bakım job'u eklendi (Her Pazar 04:00)")

        # Döviz güncelleme - 10 dakikada bir
        scheduler.add_job(
            lambda: run_with_jitter(fetch_currencies),
            "interval",
            minutes=10,
            id="currency_job",
            name="Döviz güncelleme"
        )

        # Altın güncelleme - 10 dakikada bir
        scheduler.add_job(
            lambda: run_with_jitter(fetch_golds),
            "interval",
            minutes=10,
            id="gold_job",
            name="Altın güncelleme"
        )

        # Gümüş güncelleme - 10 dakikada bir
        scheduler.add_job(
            lambda: run_with_jitter(fetch_silvers),
            "interval",
            minutes=10,
            id="silver_job",
            name="Gümüş güncelleme"
        )

        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())
        
        logger.info("🚀 Scheduler başlatıldı (10 dakikada bir güncelleme)")

    except Exception as e:
        logger.error(f"❌ Scheduler hata: {e}")

def initial_setup():
    try:
        logger.info("🚀 İlk kurulum başlatılıyor...")
        verify_database_health()
        logger.info("🎉 İlk kurulum tamamlandı!")
    except Exception as e:
        logger.error(f"❌ İlk kurulum hatası: {e}")

logger.info("🔧 KuraBak Backend başlıyor...")

init_connection_pool()
init_db()

if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    initial_setup()
    init_scheduler()

atexit.register(close_all_connections)

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "app": "KuraBak Backend",
        "status": "running",
        "version": "4.1 (Production Ready - 10K+ Users)",
        "endpoints": [
            "/api/currency/all",
            "/api/currency/gold/all",
            "/api/currency/silver/all",
            "/api/update",
            "/health"
        ],
        "features": [
            "Redis cache sistemi",
            "Connection pool yönetimi (2-20)",
            "10 dakikalık otomatik güncelleme",
            "Haftalık otomatik bakım (Pazar 04:00)",
            "30 günlük veri saklama",
            "Jitter ile bot koruması"
        ],
        "timestamp": datetime.now().isoformat()
    })

@app.route("/health", methods=["GET", "HEAD"])
def health():
    try:
        with get_db_cursor() as (conn, cur):
            cur.execute("SELECT COUNT(*) FROM currencies")
            doviz = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM golds")
            altin = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM silvers")
            gumus = cur.fetchone()[0]
            
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('currencies', 'golds', 'silvers')
                ORDER BY table_name
            """)
            existing_tables = [row[0] for row in cur.fetchall()]

        return jsonify({
            "status": "healthy",
            "counts": {
                "doviz": doviz,
                "altin": altin,
                "gumus": gumus
            },
            "database": {
                "tables_count": len(existing_tables),
                "tables": existing_tables,
                "all_present": len(existing_tables) >= 3
            },
            "timestamp": datetime.now().isoformat()
        }), 200

    except Exception as e:
        logger.error(f"❌ Health check hatası: {e}")
        return jsonify({
            "status": "unhealthy", 
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route("/api/update", methods=["POST", "GET"])
def manual_update():
    try:
        logger.info("⚡ Manuel güncelleme tetiklendi...")
        
        g = run_with_jitter(fetch_golds)
        c = run_with_jitter(fetch_currencies)
        s = run_with_jitter(fetch_silvers)

        return jsonify({
            "success": True,
            "results": {
                "gold": g,
                "currency": c,
                "silver": s
            },
            "timestamp": datetime.now().isoformat()
        }), 200

    except Exception as e:
        logger.error(f"❌ Manuel güncelleme hatası: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"🌍 Server aktif → Port: {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
