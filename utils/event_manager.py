"""
Event Manager - AKILLI TAKVİM SİSTEMİ V2.0 🗓️
======================================
✅ BAYRAMLAR: Otomatik algılama (holidays kütüphanesi)
✅ TCMB & RAPORLAR: JSON dosyasından okuma
✅ PİYASA DURUMU: Hafta sonu/Tatil kontrolü
✅ ÖNCELİK SİSTEMİ: Manuel > TCMB > Bayram > Piyasa
✅ 🆕 TAKVİM BİLDİRİMLERİ: Etkinlik günü Telegram'a mesaj gönder
"""

import json
import os
import logging
from datetime import datetime, date
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
    Dosya bulunamazsa boş dict döner (Sistem patlamaz)
    """
    try:
        # events.json bu dosyayla aynı klasörde (utils/)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, "events.json")
        
        if not os.path.exists(json_path):
            logger.warning(f"⚠️ events.json bulunamadı: {json_path}")
            return {}
        
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
            
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
    # Ayın 3'ü ve hafta içi mi?
    if date_obj.day == 3 and date_obj.weekday() < 5:
        return True
    
    # Ayın 3'ü Pazar idiyse Pazartesi (4'ü)
    if date_obj.day == 4 and date_obj.weekday() == 0:
        prev_day = date_obj.replace(day=3)
        if prev_day.weekday() == 6:  # Pazar
            return True
    
    # Ayın 3'ü Cumartesi idiyse Pazartesi (5'i)
    if date_obj.day == 5 and date_obj.weekday() == 0:
        prev_day = date_obj.replace(day=3)
        if prev_day.weekday() == 5:  # Cumartesi
            return True
    
    return False

# ======================================
# 🆕 BUGÜNÜN ETKİNLİKLERİNİ GETIR
# ======================================

def get_todays_events() -> List[Dict[str, str]]:
    """
    Bugünün tüm etkinliklerini liste olarak döndürür.
    Her etkinlik: {"type": "tcmb"|"bayram"|"inflation", "message": "..."}
    
    Bu fonksiyon Telegram bildirim sistemi için kullanılır.
    """
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    events = []
    
    # 1. JSON'daki Özel Olaylar (TCMB, Raporlar)
    json_events = load_events_json()
    if today_str in json_events:
        events.append({
            "type": "tcmb",
            "message": json_events[today_str],
            "date": today_str
        })
    
    # 2. Bayramlar
    tr_holidays = get_holidays()
    if tr_holidays and today in tr_holidays:
        holiday_name = tr_holidays.get(today)
        # 🔥 EMOJİ SONDA
        events.append({
            "type": "bayram",
            "message": f"{holiday_name} Kutlu Olsun! 🎉",
            "date": today_str
        })
    
    # 3. Enflasyon Günü
    if is_inflation_day(today):
        # 🔥 📢 EMOJİSİ KALDIRILDI
        events.append({
            "type": "inflation",
            "message": "Bugün saat 10:00'da Enflasyon Verisi (TÜFE) açıklanacak!",
            "date": today_str
        })
    
    return events

# ======================================
# ANA FONKSİYON: BUGÜNÜN BANNER'I
# ======================================

def get_todays_banner() -> Optional[str]:
    """
    ÖNCELİK SIRASI:
    1. Manuel Duyuru (Telegram'dan /duyuru ile yazılan) -> Redis'ten okunur, bu fonksiyon bilmez
    2. JSON'daki Özel Olaylar (TCMB, Enflasyon Raporları)
    3. Bayramlar (Otomatik)
    4. Enflasyon Günü Kontrolü (Ayın 3'ü)
    5. Piyasa Kapalı mı? (Hafta sonu)
    6. Hiçbiri yoksa -> None
    
    NOT: Bu fonksiyon sadece OTOMATIK mesajları döndürür.
    Manuel duyuru kontrolü financial_service.py'de yapılır.
    """
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    current_hour = datetime.now().hour
    weekday = today.weekday()  # 0=Pzt, 4=Cuma, 5=Cmt, 6=Paz
    
    # --- 1. JSON'DAKİ ÖZEL OLAYLAR (TCMB, Raporlar) ---
    events = load_events_json()
    if today_str in events:
        logger.info(f"📅 [EVENT] Bugün özel gün: {events[today_str]}")
        return events[today_str]
    
    # --- 2. BAYRAM KONTROLÜ ---
    tr_holidays = get_holidays()
    if tr_holidays and today in tr_holidays:
        holiday_name = tr_holidays.get(today)
        # 🔥 EMOJİ SONDA
        msg = f"{holiday_name} Kutlu Olsun! 🎉"
        logger.info(f"📅 [BAYRAM] {msg}")
        return msg
    
    # --- 3. ENFLASYON GÜNÜ ---
    if is_inflation_day(today):
        # 🔥 📢 EMOJİSİ KALDIRILDI
        msg = "Bugün saat 10:00'da Enflasyon Verisi (TÜFE) açıklanacak!"
        logger.info(f"📅 [ENFLASYON] {msg}")
        return msg
    
    # --- 4. PİYASA KAPALI MI? (Hafta Sonu) ---
    # Cumartesi (5) - Pazar (6) tüm gün kapalı
    if weekday == 5 or weekday == 6:
        # 🔥 TAM MESAJ + EMOJİ SONDA
        return "Piyasalar kapalı, iyi hafta sonları! 🌙"
    
    # Cuma akşam 18:00 sonrası
    if weekday == 4 and current_hour >= 18:
        # 🔥 TAM MESAJ + EMOJİ SONDA
        return "Piyasalar kapandı, iyi hafta sonları! 🌙"
    
    # --- 5. HİÇBİR ŞEY YOK ---
    return None

# ======================================
# 🆕 TAKVİM KONTROLÜ (SCHEDULER İÇİN)
# ======================================

def check_and_notify_events():
    """
    Bu fonksiyon Scheduler tarafından her gün sabah 08:00'da çağrılır.
    Bugünün etkinliklerini kontrol eder ve:
    1. Telegram'a bildirim gönderir
    2. Saat 09:00'da banner'ı otomatik aktif eder
    """
    from utils.cache import get_cache, set_cache
    from config import Config
    
    try:
        # Bugünün etkinliklerini al
        events = get_todays_events()
        
        if not events:
            logger.info("📅 [TAKVİM] Bugün özel bir etkinlik yok.")
            return
        
        # Telegram bildirimi gönder
        from utils.telegram_monitor import get_telegram_monitor
        telegram = get_telegram_monitor()
        
        if telegram:
            for event in events:
                event_msg = event['message']
                event_date = event['date']
                
                # Bildirim gönder
                telegram.send_calendar_notification(
                    event_name=event_msg,
                    event_date=event_date
                )
                
                logger.info(f"📅 [TAKVİM] Bildirim gönderildi: {event_msg}")
        
        # Banner'ı otomatik aktif et (09:00'da aktif olacak şekilde kaydet)
        # NOT: Banner'ın kendisi get_todays_banner() ile alınacak
        # Burada sadece bildirim sistemini tetikliyoruz
        
    except Exception as e:
        logger.error(f"❌ Takvim kontrolü hatası: {e}")

# ======================================
# TEST FONKSİYONU (Opsiyonel)
# ======================================

def test_event_manager():
    """
    Terminal'den test etmek için:
    python -c "from utils.event_manager import test_event_manager; test_event_manager()"
    """
    print("🧪 Event Manager Test Ediliyor...\n")
    
    # Bugünün banner'ı
    banner = get_todays_banner()
    if banner:
        print(f"✅ BUGÜNÜN BANNER'I:\n{banner}\n")
    else:
        print("ℹ️ Bugün özel bir mesaj yok.\n")
    
    # Bugünün etkinlikleri
    events = get_todays_events()
    if events:
        print("📅 BUGÜNÜN ETKİNLİKLERİ:")
        for evt in events:
            print(f"  • [{evt['type']}] {evt['message']}")
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
        for evt_date, evt_msg in sorted(json_events.items()):
            print(f"  • {evt_date}: {evt_msg}")

if __name__ == "__main__":
    test_event_manager()
