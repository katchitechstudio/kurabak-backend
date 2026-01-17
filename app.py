"""
KuraBak Backend - ENTRY POINT (ASYNCHRONOUS & FAST) 🚀
=====================================================
✅ RENDER/HEROKU READY: Port timeout sorununu çözen asenkron yapı.
✅ NO 503: Başlangıçta bile cache boşsa 'Stale' veya boş liste döner, hata vermez.
✅ SILENT START: Arka plan işlemleri sessizce başlar.
✅ BLUEPRINT ARCHITECTURE: Modüler yapı.
"""

import os
import logging
import threading
import time
import atexit
from datetime import datetime

from flask import Flask, jsonify, request
from flask_cors import CORS

from config import Config
# Route'lar
from routes.general_routes import api_bp
# Servisler
from services.maintenance_service import start_scheduler, stop_scheduler
from utils.telegram_monitor import init_telegram_monitor

# ======================================
# LOGGING AYARLARI
# ======================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("KuraBak")

# ======================================
# FLASK APP KURULUMU
# ======================================

app = Flask(__name__)
app.config.from_object(Config)

# CORS (Çapraz Platform İzinleri)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Blueprint'i Kaydet (API Rotaları)
app.register_blueprint(api_bp)

# ======================================
# ASENKRON BAŞLATICI (CRITICAL)
# ======================================

def background_initialization():
    """
    Ağır işleri arka planda yapar.
    Böylece Flask anında ayağa kalkar ve Render portu kapatmaz.
    """
    logger.info("⏳ [Arka Plan] Sistem servisleri başlatılıyor...")
    time.sleep(1) # Kısa bir nefes alma payı
    
    # 1. Telegram Monitor'ü Başlat (Sessiz Mod)
    init_telegram_monitor()
    
    # 2. Scheduler'ı (Zamanlayıcı) Başlat
    # Bu aynı zamanda ilk veri çekme işlemini de tetikler (maintenance_service içinde)
    start_scheduler()
    
    logger.info("✅ [Arka Plan] Tüm sistemler devrede!")

# Uygulama başlatıldığında arka plan thread'ini ateşle
# Gunicorn birden fazla worker çalıştırırsa her biri için çalışır (güvenlidir)
if os.environ.get("WERKZEUG_RUN_MAIN") != "true": # Sadece ana proseste
    init_thread = threading.Thread(target=background_initialization, daemon=True)
    init_thread.start()

# ======================================
# TEMEL ENDPOINTLER
# ======================================

@app.route('/', methods=['GET'])
def index():
    """Health Check & Info"""
    return jsonify({
        "app": Config.APP_NAME,
        "version": Config.APP_VERSION,
        "status": "active",
        "environment": Config.ENVIRONMENT,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "features": [
            "Triple Fallback API (V5/V4/V3)",
            "Universal Data Parser",
            "15-Min Backup System",
            "No-503 Cache Architecture"
        ]
    }), 200

@app.route('/health', methods=['GET'])
def health():
    """Basit Sağlık Kontrolü (Load Balancer için)"""
    return jsonify({"status": "ok"}), 200

# ======================================
# TEMİZLİK (SHUTDOWN)
# ======================================

def on_exit():
    """Uygulama kapanırken çalışır"""
    logger.info("🛑 Uygulama kapatılıyor...")
    stop_scheduler()

atexit.register(on_exit)

# ======================================
# BAŞLATMA
# ======================================

if __name__ == '__main__':
    # Local Development
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"🌍 Local Sunucu Başlatılıyor: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
