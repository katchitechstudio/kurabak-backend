import logging
from datetime import datetime, date
from typing import Optional, List, Dict

from utils.cache import get_cache
from config import Config

logger = logging.getLogger(__name__)

_last_logged_banner = None


def _get_today_holiday_safe() -> Optional[tuple]:
    try:
        from utils.news_manager import get_today_holiday
        return get_today_holiday()
    except Exception as e:
        logger.warning(f"⚠️ [BAYRAM] Takvim kontrolü hatası: {e}")
        return None


def get_todays_events() -> List[Dict[str, any]]:
    today_str    = date.today().strftime("%Y-%m-%d")
    current_time = datetime.now()
    events       = []

    try:
        holiday = _get_today_holiday_safe()

        if holiday and current_time.hour < 15:
            bayram_name, bayram_emoji, bayram_end = holiday
            bayram_msg = f"{bayram_emoji} {bayram_name}"
            events.append({
                "type":        "bayram",
                "message":     bayram_msg,
                "priority":    10,
                "valid_until": "15:00",
                "date":        today_str
            })
            logger.debug(f"🏦 [BAYRAM] {bayram_msg} - 15:00'a kadar gösterilecek (Priority: 10)")
        elif holiday and current_time.hour >= 15:
            bayram_name, bayram_emoji, _ = holiday
            logger.debug(f"🏦 [BAYRAM] {bayram_emoji} {bayram_name} süresi doldu (15:00+), haberler devrede")

    except Exception as e:
        logger.warning(f"⚠️ [BAYRAM] Kontrol hatası: {e}")

    try:
        from utils.news_manager import get_current_news_banner

        news_banner = get_current_news_banner()
        if news_banner:
            events.append({
                "type":        "news",
                "message":     news_banner,
                "priority":    75,
                "valid_until": "23:59",
                "date":        today_str
            })
            logger.debug(f"📰 [HABER] Banner eklendi (Priority: 75)")
    except Exception as e:
        logger.warning(f"⚠️ [HABER] Banner eklenemedi: {e}")

    events.sort(key=lambda x: x['priority'])

    return events


def get_todays_banner() -> Optional[str]:
    global _last_logged_banner

    today        = date.today()
    current_time = datetime.now()
    weekday      = today.weekday()

    events = get_todays_events()

    if events:
        top_event  = events[0]
        banner_msg = top_event['message']

        if _last_logged_banner != banner_msg:
            logger.info(
                f"📅 [BANNER] {top_event['type'].upper()} (Priority: {top_event['priority']}): "
                f"{banner_msg[:60]}..."
            )
            _last_logged_banner = banner_msg

        return banner_msg

    if weekday == 5 or weekday == 6:
        weekend_msg = "Piyasalar kapalı, iyi hafta sonları! 🌙"
        if _last_logged_banner != weekend_msg:
            logger.info("📅 [BANNER] Piyasa kapalı (Hafta sonu)")
            _last_logged_banner = weekend_msg
        return weekend_msg

    if weekday == 4 and current_time.hour >= 18:
        friday_msg = "Piyasalar kapandı, iyi hafta sonları! 🌙"
        if _last_logged_banner != friday_msg:
            logger.info("📅 [BANNER] Piyasa kapalı (Cuma akşam)")
            _last_logged_banner = friday_msg
        return friday_msg

    if _last_logged_banner is not None:
        logger.info("📅 [BANNER] Bugün özel banner yok")
        _last_logged_banner = None

    return None


def get_daily_notification_content() -> Optional[Dict[str, str]]:
    try:
        from utils.news_manager import get_current_news_banner

        news_banner = get_current_news_banner()

        if news_banner:
            logger.info(f"🔔 [PUSH NOTIFICATION] Haber mesajı hazırlandı: {news_banner[:50]}...")
            return {
                "title": "Günün Haberi",
                "body":  news_banner,
                "type":  "news"
            }
        else:
            logger.warning("⚠️ [PUSH NOTIFICATION] Haber banner'ı bulunamadı")
    except Exception as e:
        logger.error(f"❌ [PUSH NOTIFICATION] Haber kontrolü hatası: {e}")

    logger.warning("⚠️ [PUSH NOTIFICATION] Gönderilecek haber yok, bildirim gönderilmeyecek")
    return None


def test_event_manager():
    """
    Terminal'den test etmek için:
    python -c "from utils.event_manager import test_event_manager; test_event_manager()"
    """
    print("🧪 Event Manager Test Ediliyor...\n")
    print("Priority Sistemi: DÜŞÜK SAYI = YÜKSEK ÖNCELİK\n")

    print("=" * 60)
    print("0️⃣ BAYRAM TAKVİM KONTROLÜ (Cache'siz, anlık):")
    holiday = _get_today_holiday_safe()
    if holiday:
        msg, emoji, end = holiday
        current_hour    = datetime.now().hour
        status          = "AKTİF ✅ (saat < 15:00)" if current_hour < 15 else "SÜRESİ DOLDU ❌ (15:00+)"
        print(f"   🎉 Bugün bayram: {emoji} {msg} (Bitiş: {end}) — {status}")
    else:
        print("   ℹ️ Bugün bayram yok")
    print("=" * 60)
    print()

    print("=" * 60)
    banner = get_todays_banner()
    if banner:
        print(f"✅ BUGÜNÜN BANNER'I:\n{banner}\n")
    else:
        print("ℹ️ Bugün özel bir mesaj yok.\n")
    print("=" * 60)
    print()

    events = get_todays_events()
    if events:
        print("📅 BUGÜNÜN ETKİNLİKLERİ (Priority sıralı - düşük = yüksek):")
        for i, evt in enumerate(events, 1):
            priority_emoji = "🔥" if evt['priority'] < 30 else "📰" if evt['priority'] < 50 else "ℹ️"
            print(
                f"  {i}. {priority_emoji} [{evt['type'].upper()}] "
                f"Priority: {evt['priority']:>2} | {evt['message'][:80]}..."
            )
        print()
    else:
        print("ℹ️ Bugün etkinlik yok\n")

    print("=" * 60)
    print("🧪 get_daily_notification_content() TEST EDİLİYOR...")
    print("   (14:00'da gönderilecek bildirim içeriği — sadece haber)")
    print("=" * 60)
    try:
        notification = get_daily_notification_content()
        if notification:
            print(f"✅ Bildirim Hazır:")
            print(f"   Başlık: {notification['title']}")
            print(f"   İçerik: {notification['body'][:100]}...")
            print(f"   Tür: {notification['type']}")
        else:
            print("⚠️ Bildirim yok (Haber bulunamadı)")
    except Exception as e:
        print(f"❌ Hata: {e}")
        import traceback
        print(traceback.format_exc())
    print("=" * 60)


if __name__ == "__main__":
    test_event_manager()
