"""
Maintenance Service - PRODUCTION READY V5.2 🚧
===============================================
✅ BAKIM MODU: Tek basit bakım senaryosu (banner ile bilgilendirme)
✅ API V5: Tek kaynak sistemi
✅ BANNER SİSTEMİ: Uygulama tarafına özel mesaj gönderme
✅ SCHEDULER: Worker + Snapshot + Şef + Takvim + Push Notification + ALARM + HABER 📰
✅ TELEGRAM KOMUTLARI: Manuel kaynak değiştirme
✅ THREAD-SAFE: Güvenli veri erişimi
✅ SMART RECOVERY: Sistem çökerse otomatik kurtarma
✅ PUSH NOTIFICATION: Öğlen 12:00 günlük özet
✅ CLEANUP SYSTEM: Her gün eski backup'ları temizle
✅ ALARM SYSTEM: Her 5-15 dakikada alarm kontrolü
✅ NEWS SYSTEM: Günde 2 kez haber vardiyası (00:00 + 12:00) 📰
✅ JOB ERROR LISTENER: Job crash'lerde Telegram bildirimi (V5.1)
✅ JOB OVERLAP PROTECTION: Çift çalışma önleme (V5.1)
✅ SCHEDULER SINGLETON LOCK: Thread-safe başlatma (V5.2) 🔥
"""

import logging
import time
import threading  # 🔥 V5.2: Thread-safe lock için
from typing import Optional, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR

from utils.cache import get_cache, set_cache, delete_cache
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# 🔥 V5.2: SCHEDULER (GLOBAL + THREAD-SAFE LOCK)
# ======================================

scheduler = None
_scheduler_lock = threading.Lock()  # 🔥 V5.2: Thread-safe başlatma için

# ======================================
# BAKIM MODU YÖNETİMİ
# ======================================

def check_maintenance_status() -> Dict[str, Any]:
    """
    Bakım modunu kontrol eder.
    
    Returns:
        Dict: {
            'is_active': bool,
            'banner_message': str or None
        }
    """
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
    """
    Bakım modunu aktif eder.
    
    Args:
        message: Özel bakım mesajı (opsiyonel)
    
    Returns:
        bool: Başarılı mı?
    """
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
    """
    Bakım modunu kapatır.
    
    Returns:
        bool: Başarılı mı?
    """
    try:
        delete_cache(Config.CACHE_KEYS['maintenance'])
        logger.info("✅ Bakım modu kapatıldı")
        return True
        
    except Exception as e:
        logger.error(f"❌ Bakım modu kapatma hatası: {e}")
        return False


# ======================================
# BANNER YÖNETİMİ
# ======================================

def set_banner(message: str, ttl: int = 0) -> bool:
    """
    Banner mesajı ayarlar.
    
    Args:
        message: Banner mesajı
        ttl: Süreli mi? (0 = süresiz, >0 = saniye)
    
    Returns:
        bool: Başarılı mı?
    """
    try:
        set_cache(Config.CACHE_KEYS['banner'], message, ttl=ttl)
        logger.info(f"📢 Banner ayarlandı: {message} (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.error(f"❌ Banner ayarlama hatası: {e}")
        return False


def clear_banner() -> bool:
    """
    Banner mesajını kaldırır.
    
    Returns:
        bool: Başarılı mı?
    """
    try:
        delete_cache(Config.CACHE_KEYS['banner'])
        logger.info("🔇 Banner kaldırıldı")
        return True
    except Exception as e:
        logger.error(f"❌ Banner kaldırma hatası: {e}")
        return False


def get_current_banner() -> Optional[str]:
    """
    Mevcut banner mesajını getirir.
    
    Priority:
    1. Bakım modu aktifse -> Bakım mesajı
    2. Manuel banner varsa -> Manuel banner
    3. Hiçbiri yoksa -> None
    
    Returns:
        str or None: Banner mesajı
    """
    maintenance = check_maintenance_status()
    if maintenance['is_active']:
        return maintenance['banner_message']
    
    banner = get_cache(Config.CACHE_KEYS['banner'])
    if banner:
        return banner
    
    return None


# ======================================
# VERİ GÜVENLİĞİ (V5 + TRADINGVIEW)
# ======================================

def fetch_all_data_safe() -> bool:
    """
    Acil durumda tüm verileri yeniden çeker (Aktif kaynaktan).
    
    Returns:
        bool: Başarılı mı?
    """
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
    """
    Worker'ı manuel olarak tetikle (Telegram komutları için).
    """
    try:
        logger.info("⚡ Worker manuel olarak tetiklendi...")
        fetch_all_data_safe()
    except Exception as e:
        logger.error(f"❌ Manuel worker tetikleme hatası: {e}")


# ======================================
# 🔥 V5.1: JOB ERROR LISTENER
# ======================================

def job_error_listener(event):
    """
    🔥 V5.1 YENİ: Job hata verdiğinde tetiklenir
    
    Scheduler job'larından biri crash olursa:
    1. Detaylı log yazar
    2. Telegram'a kritik bildirim gönderir
    
    Args:
        event: APScheduler JobExecutionEvent
    """
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
# SCHEDULER FONKSİYONLARI
# ======================================

def worker_job():
    """
    👷 İŞÇİ (WORKER)
    🔥 V5.1: 1 dakikada bir veri çeker (60 saniye)
    """
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


def snapshot_job():
    """
    📸 FOTOĞRAFÇI (SNAPSHOT)
    Her gece 00:00:05'te referans fiyatlarını alır.
    """
    try:
        logger.info("📸 [SNAPSHOT] Gece fotoğrafı çekiliyor...")
        
        from services.financial_service import take_snapshot
        success = take_snapshot()
        
        if success:
            logger.info("✅ [SNAPSHOT] Başarıyla kaydedildi")
        else:
            logger.warning("⚠️ [SNAPSHOT] Kayıt başarısız")
            
    except Exception as e:
        logger.error(f"❌ [SNAPSHOT] Hata: {e}")
        raise


def supervisor_check():
    """
    👮 ŞEF (CONTROLLER)
    Her 10 dakikada bir sistemi kontrol eder ve onarır.
    """
    try:
        logger.info("👮 [ŞEF] Sistem kontrolü başlıyor...")
        
        snapshot_exists = bool(get_cache(Config.CACHE_KEYS['yesterday_prices']))
        if not snapshot_exists:
            logger.warning("⚠️ [ŞEF] Snapshot kayıp! Acil snapshot alınıyor...")
            from services.financial_service import take_snapshot
            take_snapshot()
        
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


def calendar_check():
    """
    🗓️ TAKVİM KONTROLÜ
    Her gün sabah 08:00'da bugünün etkinliklerini kontrol eder.
    """
    try:
        logger.info("🗓️ [TAKVİM] Bugünün etkinlikleri kontrol ediliyor...")
        
        from utils.event_manager import check_and_notify_events
        check_and_notify_events()
        
        logger.info("✅ [TAKVİM] Kontrol tamamlandı")
        
    except Exception as e:
        logger.error(f"❌ [TAKVİM] Hata: {e}")
        raise


def daily_report():
    """
    📊 GÜNLÜK RAPOR
    Her gün 09:00'da Telegram'a rapor gönderir.
    """
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


def push_notification_daily():
    """
    🔔 GÜNLÜK PUSH NOTIFICATION
    Her gün 12:00'de Firebase üzerinden günlük özet gönderir.
    """
    try:
        logger.info("🔔 [PUSH] Günlük push notification hazırlanıyor...")
        
        from utils.notification_service import send_daily_summary
        
        result = send_daily_summary()
        
        if result.get('success'):
            logger.info(f"✅ [PUSH] Özet gönderildi ({result.get('recipient_count', 0)} kullanıcı)")
        else:
            logger.warning(f"⚠️ [PUSH] Gönderim başarısız: {result.get('error')}")
        
    except Exception as e:
        logger.error(f"❌ [PUSH] Hata: {e}")
        raise


def cleanup_old_backups():
    """
    🧹 ESKİ BACKUP TEMİZLİĞİ
    Her gün 7 günden eski disk backup'larını siler.
    """
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
    """
    🔔 ALARM KONTROLCÜ
    Her 5-15 dakikada bir alarmları kontrol eder ve tetiklenenlere bildirim gönderir.
    """
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
# 📰 HABER SİSTEMİ JOB'LARI
# ======================================

def news_morning_shift_job():
    """
    🌅 SABAH VARDİYASI JOB
    Her gece 00:00'da çalışır, sabah için haberleri hazırlar.
    """
    try:
        logger.info("🌅 [SABAH VARDİYASI] Job başlatılıyor...")
        
        from utils.news_manager import prepare_morning_shift
        success = prepare_morning_shift()
        
        if success:
            logger.info("✅ [SABAH VARDİYASI] Başarıyla tamamlandı")
        else:
            logger.warning("⚠️ [SABAH VARDİYASI] Tamamlanamadı")
            
    except Exception as e:
        logger.error(f"❌ [SABAH VARDİYASI] Hata: {e}")
        raise


def news_evening_shift_job():
    """
    🌆 AKŞAM VARDİYASI JOB
    Her gün 12:00'da çalışır, akşam için haberleri hazırlar.
    """
    try:
        logger.info("🌆 [AKŞAM VARDİYASI] Job başlatılıyor...")
        
        from utils.news_manager import prepare_evening_shift
        success = prepare_evening_shift()
        
        if success:
            logger.info("✅ [AKŞAM VARDİYASI] Başarıyla tamamlandı")
        else:
            logger.warning("⚠️ [AKŞAM VARDİYASI] Tamamlanamadı")
            
    except Exception as e:
        logger.error(f"❌ [AKŞAM VARDİYASI] Hata: {e}")
        raise


# ======================================
# 🔥 V5.2: SCHEDULER YÖNETİMİ (THREAD-SAFE LOCK EKLENDİ!)
# ======================================

def start_scheduler():
    """
    🔥 V5.2: Zamanlayıcıyı başlat ve tüm job'ları ekle
    
    V5.2 YENİ:
    - Thread-safe lock eklendi (_scheduler_lock)
    - Aynı anda birden fazla thread başlatamaz
    - Memory leak önleme garantisi
    
    V5.1 ÖZELLİKLERİ:
    - Job Error Listener
    - Her job için max_instances=1 (overlap önleme)
    - Her job için coalesce=True (missed runs birleştir)
    - Worker interval 60 saniye (1 dakika)
    """
    global scheduler
    
    # 🔥 V5.2: THREAD-SAFE LOCK
    with _scheduler_lock:
        if scheduler and scheduler.running:
            logger.warning("⚠️ Scheduler zaten çalışıyor!")
            return
        
        scheduler = BackgroundScheduler(timezone=Config.DEFAULT_TIMEZONE)
        
        # 🔥 V5.1: ERROR LISTENER EKLE
        scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR)
        logger.info("✅ Job Error Listener eklendi")
        
        # 👷 WORKER: Her 1 dakikada bir (60 saniye)
        worker_interval = getattr(Config, 'UPDATE_INTERVAL', 60)
        
        scheduler.add_job(
            worker_job,
            trigger=IntervalTrigger(seconds=worker_interval),
            id='worker',
            name='Worker (Veri Güncelleyici)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 📸 SNAPSHOT: Her gece 00:00:05
        scheduler.add_job(
            snapshot_job,
            trigger=CronTrigger(
                hour=Config.SNAPSHOT_HOUR,
                minute=Config.SNAPSHOT_MINUTE,
                second=Config.SNAPSHOT_SECOND
            ),
            id='snapshot',
            name='Snapshot (Referans Fiyatları)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 👮 ŞEF: Her 10 dakikada bir
        scheduler.add_job(
            supervisor_check,
            trigger=IntervalTrigger(minutes=Config.SUPERVISOR_INTERVAL),
            id='supervisor',
            name='Şef (Sistem Kontrolü)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 🗓️ TAKVİM: Her gün 08:00
        scheduler.add_job(
            calendar_check,
            trigger=CronTrigger(
                hour=Config.CALENDAR_CHECK_HOUR,
                minute=Config.CALENDAR_CHECK_MINUTE
            ),
            id='calendar',
            name='Takvim (Etkinlik Kontrolü)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 📊 GÜNLÜK RAPOR: Her gün 09:00
        scheduler.add_job(
            daily_report,
            trigger=CronTrigger(hour=Config.TELEGRAM_DAILY_REPORT_HOUR),
            id='daily_report',
            name='Günlük Rapor',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 🔔 PUSH NOTIFICATION: Her gün 12:00
        scheduler.add_job(
            push_notification_daily,
            trigger=CronTrigger(
                hour=Config.PUSH_NOTIFICATION_DAILY_HOUR,
                minute=Config.PUSH_NOTIFICATION_DAILY_MINUTE
            ),
            id='push_notification',
            name='Push Notification (Günlük Özet)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 🧹 CLEANUP: Her gün 03:00
        scheduler.add_job(
            cleanup_old_backups,
            trigger=CronTrigger(hour=3, minute=0),
            id='cleanup',
            name='Cleanup (Eski Backup Temizliği)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 🔔 ALARM: Her 5-15 dakikada bir
        alarm_interval_minutes = getattr(Config, 'ALARM_CHECK_INTERVAL', 10)
        scheduler.add_job(
            alarm_check_job,
            trigger=IntervalTrigger(minutes=alarm_interval_minutes),
            id='alarm_check',
            name='Alarm Check (Fiyat Alarmları)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 🌅 SABAH VARDİYASI: Her gece 00:00
        scheduler.add_job(
            news_morning_shift_job,
            trigger=CronTrigger(hour=0, minute=0),
            id='news_morning',
            name='Haber Sabah Vardiyası',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # 🌆 AKŞAM VARDİYASI: Her gün 12:00
        scheduler.add_job(
            news_evening_shift_job,
            trigger=CronTrigger(hour=12, minute=0),
            id='news_evening',
            name='Haber Akşam Vardiyası',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        # Başlat
        scheduler.start()
        logger.info("✅ Scheduler başlatıldı! (V5.2 - Thread-Safe Lock)")
        logger.info(f"   👷 Worker: Her {worker_interval} saniyede (1 dakika)")
        logger.info("   📸 Snapshot: Her gece 00:00:05")
        logger.info("   👮 Şef: Her 10 dakikada")
        logger.info("   🗓️ Takvim: Her gün 08:00")
        logger.info("   📊 Rapor: Her gün 09:00")
        logger.info("   🔔 Push: Her gün 12:00")
        logger.info("   🧹 Cleanup: Her gün 03:00")
        logger.info(f"   🔔 Alarm: Her {alarm_interval_minutes} dakikada")
        logger.info("   🌅 Sabah Vardiyası: Her gece 00:00")
        logger.info("   🌆 Akşam Vardiyası: Her gün 12:00")
        logger.info("   🚨 Error Listener: AKTİF (Telegram bildirimi)")
        logger.info("   🛡️ Overlap Protection: AKTİF (max_instances=1)")
        logger.info("   🔒 Thread-Safe Lock: AKTİF (V5.2)")  # 🔥 YENİ


def stop_scheduler():
    """
    🔥 V5.2: Zamanlayıcıyı durdur (Thread-safe)
    """
    global scheduler
    
    # 🔥 V5.2: THREAD-SAFE LOCK
    with _scheduler_lock:
        if scheduler and scheduler.running:
            scheduler.shutdown()
            logger.info("🛑 Scheduler durduruldu")
        else:
            logger.warning("⚠️ Scheduler zaten durmuş")


def get_scheduler_status() -> Dict[str, Any]:
    """
    Zamanlayıcı durumunu döner.
    
    Returns:
        Dict: Scheduler bilgileri
    """
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
            'error_listener_active': True,
            'overlap_protection_active': True,
            'thread_safe_lock_active': True  # 🔥 V5.2 YENİ
        }
        
        return status
        
    except Exception as e:
        logger.error(f"❌ Scheduler status hatası: {e}")
        return {'running': False, 'jobs': []}
