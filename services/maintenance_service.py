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

SANITY_RULES = {
    "USD": (20.0,    300.0),
    "EUR": (20.0,    350.0),
    "GBP": (25.0,    400.0),
    "CHF": (20.0,    350.0),
    "GRA": (500.0,  50000.0),
    "C22": (500.0,  50000.0),
    "YAR": (500.0, 100000.0),
    "TAM": (500.0, 200000.0),
    "CUM": (500.0, 200000.0),
    "AG":  (0.5,     2000.0),
}

SANITY_NOTIFY_COOLDOWN = 3600

GOLD_MARGIN_KEYS = ['GRA', 'C22', 'YAR', 'TAM', 'ATA', 'AG', 'HAS', 'GUMUS']

_MIN_ACCEPTABLE = {
    'GRA':   0.015,
    'C22':   0.010,
    'YAR':   0.008,
    'TAM':   0.005,
    'CUM':   0.008,
    'ATA':   0.008,
    'HAS':   0.004,
    'AG':    0.050,
    'GUMUS': 0.050,
}

_MAX_STEP_PER_CYCLE = 0.005


def _is_weekend_now() -> bool:
    import pytz
    from services.financial_service import is_weekend_closed
    tz = pytz.timezone('Europe/Istanbul')
    return is_weekend_closed(datetime.now(tz))


def _is_weekend_alarm_now() -> bool:
    import pytz
    from services.financial_service import is_weekend_alarm_closed
    tz = pytz.timezone('Europe/Istanbul')
    return is_weekend_alarm_closed(datetime.now(tz))


def _send_telegram(message: str, level: str = 'warning'):
    try:
        from utils.telegram_monitor import get_telegram_monitor
        telegram = get_telegram_monitor()
        if telegram:
            telegram._send_raw(message)
    except Exception as e:
        logger.warning(f"⚠️ Telegram gönderilemedi: {e}")


def run_sanity_check() -> bool:
    try:
        currencies_raw = get_cache(Config.CACHE_KEYS['currencies_all'])
        golds_raw      = get_cache(Config.CACHE_KEYS['golds_all'])
        silvers_raw    = get_cache(Config.CACHE_KEYS['silvers_all'])

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

        bad_list_str = "\n".join(f"  ❌ {b}" for b in bad_items)
        logger.critical(f"🚨 [SANİTY] BOZUK VERİ TESPİT EDİLDİ!\n{bad_list_str}")

        cooldown_key = "sanity:last_notify"
        last_notify  = get_cache(cooldown_key)
        now          = time.time()
        should_notify = True

        if last_notify:
            try:
                elapsed = now - float(last_notify)
                if elapsed < SANITY_NOTIFY_COOLDOWN:
                    remaining = int((SANITY_NOTIFY_COOLDOWN - elapsed) / 60)
                    logger.warning(f"🔕 [SANİTY] Bildirim cooldown'da, {remaining} dk sonra tekrar gönderilecek")
                    should_notify = False
            except Exception:
                pass

        if should_notify:
            set_cache(cooldown_key, str(now), ttl=SANITY_NOTIFY_COOLDOWN)
            _send_telegram(
                f"🚨 *SANİTY CHECK ALARMI!*\n\n"
                f"Bozuk fiyat tespit edildi:\n"
                f"```\n{chr(10).join(bad_items)}\n```\n\n"
                f"🔄 Worker yeniden tetikleniyor...\n"
                f"_(Bir sonraki bildirim 1 saat sonra)_"
            )

        logger.warning("🔄 [SANİTY] Worker tetikleniyor (taze veri çek)...")
        try:
            from services.financial_service import update_financial_data
            worker_ok = update_financial_data()
        except Exception as we:
            logger.error(f"❌ [SANİTY] Worker hatası: {we}")
            worker_ok = False

        if worker_ok:
            logger.info("✅ [SANİTY] Worker başarılı, taze veri yüklendi")
            return False

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
            _send_telegram(
                "⚠️ *SANİTY: BACKUP YÜKLENDİ*\n\n"
                "Worker başarısız oldu.\n"
                "Sistem yedeği kullanıyor.\n"
                "Bir sonraki worker çalışmasında güncellenecek."
            )
        else:
            logger.critical("❌ [SANİTY] BACKUP DA YOK! Veri bozuk kalıyor.")
            _send_telegram(
                "🚨 *KRİTİK: SANİTY + BACKUP BAŞARISIZ!*\n\n"
                "Bozuk veri düzeltilemedi.\n"
                "Manuel müdahale gerekiyor!"
            )

        return False

    except Exception as e:
        logger.error(f"❌ [SANİTY] Beklenmeyen hata: {e}")
        return True


def check_maintenance_status() -> Dict[str, Any]:
    maintenance_data = get_cache(Config.CACHE_KEYS['maintenance'])
    if not maintenance_data:
        return {'is_active': False, 'banner_message': None}
    return {
        'is_active': True,
        'banner_message': maintenance_data.get('message', Config.MAINTENANCE_DEFAULT_MESSAGE)
    }


def activate_maintenance(message: Optional[str] = None) -> bool:
    try:
        banner_msg = message or Config.MAINTENANCE_DEFAULT_MESSAGE
        maintenance_data = {'message': banner_msg, 'activated_at': time.time()}
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
        job_id    = event.job_id
        exception = event.exception
        logger.critical(f"💣 SCHEDULER JOB HATASI!")
        logger.critical(f"   Job ID: {job_id}")
        logger.critical(f"   Hata: {exception}")
        logger.critical(f"   Hata Tipi: {type(exception).__name__}")
        _send_telegram(
            f"🚨 *KRİTİK: SCHEDULER JOB ÇÖKTÜ!*\n\n"
            f"*Job ID:* `{job_id}`\n"
            f"*Hata Tipi:* `{type(exception).__name__}`\n"
            f"*Hata Mesajı:*\n```\n{str(exception)[:500]}\n```\n\n"
            f"⚠️ Sistem otomatik olarak job'ı yeniden başlatacak."
        )


def worker_job():
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
    try:
        logger.info("👮 [ŞEF] Sistem kontrolü başlıyor...")

        snapshot_exists = bool(get_cache(Config.CACHE_KEYS['raw_snapshot']))
        if not snapshot_exists:
            logger.warning("⚠️ [ŞEF] Snapshot kayıp! Acil snapshot alınıyor...")
            from services.financial_service import save_daily_snapshot
            save_daily_snapshot()

        last_worker_run = get_cache(Config.CACHE_KEYS['last_worker_run'])
        if last_worker_run:
            time_diff = time.time() - float(last_worker_run)
            if time_diff > Config.SUPERVISOR_WORKER_TIMEOUT:
                logger.warning(f"⚠️ [ŞEF] Worker {int(time_diff/60)} dakikadır uyuyor! Uyandırılıyor...")
                worker_job()

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
    try:
        logger.info("🧹 [CLEANUP] Eski backup temizliği başlıyor...")
        from utils.cache import cleanup_old_disk_backups, get_disk_backup_stats
        before_stats = get_disk_backup_stats()
        result       = cleanup_old_disk_backups(max_age_days=Config.CLEANUP_BACKUP_AGE_DAYS)
        deleted_count = result.get('deleted_count', 0)
        after_stats   = result.get('after_stats', {})
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
    try:
        if _is_weekend_alarm_now():
            logger.info("🔒 [ALARM] Hafta sonu penceresi - alarm kontrolü atlandı (Cuma 18:00 → Pazartesi 00:10)")
            return

        logger.info("🔔 [ALARM] Periyodik alarm kontrolü başlıyor...")
        from services.alarm_service import check_all_alarms
        result = check_all_alarms()

        total       = result.get('total_alarms', 0)
        checked     = result.get('checked', 0)
        triggered   = result.get('triggered', 0)
        failed      = result.get('failed', 0)
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


def prepare_morning_news_job():
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


def monday_snapshot_refresh_job():
    try:
        now = datetime.now()
        if now.weekday() != 0:
            return

        logger.info("📸 [PAZARTESİ SNAPSHOT] Yeni hafta snapshot'ı yenileniyor...")
        from services.financial_service import save_daily_snapshot
        snapshot_success = save_daily_snapshot()

        if snapshot_success:
            logger.info(
                "✅ [PAZARTESİ SNAPSHOT] Snapshot yenilendi. "
                "PERCENT alarmlar artık Pazartesi açılış fiyatına göre çalışacak."
            )
            _send_telegram(
                "📸 *PAZARTESİ SNAPSHOT YENİLENDİ*\n\n"
                "00:15 yeni hafta snapshot'ı alındı.\n"
                "Marj + ham fiyat artık stabil.\n"
                "PERCENT alarmlar Pazartesi açılışına göre çalışıyor."
            )
        else:
            logger.warning("⚠️ [PAZARTESİ SNAPSHOT] Snapshot alınamadı!")

    except Exception as e:
        logger.error(f"❌ [PAZARTESİ SNAPSHOT] Hata: {e}")
        raise


def prepare_evening_news_job():
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


def retry_morning_news_job():
    try:
        shift_key  = Config.CACHE_KEYS.get('news_morning_shift', 'news:morning_shift')
        shift_data = get_cache(shift_key)
        if shift_data and len(shift_data) > 0:
            logger.info("ℹ️ [SABAH RETRY] Sabah haberleri zaten mevcut, atlanıyor")
            return
        logger.warning("🔄 [SABAH RETRY] Sabah haberleri eksik, yeniden deneniyor...")
        from utils.news_manager import prepare_morning_news, publish_morning_news
        prepare_ok = prepare_morning_news()
        if prepare_ok:
            publish_morning_news()
            logger.info("✅ [SABAH RETRY] Tamamlandı")
        else:
            logger.error("❌ [SABAH RETRY] Hazırlama yine başarısız")
    except Exception as e:
        logger.error(f"❌ [SABAH RETRY] Hata: {e}")
        raise


def retry_evening_news_job():
    try:
        shift_key  = Config.CACHE_KEYS.get('news_evening_shift', 'news:evening_shift')
        shift_data = get_cache(shift_key)
        if shift_data and len(shift_data) > 0:
            logger.info("ℹ️ [AKŞAM RETRY] Akşam haberleri zaten mevcut, atlanıyor")
            return
        logger.warning("🔄 [AKŞAM RETRY] Akşam haberleri eksik, yeniden deneniyor...")
        from utils.news_manager import prepare_evening_news, publish_evening_news
        prepare_ok = prepare_evening_news()
        if prepare_ok:
            publish_evening_news()
            logger.info("✅ [AKŞAM RETRY] Tamamlandı")
        else:
            logger.error("❌ [AKŞAM RETRY] Hazırlama yine başarısız")
    except Exception as e:
        logger.error(f"❌ [AKŞAM RETRY] Hata: {e}")
        raise


def push_notification_daily():
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


def bayram_notification_job():
    try:
        today      = date.today()
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


def _do_jeweler_rebuild():
    try:
        from services.financial_service import rebuild_jeweler_cache, update_jeweler_snapshot
        rebuild_jeweler_cache()
        update_jeweler_snapshot()
        logger.info("✅ [MARJ] Jeweler cache rebuild tamamlandı")
    except Exception as rb_err:
        logger.error(f"❌ [MARJ] Jeweler rebuild hatası: {rb_err}")


def _apply_gradual_margins(current_margins: dict, new_margins: dict) -> dict:
    result = dict(current_margins)
    for key, new_val in new_margins.items():
        old_val = current_margins.get(key, new_val)
        diff = new_val - old_val
        if abs(diff) > _MAX_STEP_PER_CYCLE:
            step = _MAX_STEP_PER_CYCLE if diff > 0 else -_MAX_STEP_PER_CYCLE
            result[key] = round(old_val + step, 6)
            logger.info(f"  📈 [KADEMELI] {key}: {old_val:.4f} → {result[key]:.4f} (hedef: {new_val:.4f})")
        else:
            result[key] = new_val
    return result


def _retry_gold_margins_async(harem_html: str, gold_api_prices: dict):
    try:
        time.sleep(300)
        logger.info("🔄 [MARJ] Altın retry başlıyor (5dk sonra)...")
        from utils.news_manager import calculate_full_margins_with_gemini
        result = calculate_full_margins_with_gemini(harem_html, gold_api_prices)
        if result:
            margin_key = Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins')
            existing   = get_cache(margin_key) or {}
            applied    = _apply_gradual_margins(existing, result)
            existing.update(applied)
            set_cache(margin_key, existing, ttl=86400)
            logger.info(f"✅ [MARJ] Altın retry başarılı! {len(result)} marj güncellendi.")
            _do_jeweler_rebuild()
            _send_telegram(
                f"✅ *MARJ: Altın Retry Başarılı*\n\n"
                f"{len(result)} altın/gümüş marjı kademeli güncellendi.\n"
                f"Jeweler cache yeniden oluşturuldu."
            )
        else:
            logger.warning("⚠️ [MARJ] Altın retry de başarısız, mevcut marj kalıyor.")
            _send_telegram(
                "⚠️ *MARJ: Altın Retry Başarısız*\n\n"
                "Mevcut marjlar kullanılmaya devam ediyor.\n"
                "Bir sonraki 6 saatlik döngüde tekrar denenecek."
            )
    except Exception as e:
        logger.error(f"❌ [MARJ] Altın retry hatası: {e}")


def check_and_refresh_margins():
    try:
        if _is_weekend_now():
            logger.info("🔒 [MARJ] Hafta sonu - kontrol atlandı")
            return

        logger.info("🏥 [MARJ] 6 saatlik kontrol + güncelleme başlıyor...")

        from utils.news_manager import (
            fetch_harem_html,
            calculate_full_margins_with_gemini,
            calculate_currency_margins_with_gemini,
            fetch_ziraat_html,
            _FALLBACK_GOLD_MARGINS,
        )
        from services.financial_service import fetch_from_v5

        margin_key      = Config.CACHE_KEYS.get('dynamic_margins', 'dynamic:margins')
        current_margins = get_cache(margin_key) or {}

        sorunlu = []
        for key in GOLD_MARGIN_KEYS:
            deger     = current_margins.get(key, None)
            min_deger = _MIN_ACCEPTABLE.get(key, 0.005)
            if deger is None:
                logger.warning(f"  ❌ {key}: YOK (eksik)")
                sorunlu.append(key)
            elif deger < min_deger:
                logger.warning(f"  ❌ {key}: {deger:.4f} (%{deger*100:.2f}) → çok düşük (min %{min_deger*100:.1f})")
                sorunlu.append(key)
            else:
                logger.info(f"  ✅ {key}: {deger:.4f} (%{deger*100:.2f}) → OK")

        harem_html = fetch_harem_html()
        ziraat_html = fetch_ziraat_html()
        gold_api_prices = {}
        currency_api_prices = {}

        try:
            api_data = fetch_from_v5()
            if api_data and 'Rates' in api_data:
                # Buying kullanıyoruz: kuyumcu marjı = (Harem Satış - Borsa Alış) / Borsa Alış
                gold_api_prices = {
                    'GRA':         api_data['Rates'].get('GRA', {}).get('Buying', 0),
                    'CEYREKALTIN': api_data['Rates'].get('CEYREKALTIN', {}).get('Buying', 0),
                    'YARIMALTIN':  api_data['Rates'].get('YARIMALTIN', {}).get('Buying', 0),
                    'TAMALTIN':    api_data['Rates'].get('TAMALTIN', {}).get('Buying', 0),
                    'GUMUS':       api_data['Rates'].get('GUMUS', {}).get('Buying', 0),
                }
                major_currencies = ["USD", "EUR", "GBP", "CHF", "CAD", "AUD", "SEK", "NOK", "SAR", "DKK", "JPY"]
                currency_api_prices = {
                    code: api_data['Rates'].get(code, {}).get('Selling', 0)
                    for code in major_currencies
                }
        except Exception as api_err:
            logger.warning(f"⚠️ [MARJ] API verisi alınamadı: {api_err}")

        if sorunlu:
            logger.warning(f"⚠️ [MARJ] {len(sorunlu)} sorunlu marj: {sorunlu} → acil Gemini tetikleniyor!")
            _send_telegram(
                f"⚠️ *MARJ: Sorunlu Marjlar Tespit Edildi!*\n\n"
                f"Sorunlu: `{', '.join(sorunlu)}`\n\n"
                f"Gemini'den çekiliyor..."
            )

            if harem_html and gold_api_prices:
                gold_result = calculate_full_margins_with_gemini(
                    harem_html, gold_api_prices, old_margins=current_margins
                )
                if gold_result:
                    applied = _apply_gradual_margins(current_margins, gold_result)
                    current_margins.update(applied)
                    set_cache(margin_key, current_margins, ttl=86400)
                    _save_margin_update(current_margins)
                    logger.info(f"✅ [MARJ] Acil güncelleme başarılı: {list(gold_result.keys())}")
                    _do_jeweler_rebuild()
                    _send_telegram(
                        f"✅ *MARJ: Sorunlu Marjlar Düzeltildi*\n\n"
                        f"Güncellenen: `{', '.join(gold_result.keys())}`\n"
                        f"Jeweler cache yeniden oluşturuldu."
                    )
                    return
                else:
                    last_key     = Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update')
                    last_data    = get_cache(last_key) or {}
                    last_margins = last_data.get('margins', {})
                    old_gold     = {
                        k: v for k, v in last_margins.items()
                        if k in GOLD_MARGIN_KEYS and v >= _MIN_ACCEPTABLE.get(k, 0.005)
                    }
                    if old_gold:
                        current_margins.update(old_gold)
                        set_cache(margin_key, current_margins, ttl=86400)
                        logger.warning(f"⚠️ [MARJ] Son bilinen marjlar kullanıldı: {list(old_gold.keys())}")
                        _do_jeweler_rebuild()
                        _send_telegram(
                            "⚠️ *MARJ: Gemini Başarısız*\n\n"
                            "Son bilinen geçerli marjlar kullanılıyor.\n"
                            "5 dakika sonra tekrar denenecek..."
                        )
                    else:
                        current_margins.update(_FALLBACK_GOLD_MARGINS)
                        set_cache(margin_key, current_margins, ttl=86400)
                        logger.warning("⚠️ [MARJ] Fallback devreye girdi.")
                        _do_jeweler_rebuild()
                        _send_telegram(
                            "🚨 *MARJ: Fallback Devreye Girdi*\n\n"
                            "Gemini ve geçmiş marj başarısız.\n"
                            "Sabit fallback değerler kullanılıyor.\n"
                            "5 dakika sonra tekrar denenecek..."
                        )
                    threading.Thread(
                        target=_retry_gold_margins_async,
                        args=(harem_html, gold_api_prices),
                        daemon=True
                    ).start()
            else:
                logger.error("❌ [MARJ] Harem HTML veya API verisi alınamadı!")
                current_margins.update(_FALLBACK_GOLD_MARGINS)
                set_cache(margin_key, current_margins, ttl=86400)
                _do_jeweler_rebuild()
                _send_telegram(
                    "🚨 *MARJ: Kaynak Erişim Hatası*\n\n"
                    "Harem HTML veya API verisi alınamadı.\n"
                    "Fallback marjlar kullanılıyor."
                )
            return

        logger.info("✅ [MARJ] Tüm marjlar sağlıklı — rutin 6 saatlik güncelleme yapılıyor...")

        updated = False

        if harem_html and gold_api_prices:
            gold_result = calculate_full_margins_with_gemini(
                harem_html, gold_api_prices, old_margins=current_margins
            )
            if gold_result:
                applied = _apply_gradual_margins(current_margins, gold_result)
                current_margins.update(applied)
                updated = True
                logger.info(f"✅ [MARJ] Altın/Gümüş kademeli güncellendi: {list(gold_result.keys())}")
            else:
                logger.warning("⚠️ [MARJ] Rutin güncelleme: Gemini altın başarısız, mevcut marjlar korundu")

        if ziraat_html and currency_api_prices:
            currency_result = calculate_currency_margins_with_gemini(
                ziraat_html, currency_api_prices, old_margins=current_margins
            )
            if currency_result:
                applied_currency = _apply_gradual_margins(current_margins, currency_result)
                current_margins.update(applied_currency)
                updated = True
                logger.info(f"✅ [MARJ] Döviz kademeli güncellendi: {list(currency_result.keys())}")
            else:
                logger.warning("⚠️ [MARJ] Rutin güncelleme: Gemini döviz başarısız, mevcut marjlar korundu")

        exotic_margins = getattr(Config, 'STATIC_EXOTIC_MARGINS', {})
        gold_static_margins = getattr(Config, 'STATIC_GOLD_MARGINS', {})
        current_margins.update(exotic_margins)
        current_margins.update(gold_static_margins)

        if updated:
            set_cache(margin_key, current_margins, ttl=86400)
            _save_margin_update(current_margins)
            _do_jeweler_rebuild()
            logger.info("✅ [MARJ] 6 saatlik kademeli güncelleme tamamlandı, jeweler rebuild yapıldı")
        else:
            logger.info("ℹ️ [MARJ] Güncelleme yapılamadı, mevcut marjlar korunuyor")

    except Exception as e:
        logger.error(f"❌ [MARJ] Beklenmeyen hata: {e}")
        raise


def _save_margin_update(margins: dict):
    try:
        update_key = Config.CACHE_KEYS.get('margin_last_update', 'margin:last_update')
        set_cache(update_key, {'timestamp': time.time(), 'margins': margins}, ttl=0)
    except Exception as e:
        logger.warning(f"⚠️ [MARJ] margin_last_update kaydedilemedi: {e}")


def start_scheduler():
    global scheduler

    with _scheduler_lock:
        if scheduler and scheduler.running:
            logger.warning("⚠️ Scheduler zaten çalışıyor!")
            return

        scheduler = BackgroundScheduler(timezone=Config.DEFAULT_TIMEZONE)
        scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR)
        logger.info("✅ Job Error Listener eklendi")

        worker_interval        = getattr(Config, 'UPDATE_INTERVAL', 60)
        alarm_interval_minutes = getattr(Config, 'ALARM_CHECK_INTERVAL', 15)

        scheduler.add_job(
            worker_job,
            trigger=IntervalTrigger(seconds=worker_interval),
            id='worker',
            name='Worker (Veri Güncelleyici)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            supervisor_check,
            trigger=IntervalTrigger(minutes=Config.SUPERVISOR_INTERVAL),
            id='supervisor',
            name='Şef (Sistem Kontrolü)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            daily_report,
            trigger=CronTrigger(hour=Config.TELEGRAM_DAILY_REPORT_HOUR),
            id='daily_report',
            name='Günlük Rapor',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            cleanup_old_backups,
            trigger=CronTrigger(hour=3, minute=0),
            id='cleanup',
            name='Cleanup (Eski Backup Temizliği)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            alarm_check_job,
            trigger=IntervalTrigger(minutes=alarm_interval_minutes),
            id='alarm_check',
            name='Alarm Check (Fiyat Alarmları)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            prepare_morning_news_job,
            trigger=CronTrigger(hour=23, minute=55),
            id='prepare_morning_news',
            name='Sabah Haberlerini Hazırla (Gemini)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            snapshot_and_publish_morning_job,
            trigger=CronTrigger(hour=0, minute=0, second=0),
            id='snapshot_and_publish_morning',
            name='Snapshot + Sabah Yayın',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            monday_snapshot_refresh_job,
            trigger=CronTrigger(day_of_week='mon', hour=0, minute=15),
            id='monday_snapshot_refresh',
            name='Pazartesi Snapshot Yenile (Yeni Hafta Baseline)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            retry_morning_news_job,
            trigger=CronTrigger(hour=1, minute=0),
            id='retry_morning_news_1',
            name='Sabah Haber Retry 1 (01:00)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            retry_morning_news_job,
            trigger=CronTrigger(hour=3, minute=0),
            id='retry_morning_news_2',
            name='Sabah Haber Retry 2 (03:00)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            prepare_evening_news_job,
            trigger=CronTrigger(hour=11, minute=55),
            id='prepare_evening_news',
            name='Akşam Haberlerini Hazırla (Gemini)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            publish_evening_news_job,
            trigger=CronTrigger(hour=12, minute=0),
            id='publish_evening_news',
            name='Akşam Yayın',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            retry_evening_news_job,
            trigger=CronTrigger(hour=13, minute=0),
            id='retry_evening_news_1',
            name='Akşam Haber Retry 1 (13:00)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            retry_evening_news_job,
            trigger=CronTrigger(hour=15, minute=0),
            id='retry_evening_news_2',
            name='Akşam Haber Retry 2 (15:00)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            push_notification_daily,
            trigger=CronTrigger(hour=14, minute=0),
            id='push_notification',
            name='Push Notification (Bayram/Haber)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            check_and_refresh_margins,
            trigger=IntervalTrigger(hours=6),
            id='margin_health_check',
            name='Marj Sağlık + Kademeli Güncelleme (6 Saatte Bir)',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now() + timedelta(hours=1)
        )

        scheduler.add_job(
            bayram_notification_job,
            trigger=CronTrigger(hour=9, minute=0),
            id='bayram_notification',
            name='Bayram Bildirimi (Dini & Milli)',
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.add_job(
            kasim_notification_job,
            trigger=CronTrigger(hour=9, minute=5),
            id='kasim_notification',
            name="10 Kasım Atatürk'ü Anma",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        scheduler.start()
        logger.info("✅ Scheduler başlatıldı! (V6.4 - KADEMELİ MARJ GÜNCELLEMESİ)")
        logger.info(f"   👷 Worker:       Her {worker_interval} saniyede")
        logger.info("   👮 Şef:          Her 10 dakikada (+ Sanity Check)")
        logger.info(f"   🔔 Alarm:        Her {alarm_interval_minutes} dakikada (Cuma 18:00 → Pazartesi 00:10 duraklatılır)")
        logger.info("   📊 Rapor:        Her gün 09:00")
        logger.info("   🧹 Cleanup:      Her gün 03:00")
        logger.info("")
        logger.info("   🔥 V6.4 MARJ SİSTEMİ:")
        logger.info("   💰 Her 6 saatte bir → Hem sağlık kontrolü hem kademeli güncelleme")
        logger.info("   📈 Kademeli adım:  Max %0.5 per döngü (alarm patlaması önlenir)")
        logger.info("   🚫 00:05 marj job'ı kaldırıldı (6 saatlik döngü yeterli)")
        logger.info("")
        logger.info("   🔥 V6.4 PAZARTESİ GEÇİŞ YÖNETİMİ:")
        logger.info("   🔒 Alarm kontrolü Cuma 18:00 → Pazartesi 00:10 arası duraklatılır")
        logger.info("   📸 Pazar 23:58 → Worker başlar, API verisi gelir")
        logger.info("   📸 Pazartesi 00:00 → Snapshot alınır")
        logger.info("   ✅ Pazartesi 00:10 → Alarm kontrolü başlar")
        logger.info("   📸 Pazartesi 00:15 → Snapshot YENİLENİR (Pazartesi açılış baseline)")
        logger.info("")
        logger.info("   🔥 OPTIMIZED TIMELINE:")
        logger.info("   🌙 23:55 → Sabah haberlerini HAZIRLA (Gemini)")
        logger.info("   📸 00:00 → Snapshot AL + Sabah YAYINLA")
        logger.info("   🔄 01:00 → Sabah Haber Retry 1")
        logger.info("   🔄 03:00 → Sabah Haber Retry 2")
        logger.info("   🎉 09:00 → Bayram Bildirimi")
        logger.info("   🕯️ 09:05 → 10 Kasım Atatürk'ü Anma")
        logger.info("   🌆 11:55 → Akşam haberlerini HAZIRLA (Gemini)")
        logger.info("   📰 12:00 → Akşam YAYINLA")
        logger.info("   🔄 13:00 → Akşam Haber Retry 1")
        logger.info("   🔔 14:00 → Push Notification GÖNDER")
        logger.info("   🔄 15:00 → Akşam Haber Retry 2")
        logger.info("   💰 Her 6 saatte → Marj Sağlık + Kademeli Güncelleme")
        logger.info("")
        logger.info("   ✅ Kademeli marj geçişi:            AKTİF  ← YENİ V6.4")
        logger.info("   ✅ 6 saatlik birleşik marj döngüsü: AKTİF  ← YENİ V6.4")
        logger.info("   ✅ Pazartesi snapshot yenileme:     AKTİF")
        logger.info("   ✅ Gelişmiş hafta sonu alarm koru.: AKTİF")
        logger.info("   ✅ Otomatik Gemini retry (5dk):     AKTİF")
        logger.info("   ✅ Son bilinen marj fallback:       AKTİF")
        logger.info("   ✅ Sabit fallback marj:             AKTİF")
        logger.info("   ✅ Telegram bildirimleri:           AKTİF")
        logger.info("   ✅ Jeweler rebuild:                 OTOMATİK")
        logger.info("   ✅ Sanity check:                    AKTİF")
        logger.info("   ✅ Haber retry:                     AKTİF")
        logger.info("   ✅ Hafta sonu marj koruması:        AKTİF")


def stop_scheduler():
    global scheduler
    with _scheduler_lock:
        if scheduler and scheduler.running:
            scheduler.shutdown()
            logger.info("🛑 Scheduler durduruldu")
        else:
            logger.warning("⚠️ Scheduler zaten durmuş")


def get_scheduler_status() -> Dict[str, Any]:
    try:
        if not scheduler:
            return {'running': False, 'jobs': []}

        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                'id':       job.id,
                'name':     job.name,
                'next_run': str(job.next_run_time) if job.next_run_time else None
            })

        last_worker_run  = get_cache(Config.CACHE_KEYS['last_worker_run'])
        last_cleanup_run = get_cache(Config.CACHE_KEYS['cleanup_last_run'])
        last_alarm_check = get_cache(Config.CACHE_KEYS['alarm_last_check'])
        worker_interval  = getattr(Config, 'UPDATE_INTERVAL', 60)

        return {
            'running':          scheduler.running,
            'jobs':             jobs,
            'last_worker_run':  last_worker_run,
            'last_cleanup_run': last_cleanup_run,
            'last_alarm_check': last_alarm_check,
            'worker_interval':  worker_interval,
            'alarm_interval':   getattr(Config, 'ALARM_CHECK_INTERVAL', 15),
            'cleanup_age_days': Config.CLEANUP_BACKUP_AGE_DAYS,
            'maintenance_active': check_maintenance_status()['is_active'],
            'version': 'V6.4',
            'optimizations': {
                'cpu_spike_prevention':       True,
                'gradual_margin_transition':  True,
                'six_hour_margin_cycle':      True,
                'jeweler_auto_rebuild':       True,
                'snapshot_auto_update':       True,
                'async_margin_bootstrap':     True,
                'margin_health_check':        True,
                'gold_margin_auto_fix':       True,
                'bayram_notifications':       True,
                'kasim_anma':                 True,
                'redis_lock_renewal':         True,
                'sanity_check':               True,
                'news_retry':                 True,
                'weekend_margin_guard':       True,
                'weekend_alarm_guard':        True,
                'monday_snapshot_refresh':    True,
                'weekend_alarm_safe_window':  'Cuma 18:00 → Pazartesi 00:10',
                'monday_baseline_snapshot':   'Pazartesi 00:15',
                'margin_max_step_per_cycle':  _MAX_STEP_PER_CYCLE,
            }
        }

    except Exception as e:
        logger.error(f"❌ Scheduler status hatası: {e}")
        return {'running': False, 'jobs': []}
