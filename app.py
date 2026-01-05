"""
KuraBak Backend - Redis Only
PostgreSQL bağımlılığı tamamen kaldırıldı
"""
from flask import Flask, jsonify
from flask_cors import CORS
import logging
from datetime import datetime
import os
import atexit

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config ve servisler
from config import Config
from services.maintenance_service import start_scheduler, stop_scheduler, fetch_all_data
from routes.general_routes import api_bp
from utils.cache import get_cache

# Flask app
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Blueprint kaydet
app.register_blueprint(api_bp)


@app.route("/", methods=["GET"])
def home():
    """Ana sayfa - API bilgileri"""
    return jsonify({
        "app": "KuraBak Backend",
        "status": "running",
        "version": "5.0 (Redis Only - Ultra Fast)",
        "endpoints": [
            "/api/currency/popular",
            "/api/currency/gold/popular",
            "/api/currency/silver/all",
            "/api/currency/all (deprecated)",
            "/api/currency/gold/all (deprecated)",
            "/health",
            "/api/update"
        ],
        "features": [
            "Redis-only architecture (no PostgreSQL)",
            "Ultra-fast response times (<10ms)",
            "90-second auto-update interval",
            "Fallback mechanism for cold starts",
            "Zero data accumulation",
            "Free hosting on Render"
        ],
        "cache_ttl": "300 seconds (5 minutes)",
        "update_interval": "90 seconds (1.5 minutes)",
        "timestamp": datetime.now().isoformat()
    })


@app.route("/health", methods=["GET", "HEAD"])
def health():
    """
    Health check endpoint
    Redis cache durumunu kontrol eder
    """
    try:
        # Redis'ten veri sayılarını al
        currencies_data = get_cache('kurabak:currencies:all', ttl_seconds=300)
        golds_data = get_cache('kurabak:golds:all', ttl_seconds=300)
        silvers_data = get_cache('kurabak:silvers:all', ttl_seconds=300)
        
        currency_count = len(currencies_data.get('data', [])) if currencies_data else 0
        gold_count = len(golds_data.get('data', [])) if golds_data else 0
        silver_count = len(silvers_data.get('data', [])) if silvers_data else 0
        
        # Tüm veriler mevcut mu?
        all_healthy = currency_count > 0 and gold_count > 0 and silver_count > 0
        
        return jsonify({
            "status": "healthy" if all_healthy else "warming_up",
            "storage": "Redis (Valkey 8)",
            "counts": {
                "currencies": currency_count,
                "golds": gold_count,
                "silvers": silver_count
            },
            "cache_status": {
                "currencies": "cached" if currencies_data else "empty",
                "golds": "cached" if golds_data else "empty",
                "silvers": "cached" if silvers_data else "empty"
            },
            "timestamp": datetime.now().isoformat()
        }), 200 if all_healthy else 503

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
    Tüm verileri API'den çeker ve Redis'e yazar
    """
    try:
        logger.info("⚡ Manuel güncelleme tetiklendi...")
        
        success = fetch_all_data()
        
        if success:
            return jsonify({
                "success": True,
                "message": "Tüm veriler başarıyla güncellendi",
                "timestamp": datetime.now().isoformat()
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Bazı veriler güncellenemedi",
                "timestamp": datetime.now().isoformat()
            }), 500

    except Exception as e:
        logger.error(f"❌ Manuel güncelleme hatası: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


def initialize_app():
    """
    Uygulama başlangıç işlemleri
    """
    try:
        logger.info("🚀 KuraBak Backend başlatılıyor...")
        
        # Redis bağlantısı kontrol et
        from utils.cache import REDIS_ENABLED
        if REDIS_ENABLED:
            logger.info("✅ Redis bağlantısı aktif")
        else:
            logger.warning("⚠️ Redis bağlantısı yok, RAM cache kullanılıyor")
        
        # Scheduler'ı başlat (90 saniyede bir güncelleme)
        start_scheduler()
        
        # Temiz kapanış için atexit kaydı
        atexit.register(stop_scheduler)
        
        logger.info("🎉 KuraBak Backend başarıyla başlatıldı!")
        
    except Exception as e:
        logger.error(f"❌ Başlatma hatası: {e}")
        raise


# Uygulama başlatma (debug mode'da sadece bir kez çalışsın)
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    initialize_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"🌍 Server başlatılıyor → Port: {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
