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
from services.gold_service import fetch_golds, save_daily_opening_prices
from services.silver_service import fetch_silvers

from routes.general_routes import api_bp

from models.db import get_db_cursor, init_connection_pool, close_all_connections
from models.currency_models import init_db, verify_database_health

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
    Scraper çalışmadan önce 0-25 saniye arasında bekletir
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

        # ⭐ Her gece 00:00'da açılış fiyatlarını kaydet
        scheduler.add_job(
            save_daily_opening_prices,
            trigger=CronTrigger(hour=0, minute=0, second=0),
            id="save_opening_prices",
            name="Günlük açılış fiyatları (Altın)",
            replace_existing=True
        )
        logger.info("📅 Günlük açılış fiyatı job'u eklendi (00:00)")

        # 🔥 10 Dakikada bir güncelleme
        scheduler.add_job(
            lambda: run_with_jitter(fetch_currencies),
            "interval",
            minutes=10,
            id="currency_job",
            name="Döviz güncelleme"
        )

        scheduler.add_job(
            lambda: run_with_jitter(fetch_golds),
            "interval",
            minutes=10,
            id="gold_job",
            name="Altın güncelleme"
        )

        scheduler.add_job(
            lambda: run_with_jitter(fetch_silvers),
            "interval",
            minutes=10,
            id="silver_job",
            name="Gümüş güncelleme"
        )

        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())
        
        logger.info("🚀 Scheduler başlatıldı")

    except Exception as e:
        logger.error(f"❌ Scheduler hata: {e}")

# ==========================================
# İLK KURULUM
# ==========================================
def initial_setup():
    """
    Uygulama başlatma rutini
    """
    try:
        logger.info("🚀 İlk kurulum başlatılıyor...")
        
        # Veritabanı sağlık kontrolü
        verify_database_health()
        
        # Açılış fiyatları kontrolü
        try:
            with get_db_cursor() as (conn, cur):
                cur.execute("""
                    SELECT COUNT(*) FROM gold_daily_opening 
                    WHERE date = CURRENT_DATE
                """)
                
                count = cur.fetchone()[0]
                
                if count == 0:
                    logger.info("📌 Bugün için açılış fiyatı yok, kaydediliyor...")
                    save_daily_opening_prices()
                else:
                    logger.info(f"✅ Bugün için {count} açılış fiyatı zaten mevcut")
                    
        except Exception as e:
            logger.warning(f"⚠️ Açılış fiyatı kontrolü atlandı: {e}")
        
        logger.info("🎉 İlk kurulum tamamlandı!")
            
    except Exception as e:
        logger.error(f"❌ İlk kurulum hatası: {e}")

# ==========================================
# STARTUP
# ==========================================
logger.info("🔧 KuraBak Backend başlıyor...")

# Connection pool oluştur
init_connection_pool()

# Veritabanı tablolarını oluştur
init_db()

# İlk kurulum ve scheduler
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    initial_setup()
    init_scheduler()

# Uygulama kapanırken bağlantıları kapat
atexit.register(close_all_connections)

# ==========================================
# ENDPOINTS
# ==========================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "app": "KuraBak Backend",
        "status": "running",
        "version": "3.1 (Connection Pool + Auto-Migration)",
        "endpoints": [
            "/api/currency/all",
            "/api/currency/gold/all",
            "/api/currency/silver/all",
            "/api/update",
            "/health"
        ],
        "features": [
            "Connection pool yönetimi",
            "Otomatik tablo oluşturma",
            "10 dakikalık otomatik güncelleme",
            "Günlük açılış fiyatı takibi (00:00)",
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
            
            try:
                cur.execute("""
                    SELECT COUNT(*) FROM gold_daily_opening 
                    WHERE date = CURRENT_DATE
                """)
                acilis = cur.fetchone()[0]
            except:
                acilis = 0
            
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN (
                    'currencies', 'golds', 'silvers', 
                    'gold_daily_opening', 'currency_history', 
                    'gold_history', 'silver_history'
                )
                ORDER BY table_name
            """)
            existing_tables = [row[0] for row in cur.fetchall()]

        return jsonify({
            "status": "healthy",
            "counts": {
                "doviz": doviz,
                "altin": altin,
                "gumus": gumus,
                "bugun_acilis_kaydi": acilis
            },
            "database": {
                "tables_count": len(existing_tables),
                "tables": existing_tables,
                "all_present": len(existing_tables) == 7
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

@app.route("/api/opening-prices/reset", methods=["POST"])
def reset_opening_prices():
    try:
        with get_db_cursor() as (conn, cur):
            cur.execute("DELETE FROM gold_daily_opening WHERE date = CURRENT_DATE")
            conn.commit()
        
        save_daily_opening_prices()
        
        logger.info("🔄 Açılış fiyatları sıfırlandı")
        
        return jsonify({
            "success": True,
            "message": "Açılış fiyatları sıfırlandı"
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Reset hatası: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ==========================================
# RUN SERVER
# ==========================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"🌍 Server aktif → Port: {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
