"""
KuraBak Backend - ENTRY POINT V4.0 🚀
=====================================================
✅ TRADINGVIEW YEDEK SİSTEMİ: V5 düşerse otomatik geçiş
✅ TELEGRAM KOMUTLARI: Manuel kaynak değiştirme
✅ TAKVİM BİLDİRİMLERİ: Günü gelen etkinlikler için uyarı
✅ FIREBASE PUSH NOTIFICATIONS: Android bildirimler
✅ SILENT START: Arka plan işlemleri sessizce başlar
✅ İLK KONTROL: Şef uygulama açılır açılmaz sistemi kontrol eder
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

# Utilities
from utils.telegram_monitor import init_telegram_monitor

# ======================================
# 🔥 FIREBASE INITIALIZATION
# ======================================
import firebase_admin
from firebase_admin import credentials

def init_firebase():
    """Firebase Admin SDK'yı başlatır"""
    try:
        # Eğer zaten başlatılmışsa tekrar başlatma
        if firebase_admin._apps:
            logger.info("🔥 [Firebase] Zaten başlatılmış, geçiliyor...")
            return True
        
        # Credentials dosyasının varlığını kontrol et
        cred_path = Config.FIREBASE_CREDENTIALS_PATH
        
        if not os.path.exists(cred_path):
            logger.warning(f"⚠️ [Firebase] Credentials dosyası bulunamadı: {cred_path}")
            logger.warning("   Push notification özellikleri devre dışı!")
            return False
        
        # Firebase'i başlat
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        
        logger.info("✅ [Firebase] Admin SDK başarıyla başlatıldı!")
        logger.info(f"   📁 Credentials: {cred_path}")
        return True
        
    except Exception as e:
        logger.error(f"❌ [Firebase] Başlatma hatası: {e}")
        logger.warning("   Push notification özellikleri devre dışı!")
        return False

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
    1. Firebase Admin SDK (Push Notifications)
    2. Telegram Monitor (Sessiz Mod + Komut Sistemi)
    3. Scheduler (Worker + Snapshot + Şef + Takvim)
    4. İLK ŞEF KONTROLÜ (Snapshot yoksa hemen alır!)
    """
    logger.info("⏳ [Arka Plan] Sistem servisleri başlatılıyor...")
    time.sleep(1)  # Kısa bir nefes alma payı
    
    # 1. Firebase'i Başlat
    firebase_status = init_firebase()
    if firebase_status:
        logger.info("🔥 [Firebase] Push notification sistemi aktif!")
    else:
        logger.warning("⚠️ [Firebase] Push notification sistemi devre dışı!")
    
    # 2. Telegram Monitor'ü Başlat (Komut Sistemi Aktif)
    telegram = init_telegram_monitor()
    
    # 3. Scheduler'ı (Zamanlayıcı) Başlat
    # Bu aynı zamanda şunları tetikler:
    # - İlk veri çekme (Worker)
    # - Gece 00:00'da Snapshot (Fotoğrafçı)
    # - Her 10dk'da Şef kontrolü (Controller)
    # - Her gün 08:00'da Takvim kontrolü
    start_scheduler()
    
    # 4. İLK ŞEF KONTROLÜ (Acil Durum Snapshot için)
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
    logger.info("   🗓️ Takvim: Her gün 08:00'da kontrol ediliyor")
    logger.info("   🔥 Firebase: Push notification sistemi hazır")
    
    # Telegram'a başlangıç mesajı gönder
    if telegram:
        try:
            telegram.send_startup_message()
        except:
            pass

# Uygulama başlatıldığında arka plan thread'ini ateşle
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
        "version": Config.APP_VERSION,
        "status": "active",
        "environment": Config.ENVIRONMENT,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "features": [
            "V5 + TradingView Dual Source (V3/V4 Kaldırıldı)",
            "Telegram Manual Source Switch",
            "Calendar Event Notifications",
            "Firebase Push Notifications (Android)",
            "Universal Data Parser",
            "15-Min Backup System",
            "No-503 Cache Architecture",
            "Worker + Snapshot + Controller System",
            "Smart Change Calculation (API Independent)",
            "Weekend Lock (Market Closed Detection)",
            "Trend Analysis (Volatility Alert 🔥)",
            "Self-Healing Mechanism",
            "Instant Supervisor Check on Startup"
        ],
        "components": {
            "worker": "Her 2 dakikada veri çeker ve değişim hesaplar",
            "snapshot": "Gece 00:00'da referans fiyatları kaydeder",
            "controller": "Her 10 dakikada sistemi denetler ve onarır",
            "calendar": "Her gün 08:00'da etkinlikleri kontrol eder",
            "firebase": "Push notification sistemi (Android)"
        },
        "sources": {
            "primary": "V5 API",
            "fallback": "TradingView",
            "manual_switch": "Telegram /source komutları"
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
    Şef, Worker, Snapshot ve Kaynak durumlarını gösterir
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
        
        # Aktif kaynak
        active_source = get_cache(Config.CACHE_KEYS['active_source']) or "v5"
        
        # Firebase durumu
        firebase_status = "🟢 Aktif" if firebase_admin._apps else "🔴 Devre Dışı"
        
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
                },
                "firebase": {
                    "status": firebase_status
                }
            },
            "data_source": {
                "active": active_source,
                "available": ["v5", "tradingview"]
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
    
    # Firebase'i temizle
    try:
        if firebase_admin._apps:
            firebase_admin.delete_app(firebase_admin.get_app())
            logger.info("🔥 [Firebase] Temiz kapanış tamamlandı.")
    except:
        pass
    
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
    logger.info(f"🚀 KuraBak Backend v{Config.APP_VERSION}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
