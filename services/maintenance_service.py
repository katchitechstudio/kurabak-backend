"""
Maintenance Service - PRODUCTION READY V6.0 🚧
===============================================
✅ SCHEDULER OPTIMIZATION: CPU spike önleme (prepare/publish ayrımı)
✅ SMOOTH MARGIN TRANSITION: Kademeli marj geçişi
✅ TAM MARJ SİSTEMİ: Kuyumcu gerçeği yansıtır
✅ İKİ SNAPSHOT: raw_snapshot + jeweler_snapshot
✅ JEWELER REBUILD: Marj değişince cache otomatik yenilenir
✅ SNAPSHOT UPDATE: Marj değişince snapshot düzeltilir
✅ 🔥 KOMBO TAKTİK: Async margin bootstrap + 6 saatlik sağlık kontrolü
✅ 🎉 MİLLİ & DİNİ BAYRAM BİLDİRİMLERİ: Sabit takvim, Gemini'ye bağımlı değil
✅ 🔒 REDIS LOCK YENİLEME V5.5: worker_job her çalışmada lock'u yeniler
✅ 🧠 SANİTY CHECK V6.0: Şef bozuk veri tespiti yapıyor, backup'tan kurtarıyor

V6.0 Değişiklikler (SANİTY CHECK):
- 🧠 supervisor_check içinde USD/EUR/GRA fiyat doğrulaması
- 🔒 Fiyat 0, negatif veya aşırı anormal ise → backup yükle
- 📢 Bozuk veri tespitinde Telegram bildirimi
- Eşikler: USD 20-200 TL | EUR 20-220 TL | GRA 500-30000 TL

Timeline:
23:55 → Sabah haberlerini HAZIRLA (Gemini)
00:00 → Snapshot AL + Sabah YAYINLA (hafif)
00:05 → Marj GÜNCELLE + Jeweler Rebuild + Snapshot Update
00:05, 06:05, 12:05, 18:05 → 🔥 Marj Sağlık Kontrolü (Her 6 saat)
09:00 → 🎉 Bayram/Milli Gün Bildirim Kontrolü
09:05 → 🕯️ 10 Kasım Atatürk'ü Anma Bildirimi
11:55 → Akşam haberlerini HAZIRLA (Gemini)
12:00 → Akşam YAYINLA (hafif)
14:00 → Push notification GÖNDER
"""

import logging
import time
import threading
from datetime import datetime, timedelta, date
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


# ======================================
# 🎉 V5.7 - BAYRAM TAKVİMİ
# ======================================

DINI_BAYRAMLAR = {
    "2025-03-30": ("Ramazan Bayramı Mübarek Olsun", "Ramazan Bayramınızı en içten dileklerimizle kutlarız."),
    "2026-03-20": ("Ramazan Bayramı Mübarek Olsun", "Ramazan Bayramınızı en içten dileklerimizle kutlarız."),
    "2027-03-09": ("Ramazan Bayramı Mübarek Olsun", "Ramazan Bayramınızı en içten dileklerimizle kutlarız."),
    "2025-06-06": ("Kurban Bayramı Mübarek Olsun", "Kurban Bayramınızı en içten dileklerimizle kutlarız."),
    "2026-05-27": ("Kurban Bayramı Mübarek Olsun", "Kurban Bayramınızı en içten dileklerimizle kutlarız."),
    "2027-05-16": ("Kurban Bayramı Mübarek Olsun", "Kurban Bayramınızı en içten dileklerimizle kutlarız."),
}

MILLI_BAYRAMLAR = {
    "04-23": ("23 Nisan Ulusal Egemenlik ve Çocuk Bayramı", "Nice senelere, nice bayramlara."),
    "05-19": ("19 Mayıs Gençlik ve Spor Bayramı", "Nice senelere, nice bayramlara."),
    "07-15": ("15 Temmuz Demokrasi ve Millî Birlik Günü", "Nice senelere, nice bayramlara."),
    "08-30": ("30 Ağustos Zafer Bayramı", "Nice senelere, nice bayramlara."),
    "10-29": ("29 Ekim Cumhuriyet Bayramı", "Nice senelere, nice bayramlara."),
}


# ======================================
# 🧠 V6.0 - SANİTY CHECK KURALLARI
# ======================================

SANITY_RULES = {
    # kod: (min_fiyat, max_fiyat)
    "USD": (20.0,    200.0),
    "EUR": (20.0,    220.0),
    "GBP": (25.0,    260.0),
    "CHF": (20.0,    220.0),
    "GRA": (500.0,  30000.0),   # Gram Altın
    "C22": (100.0,   8000.0),   # Çeyrek Altın
    "AG":  (0.5,      500.0),   # Gümüş
}


def run_sanity_check() -> bool:
    """
    🧠 V6.0: Fiyat doğrulama — bozuk veri tespiti.

    Redis'teki raw cache'den SANITY_RULES içindeki kodları kontrol eder.
    Herhangi biri 0, negatif veya belirlenen aralık dışındaysa:
      1. Telegram'a kritik uyarı gönderir
      2. Worker'ı yeniden tetikler (taze veri çek)
      3. Worker da başarısız olursa backup'tan yükler

    Returns:
        True  → Veri sağlıklı
        False → Bozuk veri tespit edildi, kurtarma denendi
    """
    try:
        currencies_raw = get_cache(Config.CACHE_KEYS['currencies_all'])
        golds_raw      = get_cache(Config.CACHE_KEYS['golds_all'])
        silvers_raw    = get_cache(Config.CACHE_KEYS['silvers_all'])

        # Tüm item'ları tek listede topla
        all_items = []
        for cache_data in [currencies_raw, golds_raw, silvers_raw]:
            if cache_data and isinstance(cache_data, dict):
                all_items.extend(cache_data.get("data", []))

        if not all_items:
            logger.warning("⚠️ [SANİTY] Cache boş, kontrol atlanıyor")
            return True

        bad_items = []

        for item in all_items:
            code    = item.get("code")
            selling = item.get("selling", 0)

            if code not in SANITY_RULES:
                continue

            min_val, max_val = SANITY_RULES[code]

            if selling <= 0:
                bad_items.append(f"{code}: {selling} ₺ (SIFIR/NEGATİF)")
            elif selling < min_val:
                bad_items.append(f"{code}: {selling} ₺ (çok düşük, min {min_val})")
            elif selling > max_val:
                bad_items.append(f"{code}: {selling} ₺ (çok yüksek, max {max_val})")

        if not bad_items:
            logger.debug("✅ [SANİTY] Tüm fiyatlar sağlıklı")
            return True

        # ── Bozuk veri tespit edildi ──────────────────────────────
        bad_list_str = "\n".join(f"  ❌ {b}" for b in bad_items)
        logger.critical(
            f"🚨 [SANİTY] BOZUK VERİ TESPİT EDİLDİ!\n{bad_list_str}"
        )

        # Telegram bildirimi
        try:
            from utils.telegram_monitor import get_telegram_monitor
            telegram = get_telegram_monitor()
            if telegram:
                telegram._send_raw(
                    f"🚨 *SANİTY CHECK ALARMI!*\n\n"
                    f"Bozuk fiyat tespit edildi:\n"
                    f"```\n{chr(10).join(bad_items)}\n```\n\n"
                    f"🔄 Worker yeniden tetikleniyor..."
                )
        except Exception as tg_err:
            logger.warning(f"⚠️ [SANİTY] Telegram hatası: {tg_err}")

        # Önce worker'ı yeniden tetikle — taze veri gelsin
        logger.warning("🔄 [SANİTY] Worker tetikleniyor (taze veri çek)...")
        try:
            from services.financial_service import update_financial_data
            worker_ok = update_financial_data()
        except Exception as we:
            logger.error(f"❌ [SANİTY] Worker hatası: {we}")
            worker_ok = False

        if worker_ok:
            logger.info("✅ [SANİTY] Worker başarılı, taze veri yüklendi")
            return False  # False döndür → şef logunda görünsün

        # Worker da başarısız → backup'tan yükle
        logger.error("❌ [SANİTY] Worker başarısız, backup yükleniyor...")
        backup_data = get_cache("kurabak:backup:all")

        if backup_data:
            for asset_type in ['currencies', 'golds', 'silvers']:
                raw_key = Config.CACHE_KEYS.get(f'{asset_type}_all')
                if raw_key and asset_type in backup_data:
                    set_cache(raw_key, backup_data[asset_type], ttl=0)

                jeweler_key = Config.CACHE_KEYS.get(f'{asset_type}_jeweler')
                jeweler_data_key = f"{asset_type}_jeweler"
                if jeweler_key and jeweler_data_key in backup_data:
                    set_cache(jeweler_key, backup_data[jeweler_data_key], ttl=0)

            logger.info("✅ [SANİTY] Backup başarıyla yüklendi")

            try:
                from utils.telegram_monitor import get_telegram_monitor
                telegram = get_telegram_monitor()
                if telegram:
                    telegram._send_raw(
                        "⚠️ *SANİTY: BACKUP YÜKLENDİ*\n\n"
                        "Worker başarısız oldu.\n"
                        "Sistem yedeği kullanıyor.\n"
                        "Bir sonraki worker çalışmasında güncellenecek."
                    )
            except Exception:
                pass
        else:
            logger.critical("❌ [SANİTY] BACKUP DA YOK! Veri bozuk kalıyor.")
            try:
                from utils.telegram_monitor import get_telegram_monitor
                telegram = get_telegram_monitor()
                if telegram:
                    telegram._send_raw(
                        "🚨 *KRİTİK: SANİTY + BACKUP BAŞARISIZ!*\n\n"
                        "Bozuk veri düzeltilemedi.\n"
                        "Manuel müdahale gerekiyor!"
                    )
            except Exception:
                pass

        return False

    except Exception as e:
        logger.error(f"❌ [SANİTY] Beklenmeyen hata: {e}")
        return True  # Hata durumunda sistemi bloke etme


# ======================================
# MAINTENANCE UTILS
# ======================================

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
        try:
            from utils.cache import renew_scheduler_lock
            renew_scheduler_lock()
        except Exception:
            pass

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
    """
    👮 Şef - Sistem kontrolü V6.0

    Kontroller (sırasıyla):
    1. Raw snapshot varlığı
    2. Worker son çalışma zamanı
    3. 🧠 SANİTY CHECK — fiyat doğrulaması (V6.0)
    """
    try:
        logger.info("👮 [ŞEF] Sistem kontrolü başlıyor...")

        # 1. Raw snapshot kontrolü
        snapshot_exists = bool(get_cache(Config.CACHE_KEYS['raw_snapshot']))
        if not snapshot_exists:
            logger.warning("⚠️ [ŞEF] Snapshot kayıp! Acil snapshot alınıyor...")
            from services.financial_service import save_daily_snapshot
            save_daily_snapshot()

        # 2. Worker son çalışma zamanı kontrolü
        last_worker_run = get_cache(Config.CACHE_KEYS['last_worker_run'])
        if last_worker_run:
            time_diff = time.time() - float(last_worker_run)
            if time_diff > Config.SUPERVISOR_WORKER_TIMEOUT:
                logger.warning(f"⚠️ [ŞEF] Worker {int(time_diff/60)} dakikadır uyuyor! Uyandırılıyor...")
                worker_job()

        # 3. 🧠 SANİTY CHECK — fiyat doğrulaması (V6.0)
        # Hafta sonu ve bakım modunda piyasa kapalı olabilir,
        # bu durumlarda sanity check atla (fiyatlar güncellenmez zaten)
        is_market_closed = bool(get_cache("market_closed_logged"))
        is_maintenance   = check_maintenance_status()['is_active']

        if not is_market_closed and not is_maintenance:
            data_healthy = run_sanity_check()
            if not data_healthy:
                logger.warning("⚠️ [ŞEF] Sanity check başarısız, kurtarma denendi")
            else:
                logger.info("✅ [ŞEF] Sanity check geçti")
        else:
            reason = "hafta sonu/bakım modu" if is_market_closed else "bakım modu"
            logger.info(f"ℹ️ [ŞEF] Sanity check atlandı ({reason})")

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
# 🔥 V5.5 JOBS
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
        
        from services.financial_service import save_daily_snapshot
        snapshot_success = save_daily_snapshot()
        
        if snapshot_success:
            logger.info("✅ [SABAH YAYINI] Snapshot başarıyla alındı")
        else:
            logger.warning("⚠️ [SABAH YAYINI] Snapshot alınamadı")
        
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
        
        from utils.news_manager import update_dynamic_margins
        margin_success = update_dynamic_margins()
        
        if margin_success:
            logger.info("✅ [MARJ + REBUILD] Dinamik marjlar güncellendi")
            
            from services.financial_service import rebuild_jeweler_cache
            rebuild_success = rebuild_jeweler_cache()
            
            if rebuild_success:
                logger.info("✅ [MARJ + REBUILD] Jeweler cache rebuild tamamlandı")
            else:
                logger.warning("⚠️ [MARJ + REBUILD] Jeweler cache rebuild başarısız")
            
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
# 🎉 V5.7 - BAYRAM BİLDİRİM JOB'LARI
# ======================================

def bayram_notification_job():
    """🎉 09:00 - Dini ve Milli Bayram Bildirimi"""
    try:
        today = date.today()
        today_full = today.strftime("%Y-%m-%d")
        today_md   = today.strftime("%m-%d")

        title = None
        body  = None

        if today_full in DINI_BAYRAMLAR:
            title, body = DINI_BAYRAMLAR[today_full]
            logger.info(f"🎉 [BAYRAM] Dini bayram tespit edildi: {title}")
        elif today_md in MILLI_BAYRAMLAR:
            title, body = MILLI_BAYRAMLAR[today_md]
            logger.info(f"🏛️ [BAYRAM] Milli bayram tespit edildi: {title}")
        else:
            logger.info("ℹ️ [BAYRAM] Bugün bayram yok, bildirim gönderilmeyecek")
            return

        from utils.notification_service import send_to_all
        send_to_all(title, body, data={"type": "bayram"})
        logger.info(f"✅ [BAYRAM] Bildirim gönderildi: {title}")

    except Exception as e:
        logger.error(f"❌ [BAYRAM] Hata: {e}")
        raise


def kasim_notification_job():
    """🕯️ 09:05 - 10 Kasım Atatürk'ü Anma Bildirimi"""
    try:
        today_md = date.today().strftime("%m-%d")

        if today_md != "11-10":
            return

        logger.info("🕯️ [10 KASIM] Atatürk'ü Anma bildirimi gönderiliyor...")

        title = "10 Kasım — Atatürk'ü Anma"
        body  = "Mustafa Kemal Atatürk'ü saygı, minnet ve özlemle anıyoruz."

        from utils.notification_service import send_to_all
        send_to_all(title, body, data={"type": "anma"})
        logger.info("✅ [10 KASIM] Bildirim gönderildi")

    except Exception as e:
        logger.error(f"❌ [10 KASIM] Hata: {e}")
        raise


# ======================================
# 🔥 V5.6 KOMBO TAKTİK - MARJ SAĞLIK
# ======================================

def check_and_refresh_margins():
    """🔥 KOMBO TAKTİK: MARJ SAĞLIK KONTROLÜ — Her 6 saatte bir"""
    try:
        logger.info("🏥 [MARJ SAĞLIK] Kontrol başlıyor...")
        
        from utils.cache import get_cache
        from utils.news_manager import update_dynamic_margins
        from config import Config
        import time
        
        last_successful_key = Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update')
        last_successful = get_cache(last_successful_key)
        
        if not last_successful:
            logger.warning("⚠️ [MARJ SAĞLIK] Hiç marj yok! Güncelleniyor...")
            success = update_dynamic_margins()
            if success:
                logger.info("✅ [MARJ SAĞLIK] İlk marjlar başarıyla oluşturuldu!")
            else:
                logger.error("❌ [MARJ SAĞLIK] İlk marj oluşturulamadı!")
            return
        
        timestamp = last_successful.get('timestamp', 0)
        hours_ago = (time.time() - timestamp) / 3600
        days_ago = hours_ago / 24
        
        if hours_ago > 24:
            logger.warning(
                f"⚠️ [MARJ SAĞLIK] Marjlar çok eski ({days_ago:.1f} gün önce)! "
                f"Güncelleniyor..."
            )
            success = update_dynamic_margins()
            if success:
                logger.info("✅ [MARJ SAĞLIK] Marjlar başarıyla güncellendi!")
            else:
                logger.error("❌ [MARJ SAĞLIK] Güncelleme başarısız, 6 saat sonra tekrar denenecek")
        else:
            logger.info(f"✅ [MARJ SAĞLIK] Marjlar taze ({hours_ago:.1f} saat önce, son güncelleme)")
    
    except Exception as e:
        logger.error(f"❌ [MARJ SAĞLIK] Beklenmeyen hata: {e}")
        raise


# ======================================
# SCHEDULER START
# ======================================

def start_scheduler():
    """🚀 Scheduler başlat - V6.0 SANİTY CHECK"""
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
        
        # Alarm Check
        scheduler.add_job(
            alarm_check_job,
            trigger=IntervalTrigger(minutes=alarm_interval_minutes),
            id='alarm_check',
            name='Alarm Check (Fiyat Alarmları)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
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
        
        # Marj Sağlık Kontrolü - Her 6 saatte
        scheduler.add_job(
            check_and_refresh_margins,
            trigger=IntervalTrigger(hours=6),
            id='margin_health_check',
            name='Marj Sağlık Kontrolü',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now() + timedelta(minutes=5)
        )
        
        # 09:00 - Dini & Milli Bayram Bildirimi
        scheduler.add_job(
            bayram_notification_job,
            trigger=CronTrigger(hour=9, minute=0),
            id='bayram_notification',
            name='Bayram Bildirimi (Dini & Milli)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        # 09:05 - 10 Kasım Atatürk'ü Anma
        scheduler.add_job(
            kasim_notification_job,
            trigger=CronTrigger(hour=9, minute=5),
            id='kasim_notification',
            name='10 Kasım Atatürk\'ü Anma',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        
        scheduler.start()
        logger.info("✅ Scheduler başlatıldı! (V6.0 - SANİTY CHECK)")
        logger.info(f"   👷 Worker: Her {worker_interval} saniyede")
        logger.info("   👮 Şef: Her 10 dakikada (+ Sanity Check)")
        logger.info(f"   🔔 Alarm: Her {alarm_interval_minutes} dakikada")
        logger.info("   📊 Rapor: Her gün 09:00")
        logger.info("   🧹 Cleanup: Her gün 03:00")
        logger.info("")
        logger.info("   🔥 V6.0 OPTIMIZED TIMELINE:")
        logger.info("   🌙 23:55 → Sabah haberlerini HAZIRLA (Gemini)")
        logger.info("   📸 00:00 → Snapshot AL + Sabah YAYINLA (hafif)")
        logger.info("   💰 00:05 → Marj GÜNCELLE + Jeweler Rebuild + Snapshot Update")
        logger.info("   🎉 09:00 → Bayram Bildirimi (Dini & Milli)")
        logger.info("   🕯️ 09:05 → 10 Kasım Atatürk'ü Anma")
        logger.info("   🌆 11:55 → Akşam haberlerini HAZIRLA (Gemini)")
        logger.info("   📰 12:00 → Akşam YAYINLA (hafif)")
        logger.info("   🔔 14:00 → Push Notification GÖNDER")
        logger.info("   🏥 00:05, 06:05, 12:05, 18:05 → Marj Sağlık Kontrolü (Her 6 saat)")
        logger.info("")
        logger.info("   ✅ CPU spike önleme: AKTİF")
        logger.info("   ✅ Smooth margin: AKTİF")
        logger.info("   ✅ Jeweler rebuild: OTOMATİK")
        logger.info("   ✅ Snapshot update: OTOMATİK")
        logger.info("   ✅ Marj sağlık kontrolü: AKTİF (Her 6 saat)")
        logger.info("   ✅ Async margin bootstrap: AKTİF (Worker'da)")
        logger.info("   ✅ Dini & Milli bayram bildirimleri: AKTİF")
        logger.info("   ✅ 10 Kasım anma bildirimi: AKTİF (09:05)")
        logger.info("   ✅ Redis lock yenileme: AKTİF (Her worker çalışmasında)")
        logger.info("   ✅ Sanity check: AKTİF (Her şef kontrolünde)")


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
        
        last_worker_run  = get_cache(Config.CACHE_KEYS['last_worker_run'])
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
            'version': 'V6.0',
            'optimizations': {
                'cpu_spike_prevention':  True,
                'smooth_margin':         True,
                'jeweler_auto_rebuild':  True,
                'snapshot_auto_update':  True,
                'async_margin_bootstrap': True,
                'margin_health_check':   True,
                'bayram_notifications':  True,
                'kasim_anma':            True,
                'redis_lock_renewal':    True,
                'sanity_check':          True,   # 🆕 V6.0
            }
        }
        
        return status
        
    except Exception as e:
        logger.error(f"❌ Scheduler status hatası: {e}")
        return {'running': False, 'jobs': []}
