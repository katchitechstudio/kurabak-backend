"""
Event Manager - AKILLI TAKVİM SİSTEMİ V4.4 🗓️
======================================
✅ BAYRAMLAR: Otomatik algılama (holidays kütüphanesi)
✅ TCMB & RAPORLAR: JSON dosyasından okuma
✅ PİYASA DURUMU: Hafta sonu/Tatil kontrolü
✅ ÖNCELİK SİSTEMİ: Manuel > TCMB > Bayram > Piyasa
✅ TAKVİM BİLDİRİMLERİ: Etkinlik günü Telegram'a mesaj gönder
✅ PRIORITY SYSTEM: Event önceliklendirme (90-40 arası)
✅ VALID_UNTIL: Zaman bazlı banner kontrolü
✅ TEK BANNER KURALI: Sadece en yüksek priority gösterilir
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
    
    YENİ FORMAT:
    {
      "2026-01-22": {
        "message": "⚠️ Bugün TCMB faiz kararı günü",
        "type": "macro",
        "priority": 90,
        "valid_until": "15:00"
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
    
    Returns:
        List[Dict]: [
            {
                "type": "macro" | "bayram" | "inflation",
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
        
        # valid_until kontrolü
        if is_valid_at_time(event_data['valid_until'], current_time):
            events.append({
                "type": event_data['type'],
                "message": event_data['message'],
                "priority": event_data['priority'],
                "valid_until": event_data['valid_until'],
                "date": today_str
            })
    
    # 2. Bayramlar (Priority: 40)
    tr_holidays = get_holidays()
    if tr_holidays and today in tr_holidays:
        holiday_name = tr_holidays.get(today)
        events.append({
            "type": "bayram",
            "message": f"🏦 Resmî tatil: {holiday_name}",
            "priority": 40,
            "valid_until": "23:59",
            "date": today_str
        })
    
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
    3. Bayramlar (40)
    4. Piyasa Kapalı (Hafta sonu - 30)
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
    print("🧪 Event Manager V4.4 Test Ediliyor...\n")
    
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
                print(
                    f"  • {evt_date}: {evt_data['message']} "
                    f"(P:{evt_data['priority']}, Until:{evt_data['valid_until']})"
                )
            else:
                print(f"  • {evt_date}: {evt_data}")

if __name__ == "__main__":
    test_event_manager()
