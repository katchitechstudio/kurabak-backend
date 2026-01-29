"""
Event Manager - AKILLI TAKVİM SİSTEMİ V5.1 🗓️🤖📰
======================================
✅ BAYRAMLAR: Otomatik algılama (holidays kütüphanesi)
✅ TCMB & RAPORLAR: JSON dosyasından okuma
✅ PİYASA DURUMU: Hafta sonu/Tatil kontrolü
✅ ÖNCELİK SİSTEMİ: Manuel > TCMB > Haber > Bayram > Piyasa
✅ TAKVİM BİLDİRİMLERİ: Etkinlik günü Telegram'a mesaj gönder
✅ PRIORITY SYSTEM: Event önceliklendirme (90-40 arası)
✅ VALID_UNTIL: Zaman bazlı banner kontrolü
✅ TEK BANNER KURALI: Sadece en yüksek priority gösterilir
✅ 🤖 GEMINI AI: Event geçince otomatik sonuç çekme
✅ 📰 GÜNLÜK HABERLER: Sabah + Akşam vardiyası entegrasyonu (Priority: 75)
✅ 🏦 BAYRAM SAATİ: Bayramlar 12:00'a kadar gösterilir, sonra haberler devreye girer
"""

import json
import os
import logging
from datetime import datetime, date, time as dt_time
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# ======================================
# 🤖 GEMINI AI ENTEGRASYONU
# ======================================

def get_gemini_result(event_query: str, cache_key: str) -> Optional[str]:
    """
    Gemini AI'dan event sonucunu çeker.
    
    Args:
        event_query: Gemini'ye sorulacak soru
        cache_key: Redis cache anahtarı
        
    Returns:
        str: AI sonucu (örn: "TCMB faizi %47.5'te sabit tuttu")
        None: Hata durumunda
    """
    try:
        # Cache kontrolü
        from utils.cache import get_cache, set_cache
        cached_result = get_cache(cache_key)
        if cached_result:
            logger.info(f"🤖 [GEMINI] Cache'den alındı: {cache_key}")
            return cached_result
        
        # Gemini API
        import google.generativeai as genai
        
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.warning("⚠️ GEMINI_API_KEY bulunamadı!")
            return None
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        {event_query}
        
        Lütfen sadece sonucu tek cümlede özetle. Açıklama yapma.
        Örnek formatlar:
        - "TCMB faizi %47.5'te sabit tuttu"
        - "Enflasyon %64.77'ye yükseldi"
        - "TCMB politika faizini 200 baz puan düşürdü"
        
        Sadece özet sonucu yaz, başka bir şey ekleme.
        """
        
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        # Cache'e kaydet (24 saat)
        set_cache(cache_key, result, expire=86400)
        
        logger.info(f"🤖 [GEMINI] Yeni sonuç alındı: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Gemini API hatası: {e}")
        return None

# ======================================
# BAYRAM SİSTEMİ (OTOMATIK)
# ======================================

def get_holidays():
    """
    Türkiye bayramlarını döndürür.
    holidays kütüphanesi yoksa boş dict döner (Sistem patlamaz)
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
# EVENTS.JSON OKUYUCU
# ======================================

def load_events_json():
    """
    events.json dosyasını okur.
    
    YENİ FORMAT (V4.5):
    {
      "2026-01-22": {
        "message": "⚠️ Bugün TCMB faiz kararı günü",
        "type": "macro",
        "priority": 90,
        "valid_until": "15:00",
        "query_after": "TCMB faiz kararı Ocak 2026 sonucu nedir?"
      }
    }
    
    ESKİ FORMAT (String) de desteklenir (geriye uyumluluk)
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, "events.json")
        
        if not os.path.exists(json_path):
            logger.warning(f"⚠️ events.json bulunamadı: {json_path}")
            return {}
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
            # Format dönüşümü: Eski string formatı yeni object formatına çevir
            normalized = {}
            for event_date, event_data in data.items():
                if isinstance(event_data, str):
                    # ESKİ FORMAT (geriye uyumluluk)
                    normalized[event_date] = {
                        "message": event_data,
                        "type": "legacy",
                        "priority": 80,
                        "valid_until": "23:59"
                    }
                else:
                    # YENİ FORMAT
                    normalized[event_date] = event_data
            
            return normalized
            
    except Exception as e:
        logger.error(f"❌ events.json okuma hatası: {e}")
        return {}

# ======================================
# ENFLASYON TARİHİ KONTROLÜ
# ======================================

def is_inflation_day(date_obj: date) -> bool:
    """
    TÜİK Enflasyon verisi her ayın 3'ünde açıklanır.
    Eğer 3'ü hafta sonuna denk gelirse ilk iş günü açıklanır.
    """
    if date_obj.day == 3 and date_obj.weekday() < 5:
        return True
    
    if date_obj.day == 4 and date_obj.weekday() == 0:
        prev_day = date_obj.replace(day=3)
        if prev_day.weekday() == 6:
            return True
    
    if date_obj.day == 5 and date_obj.weekday() == 0:
        prev_day = date_obj.replace(day=3)
        if prev_day.weekday() == 5:
            return True
    
    return False

# ======================================
# VALID_UNTIL KONTROLÜ
# ======================================

def is_valid_at_time(valid_until: str, current_time: datetime) -> bool:
    """
    Banner'ın hala gösterilip gösterilmeyeceğini kontrol eder.
    
    Args:
        valid_until: "15:00" formatında saat
        current_time: Şu anki zaman
        
    Returns:
        True: Banner gösterilmeli
        False: Banner süresi doldu
    """
    try:
        # valid_until formatı: "HH:MM"
        hour, minute = map(int, valid_until.split(':'))
        valid_time = dt_time(hour, minute)
        current_time_only = current_time.time()
        
        # Şu anki saat valid_until'den önce mi?
        return current_time_only < valid_time
        
    except Exception as e:
        logger.warning(f"⚠️ valid_until parse hatası ({valid_until}): {e}")
        return True  # Hata durumunda göster (güvenli taraf)

# ======================================
# 🆕 BUGÜNÜN ETKİNLİKLERİNİ GETIR
# ======================================

def get_todays_events() -> List[Dict[str, any]]:
    """
    Bugünün tüm etkinliklerini priority sırasına göre döndürür.
    
    🤖 YENİ: Event süresi geçmişse Gemini'den sonuç çeker!
    📰 YENİ: Günlük haber sistemi entegrasyonu (Priority: 75)
    🏦 YENİ: Bayramlar 12:00'a kadar gösterilir, sonra haberler devreye girer
    
    Returns:
        List[Dict]: [
            {
                "type": "macro" | "bayram" | "inflation" | "news",
                "message": "...",
                "priority": 90,
                "valid_until": "15:00",
                "date": "2026-01-22"
            }
        ]
    """
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    current_time = datetime.now()
    events = []
    
    # 1. JSON'daki Özel Olaylar (TCMB, Raporlar)
    json_events = load_events_json()
    if today_str in json_events:
        event_data = json_events[today_str]
        
        # Saat kontrolü: valid_until geçti mi?
        time_expired = not is_valid_at_time(event_data['valid_until'], current_time)
        
        if time_expired and 'query_after' in event_data:
            # 🤖 GEMINI MODU: Event geçmiş, AI'dan sonuç çek
            cache_key = f"gemini_result:{today_str}"
            ai_result = get_gemini_result(event_data['query_after'], cache_key)
            
            if ai_result:
                # AI sonucunu göster
                events.append({
                    "type": "ai_result",
                    "message": f"🔴 {ai_result}",
                    "priority": event_data['priority'] + 5,  # AI sonucu +5 priority
                    "valid_until": "23:59",
                    "date": today_str
                })
            else:
                # AI başarısız, fallback mesaj
                fallback_msg = event_data['message'].replace("⚠️ Bugün", "✅").replace("günü", "açıklandı")
                events.append({
                    "type": event_data['type'],
                    "message": fallback_msg,
                    "priority": event_data['priority'],
                    "valid_until": "23:59",
                    "date": today_str
                })
        
        elif not time_expired:
            # Henüz event zamanı geçmedi, normal mesajı göster
            events.append({
                "type": event_data['type'],
                "message": event_data['message'],
                "priority": event_data['priority'],
                "valid_until": event_data['valid_until'],
                "date": today_str
            })
    
    # 2. 🏦 Bayramlar (Priority: 40) → ÖĞLENE KADAR (12:00)
    tr_holidays = get_holidays()
    if tr_holidays and today in tr_holidays:
        holiday_name = tr_holidays.get(today)
        
        # 🆕 BAYRAM SAATİ: Saat 12:00'dan önce mi?
        if current_time.hour < 12:
            events.append({
                "type": "bayram",
                "message": f"🏦 Resmî tatil: {holiday_name}",
                "priority": 40,
                "valid_until": "12:00",  # ← ÖĞLENE KADAR!
                "date": today_str
            })
            logger.info(f"🏦 [BAYRAM] {holiday_name} - 12:00'a kadar gösterilecek")
        else:
            logger.info(f"🏦 [BAYRAM] {holiday_name} süresi doldu (12:00+), haberler devrede")
    
    # 3. Enflasyon Günü (Priority: 85)
    if is_inflation_day(today):
        if current_time.hour < 11:  # 11:00'a kadar göster
            events.append({
                "type": "inflation",
                "message": "📉 Bugün enflasyon verisi açıklanacak",
                "priority": 85,
                "valid_until": "11:00",
                "date": today_str
            })
    
    # 4. 📰 GÜNLÜK HABERLER (Priority: 75)
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
            logger.debug(f"📰 [EVENT] Haber banner'ı eklendi: {news_banner[:50]}...")
    except Exception as e:
        logger.warning(f"⚠️ [EVENT] Haber banner'ı eklenemedi (önemsiz): {e}")
    
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
    2. Makro Eventler (TCMB Faiz: 90, Enflasyon: 85-90)
    3. 🤖 AI Sonuçları (Priority +5 boost = 95)
    4. 📰 Günlük Haberler (Priority: 75)
    5. 🏦 Bayramlar (40, sadece 00:00-12:00 arası) ← YENİ!
    6. Piyasa Kapalı (Hafta sonu - 30)
    7. Hiçbiri yoksa -> None
    
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
# 🆕 TAKVİM KONTROLÜ (SCHEDULER İÇİN)
# ======================================

def check_and_notify_events():
    """
    Bu fonksiyon Scheduler tarafından her gün sabah 08:00'da çağrılır.
    Bugünün etkinliklerini kontrol eder ve Telegram'a bildirim gönderir.
    """
    from utils.cache import get_cache, set_cache
    from config import Config
    
    try:
        events = get_todays_events()
        
        if not events:
            logger.info("📅 [TAKVİM] Bugün özel bir etkinlik yok.")
            return
        
        # Telegram bildirimi gönder
        from utils.telegram_monitor import get_telegram_monitor
        telegram = get_telegram_monitor()
        
        if telegram:
            # Sadece en yüksek priority'li eventi bildir
            top_event = events[0]
            
            telegram.send_calendar_notification(
                event_name=top_event['message'],
                event_date=top_event['date']
            )
            
            logger.info(
                f"📅 [TAKVİM] Bildirim gönderildi: {top_event['message']} "
                f"(Priority: {top_event['priority']})"
            )
        
    except Exception as e:
        logger.error(f"❌ Takvim kontrolü hatası: {e}")

# ======================================
# TEST FONKSİYONU
# ======================================

def test_event_manager():
    """
    Terminal'den test etmek için:
    python -c "from utils.event_manager import test_event_manager; test_event_manager()"
    """
    print("🧪 Event Manager V5.1 🤖📰🏦 Test Ediliyor...\n")
    
    # Bugünün banner'ı
    banner = get_todays_banner()
    if banner:
        print(f"✅ BUGÜNÜN BANNER'I:\n{banner}\n")
    else:
        print("ℹ️ Bugün özel bir mesaj yok.\n")
    
    # Bugünün etkinlikleri (Priority sıralı)
    events = get_todays_events()
    if events:
        print("📅 BUGÜNÜN ETKİNLİKLERİ (Priority sıralı):")
        for evt in events:
            print(
                f"  • [{evt['type']}] Priority: {evt['priority']} | "
                f"Valid: {evt['valid_until']} | {evt['message']}"
            )
        print()
    
    # Bayram listesi
    tr_holidays = get_holidays()
    if tr_holidays:
        print("📅 2026 BAYRAMLARI:")
        for hol_date, hol_name in sorted(tr_holidays.items()):
            if hol_date.year == 2026:
                print(f"  • {hol_date.strftime('%d.%m.%Y')}: {hol_name}")
    
    # JSON olayları
    json_events = load_events_json()
    if json_events:
        print("\n📊 2026 FİNANS TAKVİMİ:")
        for evt_date, evt_data in sorted(json_events.items()):
            if isinstance(evt_data, dict):
                msg = f"  • {evt_date}: {evt_data['message']} (P:{evt_data['priority']}, Until:{evt_data['valid_until']})"
                if 'query_after' in evt_data:
                    msg += " 🤖 [AI]"
                print(msg)
            else:
                print(f"  • {evt_date}: {evt_data}")

if __name__ == "__main__":
    test_event_manager()
