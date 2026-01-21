"""
KuraBak Backend - ENTRY POINT (ASYNCHRONOUS & FAST) 🚀
=====================================================
✅ RENDER/HEROKU READY: Port timeout sorununu çözen asenkron yapı.
✅ NO 503: Başlangıçta bile cache boşsa 'Stale' veya boş liste döner, hata vermez.
✅ SILENT START: Arka plan işlemleri sessizce başlar.
✅ BLUEPRINT ARCHITECTURE: Modüler yapı.
✅ WORKER + SNAPSHOT + ŞEF SİSTEMİ: Akıllı backend mimarisi
✅ İLK KONTROL: Şef uygulama açılır açılmaz sistemi kontrol eder (10dk beklemez!)
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
from services.maintenance_service import start_scheduler, stop_scheduler, supervisor_check
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
    
    BAŞLATMA SIRASI:
    1. Telegram Monitor (Sessiz Mod)
    2. Scheduler (Worker + Snapshot + Şef)
    3. 🔥 İLK ŞEF KONTROLÜ (Snapshot yoksa hemen alır!)
    """
    logger.info("⏳ [Arka Plan] Sistem servisleri başlatılıyor...")
    time.sleep(1)  # Kısa bir nefes alma payı
    
    # 1. Telegram Monitor'ü Başlat (Sessiz Mod)
    telegram = init_telegram_monitor()
    
    # 2. Scheduler'ı (Zamanlayıcı) Başlat
    # Bu aynı zamanda şunları tetikler:
    # - İlk veri çekme (Worker)
    # - Gece 00:00'da Snapshot (Fotoğrafçı)
    # - Her 10dk'da Şef kontrolü (Controller)
    start_scheduler()
    
    # 3. 🔥 İLK ŞEF KONTROLÜ (Acil Durum Snapshot için)
    logger.info("👮 [İlk Kontrol] Şef sistemi kontrol ediyor...")
    logger.info("   📸 Snapshot yoksa hemen alınacak")
    logger.info("   👷 İşçi uyuyorsa uyandırılacak")
    logger.info("   🧪 Zehirli veri varsa temizlenecek")
    
    try:
        supervisor_check()
        logger.info("✅ [İlk Kontrol] Şef kontrolü tamamlandı!")
    except Exception as e:
        logger.error(f"⚠️ [İlk Kontrol] Şef hatası: {e}")
    
    logger.info("✅ [Arka Plan] Tüm sistemler devrede!")
    logger.info("   👷 İşçi (Worker): 2 dakikada bir çalışıyor")
    logger.info("   📸 Fotoğrafçı (Snapshot): Gece 00:00'da çalışacak")
    logger.info("   👮 Şef (Controller): 10 dakikada bir denetliyor")
    
    # Telegram'a başlangıç mesajı gönder (İsteğe bağlı)
    if telegram:
        try:
            telegram.send_startup_message()
        except:
            pass

# Uygulama başlatıldığında arka plan thread'ini ateşle
# Gunicorn birden fazla worker çalıştırırsa her biri için çalışır (güvenlidir)
if os.environ.get("WERKZEUG_RUN_MAIN") != "true":  # Sadece ana proseste
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
        "version": "2.0.1",  # 🔥 Yeni Versiyon (İlk Şef Kontrolü eklendi)
        "status": "active",
        "environment": Config.ENVIRONMENT,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "features": [
            "Triple Fallback API (V5/V4/V3)",
            "Universal Data Parser",
            "15-Min Backup System",
            "No-503 Cache Architecture",
            "Worker + Snapshot + Controller System",
            "Smart Change Calculation (API Independent)",
            "Weekend Lock (Market Closed Detection)",
            "Trend Analysis (Volatility Alert 🔥)",
            "Self-Healing Mechanism",
            "Instant Supervisor Check on Startup"  # 🔥 YENİ
        ],
        "components": {
            "worker": "Her 2 dakikada veri çeker ve değişim hesaplar",
            "snapshot": "Gece 00:00'da referans fiyatları kaydeder",
            "controller": "Her 10 dakikada sistemi denetler ve onarır (İlk kontrol: Başlangıçta)"
        }
    }), 200

@app.route('/health', methods=['GET'])
def health():
    """Basit Sağlık Kontrolü (Load Balancer için)"""
    return jsonify({"status": "ok"}), 200

@app.route('/api/system/status', methods=['GET'])
def system_status():
    """
    Detaylı Sistem Durumu
    Şef, Worker ve Snapshot durumlarını gösterir
    """
    try:
        from services.maintenance_service import get_scheduler_status
        from services.financial_service import get_service_metrics
        from utils.cache import get_cache
        
        scheduler_status = get_scheduler_status()
        metrics = get_service_metrics()
        
        # Son worker çalışma zamanı
        last_worker_run = get_cache("kurabak:last_worker_run")
        worker_status = "🟢 Aktif"
        if last_worker_run:
            time_diff = time.time() - float(last_worker_run)
            if time_diff > 600:  # 10 dakikadan fazla
                worker_status = "🔴 Uyuyor"
            elif time_diff > 300:  # 5 dakikadan fazla
                worker_status = "🟡 Yavaş"
        else:
            worker_status = "⚪ Henüz Çalışmadı"
        
        # Snapshot durumu
        snapshot_exists = bool(get_cache("kurabak:yesterday_prices"))
        snapshot_status = "🟢 Mevcut" if snapshot_exists else "🔴 Kayıp"
        
        return jsonify({
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "scheduler": {
                "running": scheduler_status.get("running", False),
                "active_jobs": scheduler_status.get("jobs", [])
            },
            "components": {
                "worker": {
                    "status": worker_status,
                    "last_run": last_worker_run
                },
                "snapshot": {
                    "status": snapshot_status
                },
                "controller": {
                    "status": "🟢 Aktif" if scheduler_status.get("running") else "🔴 Durdu"
                }
            },
            "circuit_breaker": scheduler_status.get("circuit_breaker", {}),
            "metrics": metrics
        }), 200
        
    except Exception as e:
        logger.error(f"System status error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ======================================
# TEMİZLİK (SHUTDOWN)
# ======================================

def on_exit():
    """Uygulama kapanırken çalışır"""
    logger.info("🛑 Uygulama kapatılıyor...")
    stop_scheduler()
    logger.info("✅ Temiz kapanış tamamlandı.")

atexit.register(on_exit)

# ======================================
# BAŞLATMA
# ======================================

if __name__ == '__main__':
    # Local Development
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"🌍 Local Sunucu Başlatılıyor: http://localhost:{port}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("🚀 KuraBak Backend v2.0.1")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
