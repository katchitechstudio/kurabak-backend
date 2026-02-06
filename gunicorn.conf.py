"""
Gunicorn Configuration - V5.3 🔥
==================================
✅ Post-fork hook: Her worker'da Firebase başlatır
✅ Worker settings: 1 worker, 4 thread
✅ Timeout: 120 saniye
"""
import os
import logging

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gunicorn.config")

# ======================================
# WORKER SETTINGS
# ======================================
workers = 1
threads = 4
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
timeout = 120
loglevel = "info"

# Worker class
worker_class = "gthread"

# Graceful timeout
graceful_timeout = 30

# Keep alive
keepalive = 5

# ======================================
# 🔥 POST-FORK HOOK
# ======================================

def post_fork(server, worker):
    """
    🔥 V5.3 FIX: Her worker başladığında Firebase'i başlat
    
    Gunicorn multi-process modunda her worker process'inin 
    kendi Firebase instance'ına ihtiyacı var.
    
    Bu hook sayesinde:
    - Master process Firebase'i başlatır
    - Her worker kendi Firebase instance'ını alır
    - "The default Firebase app does not exist" hatası ortadan kalkar
    """
    logger.info(f"🔥 [Gunicorn Config] Post-fork hook tetiklendi - Worker PID: {worker.pid}")
    
    try:
        # app.py'deki post_fork fonksiyonunu import et ve çağır
        from app import post_fork as app_post_fork
        app_post_fork(server, worker)
        logger.info(f"✅ [Gunicorn Config] Worker {worker.pid} post-fork işlemi tamamlandı")
    except ImportError as e:
        logger.error(f"❌ [Gunicorn Config] app.post_fork import hatası: {e}")
        logger.warning("⚠️ [Gunicorn Config] Firebase worker'da başlatılamayabilir!")
    except Exception as e:
        logger.error(f"❌ [Gunicorn Config] Post-fork hatası: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")

# ======================================
# WORKER LIFECYCLE HOOKS (OPTIONAL)
# ======================================

def on_starting(server):
    """Server başlatılırken"""
    logger.info("🚀 [Gunicorn] Server başlatılıyor...")

def when_ready(server):
    """Server hazır olduğunda"""
    logger.info("✅ [Gunicorn] Server hazır ve dinlemeye başladı")

def pre_fork(server, worker):
    """Worker fork edilmeden önce"""
    logger.info(f"⏳ [Gunicorn] Worker {worker.pid} fork ediliyor...")

def worker_int(worker):
    """Worker SIGINT aldığında"""
    logger.info(f"⚠️ [Gunicorn] Worker {worker.pid} SIGINT aldı")

def worker_abort(worker):
    """Worker abort olduğunda"""
    logger.error(f"❌ [Gunicorn] Worker {worker.pid} abort oldu!")
