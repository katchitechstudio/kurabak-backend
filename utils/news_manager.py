Event Manager - AKILLI TAKVİM SİSTEMİ V6.0 🗓️📰🏦
======================================
✅ BAYRAMLAR: Gemini otomatik tespit (her vardiya hazırlığında)
✅ HABERLER: GNews + NewsData + Gemini özet
✅ ÖNCELİK SİSTEMİ: Bayram (15:00'a kadar) > Haberler
✅ TEK BANNER KURALI: Sadece en yüksek priority gösterilir
✅ BASIT VE ETKİLİ: Gereksiz karmaşıklık yok
"""

import logging
from datetime import datetime, date
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# ======================================
# 🆕 BUGÜNÜN ETKİNLİKLERİNİ GETIR
# ======================================

def get_todays_events() -> List[Dict[str, any]]:
    """
    Bugünün tüm etkinliklerini priority sırasına göre döndürür.
    
    🏦 BAYRAM: Gemini'den alınır (news_manager tarafından Redis'e kaydedilir)
    📰 HABERLER: GNews + NewsData + Gemini özet
    
    Returns:
        List[Dict]: [
            {
                "type": "bayram" | "news",
                "message": "...",
                "priority": 40 | 75,
                "date": "2026-01-29"
            }
        ]
    """
    today_str = date.today().strftime("%Y-%m-%d")
    current_time = datetime.now()
    events = []
    
    # 1. 🏦 BAYRAM KONTROLÜ (Gemini'den - Redis cache)
    try:
        from utils.cache import get_cache
        from config import Config
        
        bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
        bayram_msg = get_cache(bayram_key)
        
        # Bayram varsa VE saat 15:00'dan önceyse göster
        if bayram_msg and current_time.hour < 15:
            events.append({
                "type": "bayram",
                "message": bayram_msg,
                "priority": 40,
                "valid_until": "15:00",
                "date": today_str
            })
            logger.info(f"🏦 [BAYRAM] {bayram_msg} - 15:00'a kadar gösterilecek")
        elif bayram_msg and current_time.hour >= 15:
            logger.info(f"🏦 [BAYRAM] Süresi doldu (15:00+), haberler devrede")
            
    except Exception as e:
        logger.warning(f"⚠️ [BAYRAM] Kontrol hatası (önemsiz): {e}")
    
    # 2. 📰 GÜNLÜK HABERLER (Priority: 75)
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
            logger.debug(f"📰 [HABER] Banner eklendi")
    except Exception as e:
        logger.warning(f"⚠️ [HABER] Banner eklenemedi (önemsiz): {e}")
    
    # Priority'ye göre sırala (Yüksekten düşüğe)
    events.sort(key=lambda x: x['priority'], reverse=True)
    
    return events

# ======================================
# ANA FONKSİYON: BUGÜNÜN BANNER'I
# ======================================

def get_todays_banner() -> Optional[str]:
    """
    🔥 TEK BANNER KURALI: Sadece en yüksek priority'li banner gösterilir!
    
    ÖNCELİK SIRASI:
    1. Manuel Duyuru (Redis'ten - bu fonksiyon bilmez)
    2. 🏦 Bayram (Priority: 40, sadece 00:00-15:00 arası)
    3. 📰 Günlük Haberler (Priority: 75)
    4. Piyasa Kapalı (Hafta sonu - Priority: 30)
    5. Hiçbiri yoksa -> None
    
    Returns:
        str: Banner mesajı
        None: Banner yok
    """
    today = date.today()
    current_time = datetime.now()
    weekday = today.weekday()  # 0=Pzt, 4=Cuma, 5=Cmt, 6=Paz
    
    # --- 1. BUGÜNÜN ETKİNLİKLERİNİ AL (Priority sıralı) ---
    events = get_todays_events()
    
    if events:
        # En yüksek priority'li event (Liste zaten sıralı)
        top_event = events[0]
        logger.info(
            f"📅 [BANNER] {top_event['type']} (Priority: {top_event['priority']}): "
            f"{top_event['message'][:60]}..."
        )
        return top_event['message']
    
    # --- 2. PİYASA KAPALI MI? (Hafta Sonu - Priority: 30) ---
    # Cumartesi (5) - Pazar (6) tüm gün kapalı
    if weekday == 5 or weekday == 6:
        return "Piyasalar kapalı, iyi hafta sonları! 🌙"
    
    # Cuma akşam 18:00 sonrası
    if weekday == 4 and current_time.hour >= 18:
        return "Piyasalar kapandı, iyi hafta sonları! 🌙"
    
    # --- 3. HİÇBİR ŞEY YOK ---
    return None

# ======================================
# TEST FONKSİYONU
# ======================================

def test_event_manager():
    """
    Terminal'den test etmek için:
    python -c "from utils.event_manager import test_event_manager; test_event_manager()"
    """
    print("🧪 Event Manager V6.0 📰🏦 Test Ediliyor...\n")
    
    # Bugünün banner'ı
    banner = get_todays_banner()
    if banner:
        print(f"✅ BUGÜNÜN BANNER'I:\n{banner}\n")
    else:
        print("ℹ️ Bugün özel bir mesaj yok.\n")
    
    # Bugünün etkinlikleri
    events = get_todays_events()
    if events:
        print("📅 BUGÜNÜN ETKİNLİKLERİ (Priority sıralı):")
        for evt in events:
            print(
                f"  • [{evt['type']}] Priority: {evt['priority']} | "
                f"{evt['message']}"
            )
        print()
    else:
        print("ℹ️ Bugün etkinlik yok\n")
    
    # Bayram kontrolü
    from utils.cache import get_cache
    from config import Config
    
    bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
    bayram_msg = get_cache(bayram_key)
    
    if bayram_msg:
        print(f"🏦 BAYRAM CACHE'İ:\n{bayram_msg}\n")
    else:
        print("ℹ️ Bayram cache'i boş (Gemini henüz kontrol etmedi)\n")

if __name__ == "__main__":
    test_event_manager()
