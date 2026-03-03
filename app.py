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
from utils.notification_service import register_fcm_token, send_test_notification, is_token_registered

from utils.cache import renew_scheduler_lock, SCHEDULER_LOCK_KEY, SCHEDULER_LOCK_TTL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("KuraBak")

import firebase_admin
from firebase_admin import credentials

_firebase_initialized = False
_firebase_lock = threading.Lock()

def init_firebase():
    global _firebase_initialized
    
    if _firebase_initialized:
        logger.info("🔥 [Firebase] Zaten başlatılmış (global flag)")
        return True
    
    with _firebase_lock:
        if _firebase_initialized:
            return True
        
        try:
            if firebase_admin._apps:
                logger.info("🔥 [Firebase] firebase_admin._apps dolu, başlatılmış kabul ediliyor")
                _firebase_initialized = True
                return True
            
            if os.environ.get("RENDER"):
                cred_path = "/etc/secrets/firebase_credentials.json"
            else:
                cred_path = Config.FIREBASE_CREDENTIALS_PATH or "firebase_credentials.json"
            
            logger.info(f"🔍 [Firebase] Credentials yolu: {cred_path}")
            
            if not os.path.exists(cred_path):
                logger.error(f"❌ [Firebase] Credentials dosyası bulunamadı: {cred_path}")
                
                alternative_paths = [
                    "firebase_credentials.json",
                    "./firebase_credentials.json",
                    "/etc/secrets/firebase_credentials.json",
                    os.path.join(os.getcwd(), "firebase_credentials.json")
                ]
                
                logger.info("🔍 [Firebase] Alternatif yollar deneniyor...")
                for alt_path in alternative_paths:
                    logger.info(f"   Kontrol: {alt_path}")
                    if os.path.exists(alt_path):
                        cred_path = alt_path
                        logger.info(f"   ✅ Bulundu: {alt_path}")
                        break
                else:
                    logger.warning("⚠️ [Firebase] Hiçbir yolda dosya bulunamadı!")
                    logger.warning("   Push notification özellikleri devre dışı!")
                    return False
            
            logger.info(f"✅ [Firebase] Credentials dosyası bulundu: {cred_path}")
            
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {'projectId': 'kurabak-f1950'})

            import requests as _requests
            import google.auth.transport.requests as _google_transport
            _session = _requests.Session()
            _adapter = _requests.adapters.HTTPAdapter(
                pool_connections=10,
                pool_maxsize=100,
                max_retries=3
            )
            _session.mount('https://', _adapter)
            _google_transport.Request(session=_session)
            logger.info("✅ [Firebase] HTTP connection pool genişletildi (maxsize=100)")

            _firebase_initialized = True
            logger.info("✅ [Firebase] Admin SDK başarıyla başlatıldı! (Singleton)")
            logger.info(f"   📁 Credentials: {cred_path}")
            logger.info(f"   🎯 Project ID: kurabak-f1950")
            return True
            
        except ValueError as ve:
            if "already exists" in str(ve).lower():
                logger.info("🔥 [Firebase] Zaten başlatılmış (ValueError yakalandı)")
                _firebase_initialized = True
                return True
            else:
                logger.error(f"❌ [Firebase] Başlatma hatası: {ve}")
                return False
        except Exception as e:
            logger.error(f"❌ [Firebase] Başlatma hatası: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")
            logger.warning("   Push notification özellikleri devre dışı!")
            return False

app = Flask(__name__)
app.config.from_object(Config)

CORS(app, resources={r"/api/*": {"origins": "*"}})

app.register_blueprint(api_bp)
app.register_blueprint(alarm_bp)

_telegram_instance = None
_telegram_lock = threading.Lock()

def get_telegram_instance():
    global _telegram_instance
    
    if _telegram_instance is not None:
        return _telegram_instance
    
    with _telegram_lock:
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

def post_fork(server, worker):
    global _firebase_initialized
    
    logger.info(f"🔥 [Worker {worker.pid}] Post-fork hook tetiklendi")
    
    _firebase_initialized = False
    
    try:
        firebase_status = init_firebase()
        if firebase_status:
            logger.info(f"✅ [Worker {worker.pid}] Firebase başarıyla başlatıldı!")
        else:
            logger.warning(f"⚠️ [Worker {worker.pid}] Firebase başlatılamadı (devre dışı)")
    except Exception as e:
        logger.error(f"❌ [Worker {worker.pid}] Firebase başlatma hatası: {e}")


def _watch_scheduler_health(current_pid: int):
    logger.info(f"👁️ [Watch] PID {current_pid} izleme modunda başladı")

    while True:
        try:
            time.sleep(30)

            from utils.cache import get_redis_client
            redis_client = get_redis_client()

            if not redis_client:
                continue

            existing = redis_client.get(SCHEDULER_LOCK_KEY)

            if existing:
                continue

            acquired = redis_client.set(
                SCHEDULER_LOCK_KEY, current_pid,
                ex=SCHEDULER_LOCK_TTL,
                nx=True
            )

            if acquired:
                logger.warning(
                    f"🚨 [Watch] Lock kayboldu! PID {current_pid} scheduler'ı devralıyor..."
                )
                telegram = get_telegram_instance()
                if telegram:
                    try:
                        telegram._send_raw(
                            f"⚠️ *SCHEDULER DEVİR TESLİM*\n\n"
                            f"Lock sahibi çöktü.\n"
                            f"PID {current_pid} scheduler'ı devraldı."
                        )
                    except Exception:
                        pass

                start_scheduler()
                renew_scheduler_lock()
                logger.info(f"✅ [Watch] Scheduler devralındı! PID {current_pid} aktif.")
                return

        except Exception as e:
            logger.error(f"❌ [Watch] İzleme hatası: {e}")
            time.sleep(30)


def background_initialization():
    from utils.cache import get_redis_client

    current_pid = os.getpid()

    logger.info(f"🔥 [Firebase] Lock kontrolünden önce başlatılıyor (PID: {current_pid})...")
    firebase_status = init_firebase()
    if firebase_status:
        logger.info("🔥 [Firebase] Push notification sistemi aktif!")
    else:
        logger.warning("⚠️ [Firebase] Push notification sistemi devre dışı!")

    try:
        redis_client = get_redis_client()

        if not redis_client:
            logger.warning("⚠️ [Redis Lock] Redis bağlantısı yok, fallback mode — scheduler başlatılıyor")
        else:
            acquired = redis_client.set(
                SCHEDULER_LOCK_KEY, current_pid,
                ex=SCHEDULER_LOCK_TTL,
                nx=True
            )

            if not acquired:
                existing_pid = redis_client.get(SCHEDULER_LOCK_KEY)
                logger.info(
                    f"⏭️ [Redis Lock] Lock PID {existing_pid} tarafından alındı. "
                    f"PID {current_pid} izleme moduna geçiyor..."
                )
                watch_thread = threading.Thread(
                    target=_watch_scheduler_health,
                    args=(current_pid,),
                    daemon=True,
                    name=f"SchedulerWatch-{current_pid}"
                )
                watch_thread.start()
                return

            logger.info(f"🔒 [Redis Lock] Lock alındı: PID {current_pid} ({SCHEDULER_LOCK_TTL}s TTL)")

    except Exception as e:
        logger.warning(f"⚠️ [Redis Lock] Redis erişim hatası: {e}")
        logger.warning("   Redis olmadan devam ediliyor (fallback mode)")

    logger.info(f"⏳ [Arka Plan] Sistem servisleri başlatılıyor (PID: {current_pid})...")
    time.sleep(1)

    telegram = get_telegram_instance()
    if telegram:
        logger.info("📱 [Telegram] Komut sistemi aktif!")
    else:
        logger.warning("⚠️ [Telegram] Komut sistemi devre dışı!")

    start_scheduler()

    renew_scheduler_lock()
    logger.info(f"🔒 [Redis Lock] Scheduler başladı, ilk yenileme yapıldı (PID: {current_pid})")

    logger.info("👮 [İlk Kontrol] Şef sistemi kontrol ediyor...")

    try:
        supervisor_check()
        logger.info("✅ [İlk Kontrol] Şef kontrolü tamamlandı!")
    except Exception as e:
        logger.error(f"⚠️ [İlk Kontrol] Şef hatası: {e}")

    logger.info("✅ [Arka Plan] Tüm sistemler devrede!")

    if telegram:
        try:
            telegram.send_startup_message()
        except Exception:
            pass

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

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "app":         Config.APP_NAME,
        "version":     Config.APP_VERSION,
        "status":      "active",
        "environment": Config.ENVIRONMENT,
        "timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }), 200

@app.route('/health', methods=['GET'])
@app.route('/healthz', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

@app.route('/api/system/status', methods=['GET'])
def system_status():
    try:
        from services.maintenance_service import scheduler, get_scheduler_status
        from services.financial_service import get_service_metrics
        from services.alarm_service import get_alarm_stats
        from utils.cache import get_cache
        
        scheduler_running = False
        active_job_list   = []
        
        if scheduler is not None:
            try:
                from apscheduler.schedulers import STATE_RUNNING
                scheduler_running = (scheduler.state == STATE_RUNNING)
                
                if scheduler_running:
                    active_job_list = [job.id for job in scheduler.get_jobs()]
            except Exception as sched_err:
                logger.warning(f"⚠️ Scheduler kontrol hatası: {sched_err}")
        
        scheduler_status = get_scheduler_status()
        metrics          = get_service_metrics()
        alarm_stats      = get_alarm_stats()
        
        last_worker_run = get_cache("kurabak:last_worker_run")
        worker_status   = "🟢 Aktif"
        if last_worker_run:
            time_diff = time.time() - float(last_worker_run)
            if time_diff > 600:
                worker_status = "🔴 Uyuyor"
            elif time_diff > 300:
                worker_status = "🟡 Yavaş"
        else:
            worker_status = "⚪ Henüz Çalışmadı"
        
        snapshot_exists = bool(get_cache(Config.CACHE_KEYS['raw_snapshot']))
        snapshot_status = "🟢 Mevcut" if snapshot_exists else "🔴 Kayıp"
        
        last_alarm_check = get_cache(Config.CACHE_KEYS['alarm_last_check'])
        alarm_status     = "🟢 Aktif"
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
            "success":   True,
            "timestamp": datetime.now().isoformat(),
            "scheduler": {
                "running":     scheduler_running,
                "active_jobs": active_job_list
            },
            "components": {
                "worker":     {"status": worker_status, "last_run": last_worker_run},
                "snapshot":   {"status": snapshot_status},
                "controller": {"status": "🟢 Aktif" if scheduler_running else "🔴 Durdu"},
                "alarm": {
                    "status":       alarm_status,
                    "last_check":   last_alarm_check,
                    "total_alarms": alarm_stats.get('total_alarms', 0),
                    "unique_users": alarm_stats.get('unique_users', 0),
                    "alarm_types":  alarm_stats.get('alarm_types', {})
                },
                "firebase": {"status": firebase_status},
                "telegram": {"status": telegram_status}
            },
            "metrics": metrics
        }), 200
        
    except Exception as e:
        logger.error(f"System status error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/device/register', methods=['POST'])
def register_device():
    try:
        data  = request.json
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

@app.route('/api/device/check-token', methods=['POST'])
def check_token():
    try:
        data  = request.json
        token = data.get('token') if data else None

        if not token:
            return jsonify({"success": False, "error": "Token eksik"}), 400

        registered = is_token_registered(token)
        return jsonify({"success": True, "registered": registered}), 200

    except Exception as e:
        logger.error(f"❌ [FCM] Token kontrol hatası: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/device/test-push', methods=['GET'])
def trigger_test_push():
    try:
        result = send_test_notification()
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"❌ [Push Test] Hata: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/trigger-push', methods=['POST'])
def trigger_daily_push():
    try:
        admin_token    = request.headers.get('X-Admin-Token') or (request.json.get('admin_token') if request.json else None)
        expected_token = os.environ.get('ADMIN_SECRET_TOKEN')

        if not expected_token:
            logger.warning("⚠️ [TRIGGER PUSH] ADMIN_SECRET_TOKEN env değişkeni tanımlı değil!")
            return jsonify({"success": False, "error": "Sunucu yapılandırma hatası"}), 500

        if not admin_token or admin_token != expected_token:
            logger.warning(f"🚨 [TRIGGER PUSH] Yetkisiz erişim denemesi! IP: {request.remote_addr}")
            return jsonify({"success": False, "error": "Yetkisiz erişim"}), 403

        from utils.notification_service import send_daily_summary
        result = send_daily_summary()
        logger.info(f"✅ [TRIGGER PUSH] Manuel push gönderildi: {result}")
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"❌ [TRIGGER PUSH] Hata: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/cleanup', methods=['POST'])
def emergency_cleanup():
    try:
        admin_token    = request.headers.get('X-Admin-Token') or request.json.get('admin_token') if request.json else None
        expected_token = os.environ.get('ADMIN_SECRET_TOKEN')

        if not expected_token:
            logger.warning("⚠️ [CLEANUP] ADMIN_SECRET_TOKEN env değişkeni tanımlı değil!")
            return jsonify({"success": False, "error": "Sunucu yapılandırma hatası"}), 500

        if not admin_token or admin_token != expected_token:
            logger.warning(f"🚨 [CLEANUP] Yetkisiz erişim denemesi! IP: {request.remote_addr}")
            return jsonify({"success": False, "error": "Yetkisiz erişim"}), 403

        from utils.cache import get_redis_client, cleanup_old_disk_backups
        
        logger.warning("🚨 [CLEANUP] ACİL TEMİZLİK BAŞLADI!")
        
        deleted_count = 0
        redis_client  = get_redis_client()
        
        if redis_client:
            keys = redis_client.keys("kurabak:*")
            if keys:
                for key in keys:
                    redis_client.delete(key)
                    deleted_count += 1
            logger.info(f"✅ [CLEANUP] {deleted_count} kurabak:* key silindi (FCM ve alarm keyleri korundu)")
        else:
            logger.warning("⚠️ [CLEANUP] Redis bağlantısı yok, cache temizlenemedi")
        
        cleanup_result = cleanup_old_disk_backups(max_age_days=7)
        logger.info(f"✅ [CLEANUP] {cleanup_result['deleted_count']} eski backup silindi")
        
        stop_scheduler()
        time.sleep(2)
        start_scheduler()
        renew_scheduler_lock()
        logger.info("✅ [CLEANUP] Scheduler yeniden başlatıldı")
        
        telegram = get_telegram_instance()
        if telegram:
            telegram._send_raw(
                "✅ *ACİL TEMİZLİK TAMAMLANDI!*\n\n"
                f"🧹 {deleted_count} Redis key silindi\n"
                f"🔒 FCM tokenlar ve alarmlar korundu\n"
                f"🧹 {cleanup_result['deleted_count']} eski backup silindi\n"
                f"🔄 Scheduler yeniden başlatıldı\n\n"
                "Sistem şimdi temiz ve hazır!"
            )
        
        return jsonify({
            "success": True,
            "message": "Sistem temizlendi ve yeniden başlatıldı",
            "details": {
                "cache_keys_deleted":  deleted_count,
                "old_backups_deleted": cleanup_result['deleted_count'],
                "scheduler_restarted": True,
                "protected":           ["fcm_tokens", "alarm:*"]
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ [CLEANUP] Hata: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

def on_exit():
    global _firebase_initialized, _telegram_instance
    
    logger.info("🛑 Uygulama kapatılıyor...")
    stop_scheduler()
    
    try:
        from utils.cache import get_redis_client
        redis_client = get_redis_client()
        if redis_client:
            redis_client.delete(SCHEDULER_LOCK_KEY)
            logger.info("🔒 [Redis Lock] Temizlendi.")
    except Exception as e:
        logger.warning(f"⚠️ [Redis Lock] Temizleme hatası: {e}")
    
    try:
        if _firebase_initialized and firebase_admin._apps:
            firebase_admin.delete_app(firebase_admin.get_app())
            _firebase_initialized = False
            logger.info("🔥 [Firebase] Temiz kapanış tamamlandı.")
    except Exception:
        pass
    
    try:
        if _telegram_instance:
            _telegram_instance = None
            logger.info("📱 [Telegram] Temiz kapanış tamamlandı.")
    except Exception:
        pass
    
    logger.info("✅ Temiz kapanış tamamlandı.")

atexit.register(on_exit)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"🌍 Local Sunucu Başlatılıyor: http://localhost:{port}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"🚀 KuraBak Backend {Config.APP_VERSION}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
