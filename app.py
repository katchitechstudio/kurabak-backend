"""
KuraBak Backend - ENTRY POINT V4.6 🚀
=====================================================
✅ V5 API: Tek ve güvenilir kaynak
✅ GERİ BİLDİRİM SİSTEMİ: Telegram entegrasyonu ile kullanıcı mesajları
✅ CİHAZ KAYIT SİSTEMİ: FCM Token yönetimi
✅ BACKUP SYSTEM: 15 dakikalık otomatik yedekleme
✅ TAKVİM BİLDİRİMLERİ: Günü gelen etkinlikler için uyarı
✅ FIREBASE PUSH NOTIFICATIONS: Android bildirimler
✅ ALARM SİSTEMİ: Redis tabanlı fiyat alarmları
✅ SILENT START: Arka plan işlemleri sessizce başlar
✅ İLK KONTROL: Şef uygulama açılır açılmaz sistemi kontrol eder
✅ SUMMARY SYNC FIX: Sterlin sorunu çözüldü
✅ SCHEDULER STATUS FIX: Scheduler durumu artık doğru gösteriliyor
✅ RENDER THREAD FIX: Production'da thread başlatma sorunu çözüldü
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
from routes.alarm_routes import alarm_bp

# Servisler
from services.maintenance_service import start_scheduler, stop_scheduler, supervisor_check

# Utilities
from utils.telegram_monitor import init_telegram_monitor, TelegramMonitor
from utils.notification_service import register_fcm_token, send_test_notification

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
        
        # Render ortamı için özel kontrol
        if os.environ.get("RENDER"):
            cred_path = "/etc/secrets/firebase_credentials.json"
        
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

# Blueprint'leri Kaydet (API Rotaları)
app.register_blueprint(api_bp)
app.register_blueprint(alarm_bp)  # 🔔 ALARM ROUTES

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
    3. Scheduler (Worker + Snapshot + Şef + Takvim + Alarm)
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
    # - Her 5-15dk'da Alarm kontrolü (Yeni!)
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
    logger.info("   🔔 Alarm: Her 5-15 dakikada kontrol ediliyor")
    logger.info("   🔥 Firebase: Push notification sistemi hazır")
    
    # Telegram'a başlangıç mesajı gönder
    if telegram:
        try:
            telegram.send_startup_message()
        except:
            pass

# ======================================
# 🔥 PRODUCTION FIX: Render için thread başlatma
# ======================================

# Render üzerinde mi çalışıyoruz?
is_render = os.environ.get("RENDER") is not None

if is_render:
    # Render'da → Her zaman başlat
    logger.info("🚀 [Render] Production modda thread başlatılıyor...")
    init_thread = threading.Thread(target=background_initialization, daemon=True)
    init_thread.start()
else:
    # Local development → Sadece main process'te başlat
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        logger.info("💻 [Local] Development modda thread başlatılıyor...")
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
            "V5 API (Single Reliable Source)",
            "User Feedback System (Telegram Integration)",
            "FCM Device Registration",
            "Calendar Event Notifications",
            "Firebase Push Notifications (Android)",
            "Price Alarm System (Redis-based)",
            "15-Min Backup System",
            "No-503 Cache Architecture",
            "Worker + Snapshot + Controller + Alarm System",
            "Smart Change Calculation (Snapshot Based)",
            "Weekend Lock (Market Closed Detection)",
            "Trend Analysis (Volatility Alert 🔥)",
            "Self-Healing Mechanism",
            "Instant Supervisor Check on Startup",
            "Summary Sync Fix (Embedded in Currencies)",
            "Scheduler Status Fix (Real-Time State Check)",
            "Render Thread Fix (Production Ready)"
        ],
        "components": {
            "worker": "Her 2 dakikada veri çeker ve değişim hesaplar",
            "snapshot": "Gece 00:00'da referans fiyatları kaydeder",
            "controller": "Her 10 dakikada sistemi denetler ve onarır",
            "calendar": "Her gün 08:00'da etkinlikleri kontrol eder",
            "alarm": "Her 5-15 dakikada fiyat alarmlarını kontrol eder",
            "firebase": "Push notification sistemi (Android)",
            "backup": "15 dakikada bir otomatik yedekleme"
        },
        "data_source": {
            "primary": "V5 API",
            "backup": "15-minute rolling backup"
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
    Şef, Worker, Snapshot, Alarm ve Kaynak durumlarını gösterir
    
    🔥 V4.6: Alarm sistemi bilgisi eklendi
    """
    try:
        from services.maintenance_service import scheduler, get_scheduler_status
        from services.financial_service import get_service_metrics
        from services.alarm_service import get_alarm_stats
        from utils.cache import get_cache
        
        # 🔥 FIX: Scheduler durumunu DOĞRU kontrol et
        scheduler_running = False
        active_job_list = []
        
        if scheduler is not None:
            try:
                # APScheduler state kontrolü (1 = STATE_RUNNING)
                from apscheduler.schedulers import STATE_RUNNING
                scheduler_running = (scheduler.state == STATE_RUNNING)
                
                # Aktif job'ları al
                if scheduler_running:
                    active_job_list = [job.id for job in scheduler.get_jobs()]
            except Exception as sched_err:
                logger.warning(f"⚠️ Scheduler kontrol hatası: {sched_err}")
        
        # Eski fonksiyondan sadece metrics'i al
        scheduler_status = get_scheduler_status()
        metrics = get_service_metrics()
        alarm_stats = get_alarm_stats()
        
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
        
        # Alarm durumu
        last_alarm_check = get_cache(Config.CACHE_KEYS['alarm_last_check'])
        alarm_status = "🟢 Aktif"
        if last_alarm_check:
            time_diff = time.time() - float(last_alarm_check)
            if time_diff > 1800:  # 30 dakikadan fazla
                alarm_status = "🔴 Uyuyor"
            elif time_diff > 900:  # 15 dakikadan fazla
                alarm_status = "🟡 Yavaş"
        else:
            alarm_status = "⚪ Henüz Çalışmadı"
        
        # Aktif kaynak
        data_source = "V5 API"
        
        # Firebase durumu
        firebase_status = "🟢 Aktif" if firebase_admin._apps else "🔴 Devre Dışı"
        
        return jsonify({
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "scheduler": {
                "running": scheduler_running,
                "active_jobs": active_job_list
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
                    "status": "🟢 Aktif" if scheduler_running else "🔴 Durdu"
                },
                "alarm": {
                    "status": alarm_status,
                    "last_check": last_alarm_check,
                    "total_alarms": alarm_stats.get('total_alarms', 0),
                    "unique_users": alarm_stats.get('unique_users', 0),
                    "alarm_types": alarm_stats.get('alarm_types', {})
                },
                "firebase": {
                    "status": firebase_status
                }
            },
            "data_source": {
                "active": data_source,
                "backup": "15-minute rolling backup"
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
# 🔥 GERİ BİLDİRİM & CİHAZ KAYIT SİSTEMİ
# ======================================

@app.route('/api/feedback/send', methods=['POST'])
def send_feedback():
    """
    Kullanıcı geri bildirimlerini Telegram'a iletir
    Günde 1 mesaj sınırı Android tarafında kontrol edilir
    Maksimum 250 karakter sınırı
    """
    try:
        data = request.json
        message = data.get('message', '').strip()
        
        # Validasyon
        if not message:
            return jsonify({"success": False, "error": "Mesaj boş olamaz"}), 400
        
        if len(message) > 250:
            return jsonify({"success": False, "error": "Mesaj çok uzun (max 250 karakter)"}), 400

        # Telegram'a Gönder (Anonim)
        monitor = TelegramMonitor()
        telegram_msg = f"📩 **YENİ GERİ BİLDİRİM**\n\n{message}"
        monitor._send_raw(telegram_msg)
        
        logger.info(f"✅ [Feedback] Anonim mesaj iletildi ({len(message)} karakter)")
        return jsonify({"success": True, "message": "Mesajınız iletildi"}), 200

    except Exception as e:
        logger.error(f"❌ [Feedback] Hata: {e}")
        return jsonify({"success": False, "error": "Sunucu hatası"}), 500

@app.route('/api/device/register', methods=['POST'])
def register_device():
    """
    FCM Token kaydı (Push Notification için)
    """
    try:
        data = request.json
        token = data.get('token')
        
        if not token:
            return jsonify({"success": False, "error": "Token eksik"}), 400
            
        success = register_fcm_token(token)
        
        if success:
            logger.info(f"✅ [FCM] Cihaz kaydedildi")
            return jsonify({"success": True, "message": "Cihaz kaydedildi"}), 200
        else:
            return jsonify({"success": False, "error": "Kayıt başarısız"}), 500

    except Exception as e:
        logger.error(f"❌ [FCM] Token kayıt hatası: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/device/test-push', methods=['GET'])
def trigger_test_push():
    """
    Manuel Push Notification testi
    """
    try:
        result = send_test_notification()
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"❌ [Push Test] Hata: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

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
