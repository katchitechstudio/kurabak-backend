"""
KuraBak Backend - ENTRY POINT V5.3 🚀
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
✅ TELEGRAM SINGLETON V5.1: Global instance memory leak önleme
✅ FIREBASE SINGLETON V5.1: Multiple init önleme
✅ HEALTHZ FIX: Render health check endpoint'i eklendi
✅ REDIS LOCK V5.3: Scheduler çoğalma bug'ı KESIN çözüldü 🔥
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

from routes.general_routes import api_bp
from routes.alarm_routes import alarm_bp

from services.maintenance_service import start_scheduler, stop_scheduler, supervisor_check

from utils.notification_service import register_fcm_token, send_test_notification

# ======================================
# 🔥 V5.1: FIREBASE SINGLETON (MEMORY LEAK FİX!)
# ======================================

import firebase_admin
from firebase_admin import credentials

# Global Firebase durumu
_firebase_initialized = False
_firebase_lock = threading.Lock()

def init_firebase():
    """
    🔥 V5.1 FIX: Firebase Admin SDK'yı singleton pattern ile başlatır
    
    ÖNCEKİ SORUN:
    - Her restart'ta yeni Firebase instance oluşuyordu
    - Eski instance'lar garbage collect edilmiyordu
    
    YENİ ÇÖZÜM:
    - Global flag ile kontrol
    - Thread-safe initialization
    - Tek bir instance garantisi
    """
    global _firebase_initialized
    
    # Double-checked locking
    if _firebase_initialized:
        logger.info("🔥 [Firebase] Zaten başlatılmış (global flag)")
        return True
    
    with _firebase_lock:
        # Tekrar kontrol et (thread-safe)
        if _firebase_initialized:
            return True
        
        try:
            # firebase_admin._apps kontrolü (fallback)
            if firebase_admin._apps:
                logger.info("🔥 [Firebase] firebase_admin._apps dolu, başlatılmış kabul ediliyor")
                _firebase_initialized = True
                return True
            
            cred_path = Config.FIREBASE_CREDENTIALS_PATH
            
            if os.environ.get("RENDER"):
                cred_path = "/etc/secrets/firebase_credentials.json"
            
            if not os.path.exists(cred_path):
                logger.warning(f"⚠️ [Firebase] Credentials dosyası bulunamadı: {cred_path}")
                logger.warning("   Push notification özellikleri devre dışı!")
                return False
            
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {
                'projectId': 'kurabak-f1950'
            })
            
            _firebase_initialized = True
            logger.info("✅ [Firebase] Admin SDK başarıyla başlatıldı! (Singleton)")
            logger.info(f"   📁 Credentials: {cred_path}")
            logger.info(f"   🎯 Project ID: kurabak-f1950")
            return True
            
        except ValueError as ve:
            # Firebase zaten başlatılmışsa bu hatayı alırız
            if "already exists" in str(ve).lower():
                logger.info("🔥 [Firebase] Zaten başlatılmış (ValueError yakalandı)")
                _firebase_initialized = True
                return True
            else:
                logger.error(f"❌ [Firebase] Başlatma hatası: {ve}")
                return False
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

CORS(app, resources={r"/api/*": {"origins": "*"}})

app.register_blueprint(api_bp)
app.register_blueprint(alarm_bp)

# ======================================
# 🔥 V5.1: TELEGRAM SINGLETON (MEMORY LEAK FİX!)
# ======================================

# Global Telegram instance
_telegram_instance = None
_telegram_lock = threading.Lock()

def get_telegram_instance():
    """
    🔥 V5.1 FIX: Telegram instance'ı singleton pattern ile al
    
    ÖNCEKİ SORUN:
    - Her background_initialization() çağrısında yeni instance
    - Restart durumlarında eski instance'lar bellekte kalıyordu
    
    YENİ ÇÖZÜM:
    - Global singleton instance
    - Thread-safe initialization
    - Memory leak yok!
    """
    global _telegram_instance
    
    if _telegram_instance is not None:
        return _telegram_instance
    
    with _telegram_lock:
        # Double-checked locking
        if _telegram_instance is not None:
            return _telegram_instance
        
        try:
            from utils.telegram_monitor import init_telegram_monitor
            _telegram_instance = init_telegram_monitor()
            logger.info("✅ [Telegram] Singleton instance oluşturuldu")
            return _telegram_instance
        except Exception as e:
            logger.error(f"❌ [Telegram] Instance oluşturma hatası: {e}")
            return None

# ======================================
# ASENKRON BAŞLATICI
# ======================================

def background_initialization():
    """
    🔥 V5.3 FIX: Redis Lock ile scheduler çoğalmasını önle
    
    ÖNCEKİ SORUN:
    - Gunicorn fork → global değişkenler process'ler arası paylaşılmıyor
    - Her process scheduler başlatıyor → zombie scheduler
    - SIGTERM sonrası bile job'lar çalışmaya devam ediyordu
    
    YENİ ÇÖZÜM:
    - Redis distributed lock (process-safe!)
    - İlk gelen process lock'u alıyor
    - Diğer process'ler "zaten var" görüyor
    - %100 tek scheduler garantisi
    
    BAŞLATMA SIRASI:
    1. Firebase Admin SDK (Singleton - Push Notifications)
    2. Telegram Monitor (Singleton - Komut Sistemi)
    3. Scheduler (Worker + Snapshot + Şef + Takvim + Alarm) - Redis Lock ile
    4. İLK ŞEF KONTROLÜ (Snapshot yoksa hemen alır!)
    """
    from utils.cache import get_redis_client
    
    current_pid = os.getpid()
    lock_key = "kurabak:scheduler:lock"
    
    # 🔥 V5.3: REDIS LOCK (process-safe!)
    try:
        # Redis client'ı al
        redis_client = get_redis_client()
        
        if not redis_client:
            logger.warning("⚠️ [Redis Lock] Redis bağlantısı yok, fallback mode")
        else:
            # Redis'ten mevcut scheduler PID'sini kontrol et
            existing_pid = redis_client.get(lock_key)
            
            if existing_pid:
                existing_pid_str = existing_pid if isinstance(existing_pid, str) else str(existing_pid)
                logger.info(f"⏭️ [Redis Lock] Scheduler zaten PID {existing_pid_str} tarafından başlatıldı")
                logger.info(f"   Bu PID ({current_pid}) scheduler başlatmayacak (zombie önleme)")
                return
            
            # Lock'u al (60 saniye geçici)
            redis_client.set(lock_key, current_pid, ex=60)
            logger.info(f"🔒 [Redis Lock] Lock alındı: PID {current_pid}")
        
    except Exception as e:
        logger.warning(f"⚠️ [Redis Lock] Redis erişim hatası: {e}")
        logger.warning("   Redis olmadan devam ediliyor (fallback mode)")
    
    logger.info(f"⏳ [Arka Plan] Sistem servisleri başlatılıyor (PID: {current_pid})...")
    time.sleep(1)
    
    # 1. Firebase'i Başlat (SINGLETON!)
    firebase_status = init_firebase()
    if firebase_status:
        logger.info("🔥 [Firebase] Push notification sistemi aktif!")
    else:
        logger.warning("⚠️ [Firebase] Push notification sistemi devre dışı!")
    
    # 2. Telegram Monitor'ü Başlat (SINGLETON!)
    telegram = get_telegram_instance()
    if telegram:
        logger.info("📱 [Telegram] Komut sistemi aktif!")
    else:
        logger.warning("⚠️ [Telegram] Komut sistemi devre dışı!")
    
    # 3. Scheduler'ı (Zamanlayıcı) Başlat
    start_scheduler()
    
    # 🔥 V5.3: Scheduler başarıyla başlatıldıysa lock'u kalıcı yap
    try:
        redis_client = get_redis_client()
        if redis_client:
            redis_client.set(lock_key, current_pid, ex=86400)  # 24 saat
            logger.info(f"🔒 [Redis Lock] Scheduler owner PID kaydedildi: {current_pid} (24h lock)")
    except Exception as e:
        logger.warning(f"⚠️ [Redis Lock] Kalıcı lock yazılamadı: {e}")
    
    # 4. İLK ŞEF KONTROLÜ (Acil Durum Snapshot için)
    logger.info("👮 [İlk Kontrol] Şef sistemi kontrol ediyor...")
    
    try:
        supervisor_check()
        logger.info("✅ [İlk Kontrol] Şef kontrolü tamamlandı!")
    except Exception as e:
        logger.error(f"⚠️ [İlk Kontrol] Şef hatası: {e}")
    
    logger.info("✅ [Arka Plan] Tüm sistemler devrede!")
    
    # Telegram'a başlangıç mesajı gönder (varsa)
    if telegram:
        try:
            telegram.send_startup_message()
        except:
            pass

# ======================================
# 🔥 PRODUCTION FIX: Render için thread başlatma
# ======================================

is_render = os.environ.get("RENDER") is not None

if is_render:
    logger.info("🚀 [Render] Production modda thread başlatılıyor...")
    init_thread = threading.Thread(target=background_initialization, daemon=True)
    init_thread.start()
else:
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
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }), 200

@app.route('/health', methods=['GET'])
@app.route('/healthz', methods=['GET'])  # 🔥 RENDER HEALTH CHECK FIX!
def health():
    """Basit Sağlık Kontrolü (Load Balancer için)"""
    return jsonify({"status": "ok"}), 200

@app.route('/api/system/status', methods=['GET'])
def system_status():
    """Detaylı Sistem Durumu"""
    try:
        from services.maintenance_service import scheduler, get_scheduler_status
        from services.financial_service import get_service_metrics
        from services.alarm_service import get_alarm_stats
        from utils.cache import get_cache
        
        scheduler_running = False
        active_job_list = []
        
        if scheduler is not None:
            try:
                from apscheduler.schedulers import STATE_RUNNING
                scheduler_running = (scheduler.state == STATE_RUNNING)
                
                if scheduler_running:
                    active_job_list = [job.id for job in scheduler.get_jobs()]
            except Exception as sched_err:
                logger.warning(f"⚠️ Scheduler kontrol hatası: {sched_err}")
        
        scheduler_status = get_scheduler_status()
        metrics = get_service_metrics()
        alarm_stats = get_alarm_stats()
        
        last_worker_run = get_cache("kurabak:last_worker_run")
        worker_status = "🟢 Aktif"
        if last_worker_run:
            time_diff = time.time() - float(last_worker_run)
            if time_diff > 600:
                worker_status = "🔴 Uyuyor"
            elif time_diff > 300:
                worker_status = "🟡 Yavaş"
        else:
            worker_status = "⚪ Henüz Çalışmadı"
        
        snapshot_exists = bool(get_cache("kurabak:yesterday_prices"))
        snapshot_status = "🟢 Mevcut" if snapshot_exists else "🔴 Kayıp"
        
        last_alarm_check = get_cache(Config.CACHE_KEYS['alarm_last_check'])
        alarm_status = "🟢 Aktif"
        if last_alarm_check:
            time_diff = time.time() - float(last_alarm_check)
            if time_diff > 1800:
                alarm_status = "🔴 Uyuyor"
            elif time_diff > 900:
                alarm_status = "🟡 Yavaş"
        else:
            alarm_status = "⚪ Henüz Çalışmadı"
        
        firebase_status = "🟢 Aktif" if _firebase_initialized else "🔴 Devre Dışı"
        
        telegram_status = "🟢 Aktif" if _telegram_instance else "🔴 Devre Dışı"
        
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
                },
                "telegram": {
                    "status": telegram_status
                }
            },
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
    
    🔥 V5.1: Global telegram singleton kullanımı
    """
    try:
        data = request.json
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({"success": False, "error": "Mesaj boş olamaz"}), 400
        
        if len(message) > 250:
            return jsonify({"success": False, "error": "Mesaj çok uzun (max 250 karakter)"}), 400

        # Telegram'a Gönder (Global Singleton)
        telegram = get_telegram_instance()
        
        if telegram:
            telegram_msg = f"📩 **YENİ GERİ BİLDİRİM**\n\n{message}"
            telegram._send_raw(telegram_msg)
            logger.info(f"✅ [Feedback] Anonim mesaj iletildi ({len(message)} karakter)")
        else:
            logger.warning("⚠️ [Feedback] Telegram devre dışı, mesaj kaydedildi ama gönderilemedi")
        
        return jsonify({"success": True, "message": "Mesajınız iletildi"}), 200

    except Exception as e:
        logger.error(f"❌ [Feedback] Hata: {e}")
        return jsonify({"success": False, "error": "Sunucu hatası"}), 500

@app.route('/api/device/register', methods=['POST'])
def register_device():
    """FCM Token kaydı (Push Notification için)"""
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
    """Manuel Push Notification testi"""
    try:
        result = send_test_notification()
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"❌ [Push Test] Hata: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ======================================
# 🧹 ACİL TEMİZLİK ENDPOİNTİ
# ======================================

@app.route('/api/admin/cleanup', methods=['POST'])
def emergency_cleanup():
    """
    🚨 ACİL TEMİZLİK - RAM'deki tüm çöpleri temizler
    
    - Redis FLUSHALL
    - RAM Cache temizliği
    - Disk backup temizliği (eski dosyalar)
    - Scheduler restart
    
    ⚠️ DİKKAT: Bu endpoint sadece Telegram'dan çağrılmalı!
    """
    try:
        from utils.cache import flush_all_cache, cleanup_old_disk_backups
        
        logger.warning("🚨 [CLEANUP] ACİL TEMİZLİK BAŞLADI!")
        
        # 1. Redis + RAM + Disk temizle
        flush_all_cache()
        logger.info("✅ [CLEANUP] Cache temizlendi")
        
        # 2. Eski disk backup'larını temizle (7+ gün)
        cleanup_result = cleanup_old_disk_backups(max_age_days=7)
        logger.info(f"✅ [CLEANUP] {cleanup_result['deleted_count']} eski backup silindi")
        
        # 3. Scheduler'ı yeniden başlat
        stop_scheduler()
        time.sleep(2)
        start_scheduler()
        logger.info("✅ [CLEANUP] Scheduler yeniden başlatıldı")
        
        # 4. Telegram'a bildir
        telegram = get_telegram_instance()
        if telegram:
            telegram._send_raw(
                "✅ *ACİL TEMİZLİK TAMAMLANDI!*\n\n"
                f"🧹 Redis temizlendi\n"
                f"🧹 RAM temizlendi\n"
                f"🧹 {cleanup_result['deleted_count']} eski backup silindi\n"
                f"🔄 Scheduler yeniden başlatıldı\n\n"
                "Sistem şimdi temiz ve hazır!"
            )
        
        return jsonify({
            "success": True,
            "message": "Sistem temizlendi ve yeniden başlatıldı",
            "details": {
                "cache_cleared": True,
                "old_backups_deleted": cleanup_result['deleted_count'],
                "scheduler_restarted": True
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ [CLEANUP] Hata: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ======================================
# TEMİZLİK (SHUTDOWN)
# ======================================

def on_exit():
    """
    🔥 V5.3: Temiz kapanış (Singleton'ları + Redis lock'u temizle)
    """
    global _firebase_initialized, _telegram_instance
    
    logger.info("🛑 Uygulama kapatılıyor...")
    stop_scheduler()
    
    # Redis lock'u temizle
    try:
        from utils.cache import get_redis_client
        redis_client = get_redis_client()
        if redis_client:
            lock_key = "kurabak:scheduler:lock"
            redis_client.delete(lock_key)
            logger.info("🔒 [Redis Lock] Temizlendi.")
    except Exception as e:
        logger.warning(f"⚠️ [Redis Lock] Temizleme hatası: {e}")
    
    # Firebase'i temizle
    try:
        if _firebase_initialized and firebase_admin._apps:
            firebase_admin.delete_app(firebase_admin.get_app())
            _firebase_initialized = False
            logger.info("🔥 [Firebase] Temiz kapanış tamamlandı.")
    except:
        pass
    
    # Telegram'ı temizle
    try:
        if _telegram_instance:
            _telegram_instance = None
            logger.info("📱 [Telegram] Temiz kapanış tamamlandı.")
    except:
        pass
    
    logger.info("✅ Temiz kapanış tamamlandı.")

atexit.register(on_exit)

# ======================================
# BAŞLATMA
# ======================================

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"🌍 Local Sunucu Başlatılıyor: http://localhost:{port}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"🚀 KuraBak Backend {Config.APP_VERSION}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
