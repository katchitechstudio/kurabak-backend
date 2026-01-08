"""
KuraBak Backend - v5.1 (Unified Redis Edition)
- PostgreSQL bağımlılığı tamamen kaldırıldı.
- Üçlü veri çekme (Döviz, Altın, Gümüş) tek isteğe indirildi.
- Circuit Breaker koruması eklendi.
- Render & Valkey 8 uyumlu.
"""
from flask import Flask, jsonify
from flask_cors import CORS
import logging
from datetime import datetime
import os
import atexit

# Logging Yapılandırması
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config ve Servisler
from config import Config
from services.maintenance_service import start_scheduler, stop_scheduler, fetch_all_data
from routes.general_routes import api_bp
from utils.cache import get_cache, REDIS_ENABLED

# Flask App Başlatma
app = Flask(__name__)
# Tüm originlere izin ver (Frontend erişimi için)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# API Rotalarını Kaydet (Blueprint)
app.register_blueprint(api_bp)

@app.route("/", methods=["GET"])
def home():
    """Ana sayfa - API Durum Paneli"""
    return jsonify({
        "app": "KuraBak Backend",
        "status": "running",
        "version": "5.1 (Unified Redis - Anti-Ban)",
        "endpoints": [
            "/api/currency/popular",
            "/api/currency/gold/popular",
            "/api/currency/silver/all",
            "/health",
            "/api/update"
        ],
        "features": [
            "Unified API Fetching (Döviz+Altın+Gümüş tek istekte)",
            "Circuit Breaker (API Hata Koruması)",
            "Ultra-fast Redis responses (<10ms)",
            "Zero Database overhead (No PostgreSQL)",
            "Auto-update every 120 seconds"
        ],
        "cache_system": "Valkey 8 / Redis" if REDIS_ENABLED else "RAM Fallback",
        "update_interval": "120 seconds",
        "timestamp": datetime.now().isoformat()
    })

@app.route("/health", methods=["GET", "HEAD"])
def health():
    """
    Health Check Endpoint
    Sistemin ve verilerin canlılığını kontrol eder.
    """
    try:
        # Cache'den güncel verileri kontrol et
        currencies_data = get_cache('kurabak:currencies:all')
        golds_data = get_cache('kurabak:golds:all')
        silvers_data = get_cache('kurabak:silvers:all')
        
        c_count = len(currencies_data.get('data', [])) if currencies_data else 0
        g_count = len(golds_data.get('data', [])) if golds_data else 0
        s_count = len(silvers_data.get('data', [])) if silvers_data else 0
        
        # En az bir veri türü varsa sistem sağlıklı kabul edilir
        is_healthy = c_count > 0 or g_count > 0
        
        return jsonify({
            "status": "healthy" if is_healthy else "warming_up",
            "uptime_status": {
                "currencies": c_count,
                "golds": g_count,
                "silvers": s_count
            },
            "redis_active": REDIS_ENABLED,
            "timestamp": datetime.now().isoformat()
        }), 200 if is_healthy else 503

    except Exception as e:
        logger.error(f"❌ Health check hatası: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route("/api/update", methods=["POST", "GET"])
def manual_update():
    """
    Manuel Güncelleme Tetikleyici
    Render veya admin tarafından manuel veri yenilemek için kullanılır.
    """
    try:
        logger.info("⚡ Manuel güncelleme isteği alındı...")
        success = fetch_all_data()
        
        if success:
            return jsonify({
                "success": True, 
                "message": "Tüm finansal veriler başarıyla senkronize edildi."
            }), 200
        else:
            return jsonify({
                "success": False, 
                "message": "API hatası veya Circuit Breaker devrede. Logları kontrol edin."
            }), 503
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def initialize_app():
    """
    Uygulama ayağa kalkarken yapılacak işlemler
    """
    try:
        logger.info("🚀 KuraBak Mimarisi Başlatılıyor...")
        
        # 1. Scheduler'ı Başlat (Otomatik veri çekme döngüsü)
        start_scheduler()
        
        # 2. Uygulama kapandığında scheduler'ı düzgünce durdur
        atexit.register(stop_scheduler)
        
        logger.info("✅ Arka plan görevleri ve Scheduler hazır.")
        
    except Exception as e:
        logger.error(f"❌ Başlatma sırasında kritik hata: {e}")

# Flask'ın debug mode'da iki kez çalışmasını engellemek için kontrol
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    initialize_app()

if __name__ == "__main__":
    # Render tarafından atanan PORT'u al, yoksa 5001 kullan
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"🌍 KuraBak Server Aktif → Port: {port}")
    # Üretim ortamında debug=False olmalıdır
    app.run(host="0.0.0.0", port=port, debug=False)
