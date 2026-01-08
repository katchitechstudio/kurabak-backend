"""
KuraBak Backend - v6.0 (Production Ready Edition)
==================================================

Features:
✅ Redis-only architecture (no PostgreSQL)
✅ Unified API fetching (single request)
✅ Circuit breaker protection
✅ Rate limiting
✅ Graceful shutdown
✅ Production-grade error handling
✅ Health checks
✅ Multi-worker safe
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import logging
import os
import sys
import atexit
from datetime import datetime
from functools import wraps
from collections import defaultdict
import time

from config import Config
from services.maintenance_service import (
    start_scheduler, 
    stop_scheduler, 
    fetch_all_data,
    get_scheduler_status
)
from routes.general_routes import api_bp
from utils.cache import get_cache, REDIS_ENABLED

# ======================================
# LOGGING CONFIGURATION
# ======================================

def setup_logging():
    """Environment'a göre logging seviyesi ayarla"""
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    # Gunicorn varsa onun logger'ını kullan
    if os.environ.get('GUNICORN_CMD_ARGS'):
        gunicorn_logger = logging.getLogger('gunicorn.error')
        # Gunicorn logger.level zaten integer, direkt kullan
        logging.basicConfig(
            level=gunicorn_logger.level,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            stream=sys.stdout
        )
        return logging.getLogger(__name__)
    
    # Normal çalışma: string'i integer'a çevir
    numeric_level = getattr(logging, log_level, logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        stream=sys.stdout
    )
    
    return logging.getLogger(__name__)

logger = setup_logging()

# ======================================
# FLASK APP INITIALIZATION
# ======================================

app = Flask(__name__)
app.config.from_object(Config)

# CORS Configuration
allowed_origins = os.environ.get('ALLOWED_ORIGINS', '*').split(',')

if allowed_origins == ['*']:
    logger.warning("⚠️ CORS: Tüm originler kabul ediliyor (production için önerilmez)")
    CORS(app, resources={r"/api/*": {"origins": "*"}})
else:
    logger.info(f"✅ CORS: İzin verilen originler: {allowed_origins}")
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

# ======================================
# RATE LIMITING (Simple)
# ======================================

update_requests = defaultdict(list)
UPDATE_RATE_LIMIT = 5  # İstek sayısı
UPDATE_RATE_WINDOW = 60  # Saniye

def rate_limit_update(f):
    """Rate limiting for /api/update endpoint"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        now = time.time()
        
        # Eski istekleri temizle
        update_requests[client_ip] = [
            req_time for req_time in update_requests[client_ip]
            if now - req_time < UPDATE_RATE_WINDOW
        ]
        
        # Limit kontrolü
        if len(update_requests[client_ip]) >= UPDATE_RATE_LIMIT:
            logger.warning(f"⚠️ Rate limit aşıldı: {client_ip} (/api/update)")
            return jsonify({
                'success': False,
                'error': 'Too many requests',
                'message': f'Limit: {UPDATE_RATE_LIMIT} istek/{UPDATE_RATE_WINDOW} saniye'
            }), 429
        
        # İsteği kaydet
        update_requests[client_ip].append(now)
        return f(*args, **kwargs)
    
    return decorated_function

# ======================================
# ROUTES
# ======================================

# API blueprint'ini kaydet
app.register_blueprint(api_bp)

@app.route("/", methods=["GET"])
def home():
    """Ana sayfa - API durumu"""
    return jsonify({
        "app": "KuraBak Backend",
        "version": "6.0",
        "status": "running",
        "description": "Production-ready financial data API",
        "endpoints": {
            "api": {
                "/api/currency/popular": "Popüler döviz kurları (15)",
                "/api/currency/gold/popular": "Popüler altın fiyatları (5)",
                "/api/currency/silver/all": "Gümüş fiyatı",
                "/api/metrics": "API metrikleri",
                "/api/health": "Sağlık kontrolü"
            },
            "admin": {
                "/health": "Sistem sağlığı",
                "/status": "Scheduler durumu",
                "/api/update": "Manuel güncelleme (POST, rate limited)"
            }
        },
        "features": [
            "Unified API fetching (tek istek)",
            "Circuit breaker protection",
            "Redis caching (ultra-fast)",
            "Rate limiting",
            "Graceful shutdown",
            f"Auto-update every {Config.UPDATE_INTERVAL}s"
        ],
        "cache": "Redis/Valkey" if REDIS_ENABLED else "Memory fallback",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route("/health", methods=["GET", "HEAD"])
def health():
    """
    Health Check Endpoint (Render/monitoring için)
    """
    try:
        # Cache'den verileri kontrol et
        currencies = get_cache('kurabak:currencies:all', Config.CACHE_TTL)
        golds = get_cache('kurabak:golds:all', Config.CACHE_TTL)
        silvers = get_cache('kurabak:silvers:all', Config.CACHE_TTL)
        
        c_count = len(currencies.get('data', [])) if currencies else 0
        g_count = len(golds.get('data', [])) if golds else 0
        s_count = len(silvers.get('data', [])) if silvers else 0
        
        # Veri yaşını kontrol et
        is_fresh = False
        data_age = None
        
        if currencies and currencies.get('update_date'):
            try:
                update_time = datetime.fromisoformat(currencies['update_date'])
                data_age = (datetime.now() - update_time).total_seconds()
                is_fresh = data_age < 300  # 5 dakikadan taze mi?
            except:
                pass
        
        # Sağlık kontrolü: Her üç veri de olmalı ve taze olmalı
        is_healthy = (c_count >= 10 and g_count >= 3 and s_count >= 1 and is_fresh)
        
        status = 'healthy' if is_healthy else 'degraded'
        http_code = 200 if is_healthy else 503
        
        response = {
            "status": status,
            "data": {
                "currencies": {"count": c_count, "ok": c_count >= 10},
                "golds": {"count": g_count, "ok": g_count >= 3},
                "silvers": {"count": s_count, "ok": s_count >= 1}
            },
            "data_age_seconds": data_age,
            "data_fresh": is_fresh,
            "redis_enabled": REDIS_ENABLED,
            "timestamp": datetime.now().isoformat()
        }
        
        # HEAD request için body gönderme
        if request.method == 'HEAD':
            return '', http_code
        
        return jsonify(response), http_code
    
    except Exception as e:
        logger.error(f"❌ Health check hatası: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500


@app.route("/status", methods=["GET"])
def status():
    """
    Scheduler ve circuit breaker durumu
    """
    try:
        scheduler_status = get_scheduler_status()
        
        return jsonify({
            "status": "ok",
            "scheduler": scheduler_status,
            "redis_enabled": REDIS_ENABLED,
            "config": {
                "update_interval": Config.UPDATE_INTERVAL,
                "cache_ttl": Config.CACHE_TTL
            },
            "timestamp": datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"❌ Status endpoint hatası: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@app.route("/api/update", methods=["POST"])
@rate_limit_update
def manual_update():
    """
    Manuel güncelleme tetikleyici
    Sadece POST, rate limited
    """
    try:
        logger.info(f"⚡ Manuel güncelleme isteği: {request.remote_addr}")
        
        success = fetch_all_data()
        
        if success:
            return jsonify({
                "success": True,
                "message": "Tüm finansal veriler başarıyla güncellendi",
                "timestamp": datetime.now().isoformat()
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Güncelleme başarısız (circuit breaker aktif olabilir)",
                "info": "Birkaç dakika sonra tekrar deneyin"
            }), 503
    
    except Exception as e:
        logger.error(f"❌ Manuel güncelleme hatası: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ======================================
# ERROR HANDLERS
# ======================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Not found",
        "message": "Bu endpoint bulunamadı",
        "available_endpoints": [
            "/",
            "/health",
            "/status",
            "/api/currency/popular",
            "/api/currency/gold/popular",
            "/api/currency/silver/all"
        ]
    }), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"❌ 500 Internal Server Error: {error}")
    return jsonify({
        "error": "Internal server error",
        "message": "Sunucu hatası oluştu"
    }), 500


@app.errorhandler(429)
def rate_limit_exceeded(error):
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "Çok fazla istek gönderdiniz, lütfen bekleyin"
    }), 429

# ======================================
# APPLICATION INITIALIZATION
# ======================================

_initialized = False
_init_lock = None

def initialize_app():
    """
    Uygulama başlatma (tek sefer)
    Multi-worker ortamda bile güvenli
    """
    global _initialized, _init_lock
    
    # Thread lock kullan (multi-threaded ortam için)
    import threading
    if _init_lock is None:
        _init_lock = threading.Lock()
    
    with _init_lock:
        if _initialized:
            logger.warning("⚠️ App zaten initialize edilmiş, atlanıyor")
            return
        
        try:
            pid = os.getpid()
            logger.info(f"🚀 KuraBak Backend başlatılıyor (PID: {pid})...")
            logger.info(f"📦 Python: {sys.version}")
            logger.info(f"🌍 Environment: {os.environ.get('FLASK_ENV', 'production')}")
            logger.info(f"💾 Redis: {'Enabled' if REDIS_ENABLED else 'Disabled (fallback)'}")
            
            # Scheduler'ı başlat
            scheduler = start_scheduler()
            
            if scheduler:
                logger.info("✅ Scheduler başarıyla başlatıldı")
            else:
                logger.error("❌ Scheduler başlatılamadı!")
            
            # Graceful shutdown için cleanup kaydet
            atexit.register(cleanup_on_exit)
            
            _initialized = True
            logger.info("✅ Uygulama hazır!")
        
        except Exception as e:
            logger.error(f"❌ Başlatma hatası: {e}", exc_info=True)
            sys.exit(1)


def cleanup_on_exit():
    """
    Uygulama kapanırken cleanup
    """
    logger.info("🛑 Uygulama kapatılıyor...")
    stop_scheduler()
    logger.info("✅ Cleanup tamamlandı")

# ======================================
# MAIN ENTRY POINT
# ======================================

# Flask debug mode'da iki kere başlatmayı engelle
# Gunicorn/production'da da güvenli
if __name__ == "__main__":
    # Development mode
    initialize_app()
    
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_ENV") == "development"
    
    logger.info(f"🌍 Server starting on port {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)

else:
    # Production mode (Gunicorn)
    # Sadece ilk worker initialize etsin
    worker_id = os.environ.get('GUNICORN_WORKER_ID')
    
    if worker_id is None or worker_id == '1' or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        initialize_app()
