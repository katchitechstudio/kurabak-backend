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

from models.db import get_db, put_db
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

        # ⭐ Her gece 00:00'da açılış fiyatlarını kaydet
        scheduler.add_job(
            save_daily_opening_prices,
            trigger=CronTrigger(hour=0, minute=0, second=0),
            id="save_opening_prices",
            name="Günlük açılış fiyatları (Altın)",
            replace_existing=True
        )
        logger.info("📅 Günlük açılış fiyatı job'u eklendi (00:00)")

        # 🔥 10 Dakikada bir – Jitter ile birlikte
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
        
        logger.info("🚀 Scheduler başlatıldı (Her 10 dakikada + 00:00 açılış kaydı + jitter).")

    except Exception as e:
        logger.error(f"❌ Scheduler hata: {e}")

# ==========================================
# İLK KURULUM - GÜVENLİ VERSİYON
# ==========================================
def initial_setup():
    """
    Uygulama ilk kez başlatıldığında:
    1. Tüm tabloları kontrol eder/oluşturur
    2. Bugün için açılış fiyatı yoksa kaydet
    """
    try:
        logger.info("🚀 İlk kurulum başlatılıyor...")
        
        # 1. Veritabanı sağlık kontrolü
        verify_database_health()
        
        # 2. Açılış fiyatları kontrolü (güvenli try-except ile)
        try:
            conn = get_db()
            cur = conn.cursor()
            
            cur.execute("""
                SELECT COUNT(*) FROM gold_daily_opening 
                WHERE date = CURRENT_DATE
            """)
            
            count = cur.fetchone()[0]
            
            if count == 0:
                logger.info("📌 Bugün için açılış fiyatı yok, kaydediliyor...")
                cur.close()
                put_db(conn)
                save_daily_opening_prices()
            else:
                logger.info(f"✅ Bugün için {count} açılış fiyatı zaten mevcut")
                cur.close()
                put_db(conn)
                
        except Exception as e:
            logger.warning(f"⚠️ Açılış fiyatı kontrolü atlandı: {e}")
            # İlk deploy'da tablo henüz olmayabilir, devam et
        
        logger.info("🎉 İlk kurulum tamamlandı!")
            
    except Exception as e:
        logger.error(f"❌ İlk kurulum hatası: {e}")
        # Hata olsa bile devam et, scheduler başlasın

# ==========================================
# STARTUP
# ==========================================
logger.info("🔧 KuraBak Backend başlıyor...")

# 1. Önce veritabanı tablolarını oluştur
init_db()

# 2. Scheduler başlamadan önce tek sefer çalışacak işlemler
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    # 3. İlk kurulum kontrolü (tablo doğrulama + açılış fiyatları)
    initial_setup()
    # 4. Scheduler'ı başlat
    init_scheduler()

# ==========================================
# ENDPOINTS
# ==========================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "app": "KuraBak Backend",
        "status": "running",
        "version": "3.0 (Auto-Migration + Daily Opening + Jitter)",
        "endpoints": [
            "/api/currency/all",
            "/api/currency/gold/all",
            "/api/currency/silver/all",
            "/api/update",
            "/health",
            "/api/debug/gold-opening"
        ],
        "features": [
            "Otomatik tablo oluşturma (migration-free)",
            "10 dakikalık otomatik güncelleme",
            "Günlük açılış fiyatı takibi (00:00)",
            "Jitter ile bot koruması",
            "Self-healing database"
        ],
        "timestamp": datetime.now().isoformat()
    })

@app.route("/health", methods=["GET", "HEAD"])
def health():
    try:
        conn = get_db()
        cur = conn.cursor()

        # Tablo sayılarını al
        cur.execute("SELECT COUNT(*) FROM currencies")
        doviz = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM golds")
        altin = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM silvers")
        gumus = cur.fetchone()[0]
        
        # Bugünkü açılış fiyatı sayısı (güvenli kontrol)
        try:
            cur.execute("""
                SELECT COUNT(*) FROM gold_daily_opening 
                WHERE date = CURRENT_DATE
            """)
            acilis = cur.fetchone()[0]
        except:
            acilis = 0  # Tablo yoksa 0 döndür
        
        # Tablo varlık kontrolü
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

        cur.close()
        put_db(conn)

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
    """
    Manuel güncelleme endpoint'i
    Tüm verileri yeniden çeker
    """
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
    """
    TEST AMAÇLI: Açılış fiyatlarını manuel olarak sıfırla ve yeniden kaydet
    Sadece development için kullanın!
    """
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Bugünkü kayıtları sil
        cur.execute("DELETE FROM gold_daily_opening WHERE date = CURRENT_DATE")
        conn.commit()
        
        cur.close()
        put_db(conn)
        
        # Yeniden kaydet
        save_daily_opening_prices()
        
        logger.info("🔄 Açılış fiyatları sıfırlandı ve yeniden kaydedildi")
        
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

@app.route("/api/debug/gold-opening", methods=["GET"])
def debug_gold_opening():
    """
    Bugünkü açılış fiyatlarını kontrol etmek için debug endpoint
    GET /api/debug/gold-opening
    """
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT name, opening_rate, date, 
                   to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at
            FROM gold_daily_opening
            WHERE date = CURRENT_DATE
            ORDER BY name
        """)
        
        columns = [col[0] for col in cur.description]
        data = [dict(zip(columns, row)) for row in cur.fetchall()]
        
        cur.close()
        put_db(conn)
        
        return jsonify({
            'success': True,
            'count': len(data),
            'data': data,
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Debug endpoint hatası: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

# ==========================================
# RUN SERVER
# ==========================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"🌍 Server aktif → Port: {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
