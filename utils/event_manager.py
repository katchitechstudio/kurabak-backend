"""
Event Manager - AKILLI TAKVİM SİSTEMİ V6.0 🗓️🤖📰
======================================
✅ BAYRAMLAR: Otomatik (holidays kütüphanesi)
✅ EKONOMİK EVENTLER: Günde 1 Gemini sorgusu (sabah 06:00)
✅ HABERLER: GNews + NewsData (sürekli güncelleniyor)
✅ HİBRİT SİSTEM: Sabit günler (kütüphane) + Dinamik günler (Gemini)
"""

import json
import os
import logging
from datetime import datetime, date, time as dt_time
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# ======================================
# BAYRAM SİSTEMİ (OTOMATIK)
# ======================================

def get_holidays():
    """
    Türkiye bayramlarını döndürür.
    
    Otomatik gelenler:
    - Yılbaşı (1 Ocak)
    - Ramazan Bayramı (3 gün)
    - Kurban Bayramı (4 gün)
    - 23 Nisan
    - 19 Mayıs
    - 15 Temmuz (Demokrasi Bayramı)
    - 30 Ağustos
    - 29 Ekim
    """
    try:
        import holidays
        return holidays.Turkey(years=range(2025, 2030))
    except ImportError:
        logger.warning("⚠️ 'holidays' kütüphanesi yok! Bayramlar devre dışı.")
        return {}
    except Exception as e:
        logger.error(f"❌ Holidays hatası: {e}")
        return {}

# ======================================
# 🤖 GÜNLÜK EKONOMİK EVENT KONTROLÜ
# ======================================

def get_todays_important_events() -> Optional[str]:
    """
    🤖 GÜNLÜK AKILLI KONTROL (Sabah 06:00'da 1 kez çalışır)
    
    Gemini'ye sorar:
    "Bugün Türkiye'de önemli ekonomik açıklama var mı?"
    
    Returns:
        str: Varsa event mesajı
        None: Yoksa None
    """
    try:
        from utils.cache import get_cache, set_cache
        import google.generativeai as genai
        
        today_str = date.today().strftime("%Y-%m-%d")
        cache_key = f"daily_event:{today_str}"
        
        # Cache kontrolü (Günde 1 kez soruyor)
        cached_event = get_cache(cache_key)
        if cached_event is not None:
            if cached_event == "YOK":
                return None
            logger.info(f"🤖 [EVENT] Cache'den alındı: {cached_event}")
            return cached_event
        
        # Gemini'ye sor
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı!")
            return None
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Bugünün tarihini insan okunabilir formata çevir
        today_obj = date.today()
        today_readable = today_obj.strftime("%d %B %Y")  # Örn: 29 Ocak 2026
        
        prompt = f"""
Bugün {today_readable} ({today_str}) tarihinde Türkiye'de önemli ekonomik açıklamalar var mı?

Kontrol edilecekler:
- TCMB faiz kararı (genelde ayın 3. perşembesi)
- TÜİK enflasyon verisi (her ayın 3'ü)
- TCMB finansal istikrar raporu (Mayıs/Kasım)
- Büyüme verileri (GSYİH - Her çeyrek)
- İşsizlik verileri (TÜİK)
- Cari açık verileri (TCMB)

EĞER VARSA:
- Tek cümlede yaz, max 60 karakter
- Emoji kullan (⚠️ TCMB, 📈 TÜİK, 📊 veri)
- Saat belirt (örn: "14:00'te")
- Örnek: "⚠️ TCMB faiz kararı saat 14:00'te açıklanacak"
- Örnek: "📈 Enflasyon verisi saat 10:00'da açıklanacak"

EĞER YOKSA:
- Sadece "YOK" yaz

Başka açıklama ekleme, sadece sonucu yaz.

Cevap:
"""
        
        logger.info(f"🤖 [EVENT] Gemini'ye günlük event sorusu gönderiliyor...")
        
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        # "YOK" kontrolü
        if result.upper() == "YOK" or "YOK" in result.upper():
            logger.info(f"ℹ️ [EVENT] Bugün özel ekonomik event yok")
            set_cache(cache_key, "YOK", ttl=86400)  # 24 saat
            return None
        
        # Cache'e kaydet (24 saat)
        set_cache(cache_key, result, ttl=86400)
        
        logger.info(f"✅ [EVENT] Bugün event var: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ [EVENT] Günlük event kontrolü hatası: {e}")
        return None

# ======================================
# 🆕 BUGÜNÜN ETKİNLİKLERİNİ GETIR
# ======================================

def get_todays_events() -> List[Dict[str, any]]:
    """
    Bugünün tüm etkinliklerini priority sırasına göre döndürür.
    
    🤖 HİBRİT SİSTEM:
    - Bayramlar: holidays kütüphanesi (otomatik)
    - Ekonomik eventler: Gemini (günde 1 sorgu)
    - Haberler: GNews + NewsData (sürekli güncelleniyor)
    
    Returns:
        List[Dict]: Etkinlik listesi
    """
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    current_time = datetime.now()
    events = []
    
    # 1. 🤖 GÜNLÜK AKILLI EVENT KONTROLÜ (Priority: 85)
    smart_event = get_todays_important_events()
    if smart_event:
        events.append({
            "type": "smart_event",
            "message": smart_event,
            "priority": 85,  # Haberlerden yüksek
            "valid_until": "23:59",
            "date": today_str
        })
    
    # 2. 🏦 Bayramlar (Priority: 40) → ÖĞLENE KADAR (12:00)
    tr_holidays = get_holidays()
    if tr_holidays and today in tr_holidays:
        holiday_name = tr_holidays.get(today)
        
        if current_time.hour < 12:
            events.append({
                "type": "bayram",
                "message": f"🏦 Resmî tatil: {holiday_name}",
                "priority": 40,
                "valid_until": "12:00",
                "date": today_str
            })
            logger.info(f"🏦 [BAYRAM] {holiday_name} - 12:00'a kadar gösterilecek")
    
    # 3. 📰 GÜNLÜK HABERLER (Priority: 75)
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
    except Exception as e:
        logger.warning(f"⚠️ [EVENT] Haber banner'ı eklenemedi: {e}")
    
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
    2. 🤖 Günlük Akıllı Event (Gemini sorgusu - Priority: 85)
    3. 📰 Günlük Haberler (Priority: 75)
    4. 🏦 Bayramlar (Priority: 40, sadece 00:00-12:00 arası)
    5. Piyasa Kapalı (Hafta sonu - Priority: 30)
    6. Hiçbiri yoksa -> None
    
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
            f"{top_event['message']}"
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
    print("🧪 Event Manager V6.0 🤖📰🏦 Test Ediliyor...\n")
    
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
    
    # Bayram listesi
    tr_holidays = get_holidays()
    if tr_holidays:
        print("📅 2026 BAYRAMLARI:")
        for hol_date, hol_name in sorted(tr_holidays.items()):
            if hol_date.year == 2026:
                print(f"  • {hol_date.strftime('%d.%m.%Y')}: {hol_name}")
        print()
    
    # Günlük event kontrolü
    print("🤖 GÜNLÜK EVENT KONTROLÜ:")
    smart_event = get_todays_important_events()
    if smart_event:
        print(f"  ✅ Bugün özel event var: {smart_event}\n")
    else:
        print(f"  ℹ️ Bugün özel ekonomik event yok\n")

if __name__ == "__main__":
    test_event_manager()
