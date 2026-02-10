"""
Maintenance Service - PRODUCTION READY V5.5 🚧
===============================================
✅ SCHEDULER OPTIMIZATION: CPU spike önleme (prepare/publish ayrımı)
✅ SMOOTH MARGIN TRANSITION: Kademeli marj geçişi
✅ TAM MARJ SİSTEMİ: Kuyumcu gerçeği yansıtır
✅ İKİ SNAPSHOT: raw_snapshot + jeweler_snapshot
✅ JEWELER REBUILD: Marj değişince cache otomatik yenilenir
✅ SNAPSHOT UPDATE: Marj değişince snapshot düzeltilir

V5.5 Değişiklikler (SCHEDULER OPTIMIZATION):
- 🔥 23:55 → prepare_morning_news() [Gemini call]
- 🔥 00:00 → save_daily_snapshot() + publish_morning_news() [lightweight]
- 🔥 00:05 → update_dynamic_margins() + rebuild_jeweler_cache() + update_jeweler_snapshot()
- 🔥 11:55 → prepare_evening_news() [Gemini call]
- 🔥 12:00 → publish_evening_news() [lightweight]
- 🔥 14:00 → push_notification [daily summary]

Timeline:
23:55 → Sabah haberlerini HAZIRLA (Gemini - ağır işlem)
00:00 → Snapshot AL + Sabah YAYINLA (hafif)
00:05 → Marj GÜNCELLE + Jeweler Rebuild + Snapshot Update
11:55 → Akşam haberlerini HAZIRLA (Gemini - ağır işlem)
12:00 → Akşam YAYINLA (hafif)
14:00 → Push notification GÖNDER
"""

import logging
import time
import threading
from typing import Optional, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR

from utils.cache import get_cache, set_cache, delete_cache
from config import Config

logger = logging.getLogger(__name__)

scheduler = None
_scheduler_lock = threading.Lock()


def check_maintenance_status() -> Dict[str, Any]:
    maintenance_data = get_cache(Config.CACHE_KEYS['maintenance'])
    
    if not maintenance_data:
        return {
            'is_active': False,
            'banner_message': None
        }
    
    return {
        'is_active': True,
        'banner_message': maintenance_data.get('message', Config.MAINTENANCE_DEFAULT_MESSAGE)
    }


def activate_maintenance(message: Optional[str] = None) -> bool:
    try:
        banner_msg = message or Config.MAINTENANCE_DEFAULT_MESSAGE
        
        maintenance_data = {
            'message': banner_msg,
            'activated_at': time.time()
        }
        
        set_cache(Config.CACHE_KEYS['maintenance'], maintenance_data, ttl=0)
        
        logger.info(f"🚧 Bakım modu aktif edildi: {banner_msg}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Bakım modu aktif etme hatası: {e}")
        return False


def deactivate_maintenance() -> bool:
    try:
        delete_cache(Config.CACHE_KEYS['maintenance'])
        logger.info("✅ Bakım modu kapatıldı")
        return True
        
    except Exception as e:
        logger.error(f"❌ Bakım modu kapatma hatası: {e}")
        return False


def set_banner(message: str, ttl: int = 0) -> bool:
    try:
        set_cache(Config.CACHE_KEYS['banner'], message, ttl=ttl)
        logger.info(f"📢 Banner ayarlandı: {message} (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.error(f"❌ Banner ayarlama hatası: {e}")
        return False


def clear_banner() -> bool:
    try:
        delete_cache(Config.CACHE_KEYS['banner'])
        logger.info("🔇 Banner kaldırıldı")
        return True
    except Exception as e:
        logger.error(f"❌ Banner kaldırma hatası: {e}")
        return False


def get_current_banner() -> Optional[str]:
    maintenance = check_maintenance_status()
    if maintenance['is_active']:
        return maintenance['banner_message']
    
    banner = get_cache(Config.CACHE_KEYS['banner'])
    if banner:
        return banner
    
    return None


def fetch_all_data_safe() -> bool:
    try:
        active_source = get_cache(Config.CACHE_KEYS['active_source']) or "v5"
        logger.info(f"🔄 Acil veri çekimi başlatılıyor ({active_source.upper()})...")
        
        from services.financial_service import update_financial_data
        
        success = update_financial_data()
        
        if success:
            logger.info("✅ Acil veri çekimi başarılı")
        else:
            logger.error("❌ Acil veri çekimi başarısız")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Acil veri çekimi hatası: {e}")
        return False


def force_worker_update():
    try:
        logger.info("⚡ Worker manuel olarak tetiklendi...")
        fetch_all_data_safe()
    except Exception as e:
        logger.error(f"❌ Manuel worker tetikleme hatası: {e}")


def job_error_listener(event):
    if event.exception:
        job_id = event.job_id
        exception = event.exception
        
        logger.critical(f"💣 SCHEDULER JOB HATASI!")
        logger.critical(f"   Job ID: {job_id}")
        logger.critical(f"   Hata: {exception}")
        logger.critical(f"   Hata Tipi: {type(exception).__name__}")
        
        try:
            from utils.telegram_monitor import get_telegram_monitor
            
            telegram = get_telegram_monitor()
            if telegram:
                error_message = (
                    f"🚨 *KRİTİK: SCHEDULER JOB ÇÖKTÜ!*\n\n"
                    f"*Job ID:* `{job_id}`\n"
                    f"*Hata Tipi:* `{type(exception).__name__}`\n"
                    f"*Hata Mesajı:*\n```\n{str(exception)[:500]}\n```\n\n"
                    f"⚠️ Sistem otomatik olarak job'ı yeniden başlatacak."
                )
                
                telegram.send_message(error_message, level='critical')
                logger.info("✅ Hata bildirimi Telegram'a gönderildi")
        
        except Exception as telegram_err:
            logger.error(f"❌ Telegram bildirim hatası: {telegram_err}")


# ======================================
# CORE JOBS
# ======================================

def worker_job():
    """👷 Worker - Her dakika veri güncelle"""
    try:
        logger.info("👷 [WORKER] Veri güncelleme başlıyor...")
        
        from services.financial_service import update_financial_data
        success = update_financial_data()
        
        if success:
            set_cache(Config.CACHE_KEYS['last_worker_run'], str(time.time()), ttl=0)
            logger.info("✅ [WORKER] Veri başarıyla güncellendi")
        else:
            logger.warning("⚠️ [WORKER] Veri güncellenemedi")
            
    except Exception as e:
        logger.error(f"❌ [WORKER] Hata: {e}")
        raise


def supervisor_check():
    """👮 Şef - Sistem kontrolü"""
    try:
        logger.info("👮 [ŞEF] Sistem kontrolü başlıyor...")
        
        # raw_snapshot kontrolü
        snapshot_exists = bool(get_cache(Config.CACHE_KEYS['raw_snapshot']))
        if not snapshot_exists:
            logger.warning("⚠️ [ŞEF] Snapshot kayıp! Acil snapshot alınıyor...")
            from services.financial_service import save_daily_snapshot
            save_daily_snapshot()
        
        # Worker kontrol
        last_worker_run = get_cache(Config.CACHE_KEYS['last_worker_run'])
        if last_worker_run:
            time_diff = time.time() - float(last_worker_run)
            if time_diff > Config.SUPERVISOR_WORKER_TIMEOUT:
                logger.warning(f"⚠️ [ŞEF] Worker {int(time_diff/60)} dakikadır uyuyor! Uyandırılıyor...")
                worker_job()
        
        logger.info("✅ [ŞEF] Kontrol tamamlandı")
        
    except Exception as e:
        logger.error(f"❌ [ŞEF] Hata: {e}")
        raise


def daily_report():
    """📊 Günlük rapor - Telegram"""
    try:
        logger.info("📊 [RAPOR] Günlük rapor hazırlanıyor...")
        
        from utils.telegram_monitor import get_telegram_monitor
        from services.financial_service import get_service_metrics
        
        telegram = get_telegram_monitor()
        if telegram:
            metrics = get_service_metrics()
            telegram.send_daily_report(metrics)
        
        logger.info("✅ [RAPOR] Rapor gönderildi")
        
    except Exception as e:
        logger.error(f"❌ [RAPOR] Hata: {e}")
        raise


def cleanup_old_backups():
    """🧹 Cleanup - Eski backup temizliği"""
    try:
        logger.info("🧹 [CLEANUP] Eski backup temizliği başlıyor...")
        
        from utils.cache import cleanup_old_disk_backups, get_disk_backup_stats
        
        before_stats = get_disk_backup_stats()
        result = cleanup_old_disk_backups(max_age_days=Config.CLEANUP_BACKUP_AGE_DAYS)
        deleted_count = result.get('deleted_count', 0)
        after_stats = result.get('after_stats', {})
        
        if deleted_count > 0:
            logger.info(f"✅ [CLEANUP] {deleted_count} adet eski backup silindi")
            logger.info(f"   📊 Önce: {before_stats.get('total_files', 0)} dosya, {before_stats.get('total_size_mb', 0)} MB")
            logger.info(f"   📊 Sonra: {after_stats.get('total_files', 0)} dosya, {after_stats.get('total_size_mb', 0)} MB")
        else:
            logger.info("✅ [CLEANUP] Silinecek eski backup bulunamadı")
        
        set_cache(Config.CACHE_KEYS['cleanup_last_run'], str(time.time()), ttl=0)
        
    except Exception as e:
        logger.error(f"❌ [CLEANUP] Hata: {e}")
        raise


def alarm_check_job():
    """🔔 Alarm kontrol - Periyodik"""
    try:
        logger.info("🔔 [ALARM] Periyodik alarm kontrolü başlıyor...")
        
        from services.alarm_service import check_all_alarms
        
        result = check_all_alarms()
        
        total = result.get('total_alarms', 0)
        checked = result.get('checked', 0)
        triggered = result.get('triggered', 0)
        failed = result.get('failed', 0)
        duration_ms = result.get('duration_ms', 0)
        
        if total == 0:
            logger.info("ℹ️ [ALARM] Kontrol edilecek alarm yok")
        else:
            logger.info(
                f"✅ [ALARM] Kontrol tamamlandı: "
                f"{checked}/{total} kontrol edildi, "
                f"{triggered} tetiklendi, "
                f"{failed} hata ({duration_ms:.2f}ms)"
            )
        
        set_cache(Config.CACHE_KEYS['alarm_last_check'], str(time.time()), ttl=0)
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Kontrol hatası: {e}")
        raise


# ======================================
# 🔥 V5.5 NEW JOBS
# ======================================

def prepare_morning_news_job():
    """🌅 23:55 - Sabah haberlerini HAZIRLA (Gemini call)"""
    try:
        logger.info("🌅 [SABAH HAZIRLIK] Sabah haberlerini hazırlama başlıyor (Gemini)...")
        
        from utils.news_manager import prepare_morning_news
        success = prepare_morning_news()
        
        if success:
            logger.info("✅ [SABAH HAZIRLIK] Sabah haberleri başarıyla hazırlandı!")
        else:
            logger.warning("⚠️ [SABAH HAZIRLIK] Hazırlama başarısız, yedek haber kullanılacak")
            
    except Exception as e:
        logger.error(f"❌ [SABAH HAZIRLIK] Hata: {e}")
        raise


def snapshot_and_publish_morning_job():
    """📸 00:00 - Snapshot AL + Sabah haberlerini YAYINLA"""
    try:
        logger.info("📸 [SABAH YAYINI] Snapshot + sabah yayını başlıyor...")
        
        # 1. Snapshot al (raw + jeweler)
        from services.financial_service import save_daily_snapshot
        snapshot_success = save_daily_snapshot()
        
        if snapshot_success:
            logger.info("✅ [SABAH YAYINI] Snapshot başarıyla alındı")
        else:
            logger.warning("⚠️ [SABAH YAYINI] Snapshot alınamadı")
        
        # 2. Sabah haberlerini yayınla (hafif işlem)
        from utils.news_manager import publish_morning_news
        publish_success = publish_morning_news()
        
        if publish_success:
            logger.info("✅ [SABAH YAYINI] Sabah haberleri yayınlandı")
        else:
            logger.warning("⚠️ [SABAH YAYINI] Yayınlama başarısız")
        
        logger.info("✅ [SABAH YAYINI] İşlem tamamlandı")
        
    except Exception as e:
        logger.error(f"❌ [SABAH YAYINI] Hata: {e}")
        raise


def update_margins_and_rebuild_job():
    """💰 00:05 - Marj GÜNCELLE + Jeweler Rebuild + Snapshot Update"""
    try:
        logger.info("💰 [MARJ + REBUILD] Marj güncelleme ve rebuild başlıyor...")
        
        # 1. Dinamik marjları güncelle (Gemini + Smooth)
        from utils.news_manager import update_dynamic_margins
        margin_success = update_dynamic_margins()
        
        if margin_success:
            logger.info("✅ [MARJ + REBUILD] Dinamik marjlar güncellendi")
            
            # 2. Jeweler cache'i yeniden oluştur
            from services.financial_service import rebuild_jeweler_cache
            rebuild_success = rebuild_jeweler_cache()
            
            if rebuild_success:
                logger.info("✅ [MARJ + REBUILD] Jeweler cache rebuild tamamlandı")
            else:
                logger.warning("⚠️ [MARJ + REBUILD] Jeweler cache rebuild başarısız")
            
            # 3. Jeweler snapshot'ı güncelle
            from services.financial_service import update_jeweler_snapshot
            update_success = update_jeweler_snapshot()
            
            if update_success:
                logger.info("✅ [MARJ + REBUILD] Jeweler snapshot güncellendi")
            else:
                logger.warning("⚠️ [MARJ + REBUILD] Jeweler snapshot güncellenemedi")
        else:
            logger.warning("⚠️ [MARJ + REBUILD] Marj güncellenemedi, fallback kullanılacak")
        
        logger.info("✅ [MARJ + REBUILD] İşlem tamamlandı")
        
    except Exception as e:
        logger.error(f"❌ [MARJ + REBUILD] Hata: {e}")
        raise


def prepare_evening_news_job():
    """🌆 11:55 - Akşam haberlerini HAZIRLA (Gemini call)"""
    try:
        logger.info("🌆 [AKŞAM HAZIRLIK] Akşam haberlerini hazırlama başlıyor (Gemini)...")
        
        from utils.news_manager import prepare_evening_news
        success = prepare_evening_news()
        
        if success:
            logger.info("✅ [AKŞAM HAZIRLIK] Akşam haberleri başarıyla hazırlandı!")
        else:
            logger.warning("⚠️ [AKŞAM HAZIRLIK] Hazırlama başarısız, yedek haber kullanılacak")
            
    except Exception as e:
        logger.error(f"❌ [AKŞAM HAZIRLIK] Hata: {e}")
        raise


def publish_evening_news_job():
    """🌇 12:00 - Akşam haberlerini YAYINLA"""
    try:
        logger.info("🌇 [AKŞAM YAYINI] Akşam haberlerini yayınlama başlıyor...")
        
        from utils.news_manager import publish_evening_news
        success = publish_evening_news()
        
        if success:
            logger.info("✅ [AKŞAM YAYINI] Akşam haberleri yayınlandı")
        else:
            logger.warning("⚠️ [AKŞAM YAYINI] Yayınlama başarısız")
        
    except Exception as e:
        logger.error(f"❌ [AKŞAM YAYINI] Hata: {e}")
        raise


def push_notification_daily():
    """🔔 14:00 - Günlük push notification (Bayram/Haber)"""
    try:
        logger.info("🔔 [PUSH] Günlük push notification hazırlanıyor...")
        
        from utils.notification_service import send_daily_summary
        
        result = send_daily_summary()
        
        if result.get('success'):
            logger.info(f"✅ [PUSH] {result.get('type', 'bildirim').upper()} gönderildi ({result.get('recipient_count', 0)} kullanıcı)")
        else:
            logger.warning(f"⚠️ [PUSH] Gönderim başarısız: {result.get('error')}")
        
    except Exception as e:
        logger.error(f"❌ [PUSH] Hata: {e}")
        raise


# ======================================
# SCHEDULER START
# ======================================

def start_scheduler():
    """🚀 Scheduler başlat - V5.5"""
    global scheduler
    
    with _scheduler_lock:
        if scheduler and scheduler.running:
            logger.warning("⚠️ Scheduler zaten çalışıyor!")
            return
        
        scheduler = BackgroundScheduler(timezone=Config.DEFAULT_TIMEZONE)
        
        scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR)
        logger.info("✅ Job Error Listener eklendi")
        
        worker_interval = getattr(Config, 'UPDATE_INTERVAL', 60)
        alarm_interval_minutes = getattr(Config, 'ALARM_CHECK_INTERVAL', 10)
        
        # ======================================
        # CORE JOBS
        # ======================================
        
        # Worker - Her dakika
        scheduler.add_job(
            worker_job,
            trigger=IntervalTrigger(seconds=worker_interval),
            id='worker',
            name='Worker (Veri Güncelleyici)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # Şef - Her 10 dakika
        scheduler.add_job(
            supervisor_check,
            trigger=IntervalTrigger(minutes=Config.SUPERVISOR_INTERVAL),
            id='supervisor',
            name='Şef (Sistem Kontrolü)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # Günlük Rapor - 09:00
        scheduler.add_job(
            daily_report,
            trigger=CronTrigger(hour=Config.TELEGRAM_DAILY_REPORT_HOUR),
            id='daily_report',
            name='Günlük Rapor',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # Cleanup - 03:00
        scheduler.add_job(
            cleanup_old_backups,
            trigger=CronTrigger(hour=3, minute=0),
            id='cleanup',
            name='Cleanup (Eski Backup Temizliği)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # Alarm Check - Her 10-15 dakika
        scheduler.add_job(
            alarm_check_job,
            trigger=IntervalTrigger(minutes=alarm_interval_minutes),
            id='alarm_check',
            name='Alarm Check (Fiyat Alarmları)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # ======================================
        # 🔥 V5.5 OPTIMIZED JOBS
        # ======================================
        
        # 23:55 - Sabah haberlerini HAZIRLA
        scheduler.add_job(
            prepare_morning_news_job,
            trigger=CronTrigger(hour=23, minute=55),
            id='prepare_morning_news',
            name='Sabah Haberlerini Hazırla (Gemini)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 00:00 - Snapshot AL + Sabah YAYINLA
        scheduler.add_job(
            snapshot_and_publish_morning_job,
            trigger=CronTrigger(hour=0, minute=0, second=0),
            id='snapshot_and_publish_morning',
            name='Snapshot + Sabah Yayın',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 00:05 - Marj GÜNCELLE + Rebuild + Update
        scheduler.add_job(
            update_margins_and_rebuild_job,
            trigger=CronTrigger(hour=0, minute=5),
            id='margins_and_rebuild',
            name='Marj Güncelle + Jeweler Rebuild',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 11:55 - Akşam haberlerini HAZIRLA
        scheduler.add_job(
            prepare_evening_news_job,
            trigger=CronTrigger(hour=11, minute=55),
            id='prepare_evening_news',
            name='Akşam Haberlerini Hazırla (Gemini)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 12:00 - Akşam YAYINLA
        scheduler.add_job(
            publish_evening_news_job,
            trigger=CronTrigger(hour=12, minute=0),
            id='publish_evening_news',
            name='Akşam Yayın',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 14:00 - Push Notification
        scheduler.add_job(
            push_notification_daily,
            trigger=CronTrigger(hour=14, minute=0),
            id='push_notification',
            name='Push Notification (Bayram/Haber)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        scheduler.start()
        logger.info("✅ Scheduler başlatıldı! (V5.5 - CPU Spike Önleme + Smooth Margin)")
        logger.info(f"   👷 Worker: Her {worker_interval} saniyede")
        logger.info("   👮 Şef: Her 10 dakikada")
        logger.info(f"   🔔 Alarm: Her {alarm_interval_minutes} dakikada")
        logger.info("   📊 Rapor: Her gün 09:00")
        logger.info("   🧹 Cleanup: Her gün 03:00")
        logger.info("")
        logger.info("   🔥 V5.5 OPTIMIZED TIMELINE:")
        logger.info("   🌙 23:55 → Sabah haberlerini HAZIRLA (Gemini)")
        logger.info("   📸 00:00 → Snapshot AL + Sabah YAYINLA (hafif)")
        logger.info("   💰 00:05 → Marj GÜNCELLE + Jeweler Rebuild + Snapshot Update")
        logger.info("   🌆 11:55 → Akşam haberlerini HAZIRLA (Gemini)")
        logger.info("   📰 12:00 → Akşam YAYINLA (hafif)")
        logger.info("   🔔 14:00 → Push Notification GÖNDER")
        logger.info("")
        logger.info("   ✅ CPU spike önleme: AKTİF")
        logger.info("   ✅ Smooth margin: AKTİF")
        logger.info("   ✅ Jeweler rebuild: OTOMATİK")
        logger.info("   ✅ Snapshot update: OTOMATİK")


def stop_scheduler():
    """🛑 Scheduler durdur"""
    global scheduler
    
    with _scheduler_lock:
        if scheduler and scheduler.running:
            scheduler.shutdown()
            logger.info("🛑 Scheduler durduruldu")
        else:
            logger.warning("⚠️ Scheduler zaten durmuş")


def get_scheduler_status() -> Dict[str, Any]:
    """📊 Scheduler durumunu getir"""
    try:
        if not scheduler:
            return {'running': False, 'jobs': []}
        
        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': str(job.next_run_time) if job.next_run_time else None
            })
        
        last_worker_run = get_cache(Config.CACHE_KEYS['last_worker_run'])
        last_cleanup_run = get_cache(Config.CACHE_KEYS['cleanup_last_run'])
        last_alarm_check = get_cache(Config.CACHE_KEYS['alarm_last_check'])
        
        worker_interval = getattr(Config, 'UPDATE_INTERVAL', 60)
        
        status = {
            'running': scheduler.running,
            'jobs': jobs,
            'last_worker_run': last_worker_run,
            'last_cleanup_run': last_cleanup_run,
            'last_alarm_check': last_alarm_check,
            'worker_interval': worker_interval,
            'alarm_interval': getattr(Config, 'ALARM_CHECK_INTERVAL', 10),
            'cleanup_age_days': Config.CLEANUP_BACKUP_AGE_DAYS,
            'maintenance_active': check_maintenance_status()['is_active'],
            'version': 'V5.5',
            'optimizations': {
                'cpu_spike_prevention': True,
                'smooth_margin': True,
                'jeweler_auto_rebuild': True,
                'snapshot_auto_update': True
            }
        }
        
        return status
        
    except Exception as e:
        logger.error(f"❌ Scheduler status hatası: {e}")
        return {'running': False, 'jobs': []}
