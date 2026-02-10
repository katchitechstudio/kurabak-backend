"""
Event Manager - AKILLI TAKVİM SİSTEMİ V7.1 🗓️📰🏦
======================================
✅ BAYRAMLAR: Gemini otomatik tespit (her vardiya hazırlığında)
✅ HABERLER: GNews + NewsData + Gemini özet
✅ ÖNCELİK SİSTEMİ: Bayram (15:00'a kadar) > Haberler
✅ TEK BANNER KURALI: Sadece en yüksek priority gösterilir
✅ BASIT VE ETKİLİ: Gereksiz karmaşıklık yok
✅ CLEAN CODE: Yorumsuz, profesyonel, production-ready
✅ LOG SPAM FIX: Banner sadece değiştiğinde loglanır (V7.1)

Priority Değerleri (Düşük sayı = Yüksek öncelik):
- 10: Bayram/Tatil
- 30: Piyasa Kapalı
- 75: Günlük Haberler

V7.1 Değişiklikler:
- LOG SPAM FIX: Banner tekrarını önlemek için cache mekanizması eklendi
- Sadece banner değiştiğinde log yazılır
- Global state ile son loglanan banner takip edilir
"""

import logging
from datetime import datetime, date
from typing import Optional, List, Dict

from utils.cache import get_cache
from config import Config

logger = logging.getLogger(__name__)

_last_logged_banner = None


def get_todays_events() -> List[Dict[str, any]]:
    """
    Bugünün tüm etkinliklerini priority sırasına göre döndürür.
    
    Returns:
        List[Dict]: [
            {
                "type": "bayram" | "news",
                "message": "...",
                "priority": 10 | 75,
                "valid_until": "15:00" | "23:59",
                "date": "2026-01-30"
            }
        ]
    """
    today_str = date.today().strftime("%Y-%m-%d")
    current_time = datetime.now()
    events = []
    
    try:
        bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
        bayram_msg = get_cache(bayram_key)
        
        if bayram_msg and current_time.hour < 15:
            events.append({
                "type": "bayram",
                "message": bayram_msg,
                "priority": 10,
                "valid_until": "15:00",
                "date": today_str
            })
            logger.debug(f"🏦 [BAYRAM] {bayram_msg} - 15:00'a kadar gösterilecek (Priority: 10)")
        elif bayram_msg and current_time.hour >= 15:
            logger.debug(f"🏦 [BAYRAM] Süresi doldu (15:00+), haberler devrede")
            
    except Exception as e:
        logger.warning(f"⚠️ [BAYRAM] Kontrol hatası: {e}")
    
    try:
        from utils.news_manager import get_current_news_banner
        
        news_banner = get_current_news_banner()
        if news_banner:
            events.append({
                "type": "news",
                "message": news_banner,
                "priority": 75,
                "valid_until": "23:59",
                "date": today_str
            })
            logger.debug(f"📰 [HABER] Banner eklendi (Priority: 75)")
    except Exception as e:
        logger.warning(f"⚠️ [HABER] Banner eklenemedi: {e}")
    
    events.sort(key=lambda x: x['priority'])
    
    return events


def get_todays_banner() -> Optional[str]:
    """
    App'te gösterilecek banner'ı döndürür (priority sırasına göre).
    
    V7.1: LOG SPAM FIX - Sadece banner değiştiğinde log yazar
    
    Returns:
        str: Banner mesajı
        None: Banner yok
    """
    global _last_logged_banner
    
    today = date.today()
    current_time = datetime.now()
    weekday = today.weekday()
    
    events = get_todays_events()
    
    if events:
        top_event = events[0]
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
    """
    14:00'da gönderilecek Firebase push bildiriminin içeriğini hazırlar.
    
    ÖNCELİK SIRASI:
    1. Bayram varsa → Bayram mesajı gönder
    2. Bayram yoksa → Günün haberi gönder
    3. İkisi de yoksa → None döndür (bildirim gönderilmez)
    
    Returns:
        Dict: {
            "title": "📅 Bugün Özel Gün!" | "📰 Günün Haberi",
            "body": "Mesaj içeriği",
            "type": "bayram" | "news"
        }
        None: Gönderilecek bildirim yok
    """
    today_str = date.today().strftime("%d.%m.%Y")
    
    try:
        bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
        bayram_msg = get_cache(bayram_key)
        
        if bayram_msg:
            logger.info(f"🔔 [PUSH NOTIFICATION] Bayram mesajı hazırlandı: {bayram_msg[:50]}...")
            return {
                "title": "📅 Bugün Özel Gün!",
                "body": bayram_msg,
                "type": "bayram"
            }
    except Exception as e:
        logger.warning(f"⚠️ [PUSH NOTIFICATION] Bayram kontrolü hatası: {e}")
    
    try:
        from utils.news_manager import get_current_news_banner
        
        news_banner = get_current_news_banner()
        
        if news_banner:
            logger.info(f"🔔 [PUSH NOTIFICATION] Haber mesajı hazırlandı: {news_banner[:50]}...")
            return {
                "title": "📰 Günün Haberi",
                "body": news_banner,
                "type": "news"
            }
        else:
            logger.warning("⚠️ [PUSH NOTIFICATION] Haber banner'ı bulunamadı")
    except Exception as e:
        logger.error(f"❌ [PUSH NOTIFICATION] Haber kontrolü hatası: {e}")
    
    logger.warning("⚠️ [PUSH NOTIFICATION] Ne bayram ne haber var, bildirim gönderilmeyecek")
    return None


def test_event_manager():
    """
    Terminal'den test etmek için:
    python -c "from utils.event_manager import test_event_manager; test_event_manager()"
    """
    print("🧪 Event Manager V7.1 📰🏦 Test Ediliyor...\n")
    print("Priority Sistemi: DÜŞÜK SAYI = YÜKSEK ÖNCELİK\n")
    
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
    bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
    bayram_msg = get_cache(bayram_key)
    
    if bayram_msg:
        current_hour = datetime.now().hour
        status = "AKTİF ✅" if current_hour < 15 else "SÜRESİ SONA ERDİ ❌ (15:00+)"
        print(f"🏦 BAYRAM CACHE'İ: {status}")
        print(f"   {bayram_msg}")
    else:
        print("ℹ️ Bayram cache'i boş (Gemini henüz kontrol etmedi veya bayram yok)")
    print("=" * 60)
    print()
    
    print("=" * 60)
    print("🧪 get_daily_notification_content() TEST EDİLİYOR...")
    print("   (14:00'da gönderilecek bildirim içeriği)")
    print("=" * 60)
    try:
        notification = get_daily_notification_content()
        if notification:
            print(f"✅ Bildirim Hazır:")
            print(f"   Başlık: {notification['title']}")
            print(f"   İçerik: {notification['body'][:100]}...")
            print(f"   Tür: {notification['type']}")
        else:
            print("⚠️ Bildirim yok (Ne bayram ne haber var)")
    except Exception as e:
        print(f"❌ Hata: {e}")
        import traceback
        print(traceback.format_exc())
    print("=" * 60)


if __name__ == "__main__":
    test_event_manager()
