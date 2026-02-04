"""
Event Manager - AKILLI TAKVİM SİSTEMİ V6.1 🗓️📰🏦
======================================
✅ BAYRAMLAR: Gemini otomatik tespit (her vardiya hazırlığında)
✅ HABERLER: GNews + NewsData + Gemini özet
✅ ÖNCELİK SİSTEMİ: Bayram (15:00'a kadar) > Haberler
✅ TEK BANNER KURALI: Sadece en yüksek priority gösterilir
✅ BASIT VE ETKİLİ: Gereksiz karmaşıklık yok
✅ CLEAN IMPORTS: Import'lar üstte (V6.1)
✅ CHECK_AND_NOTIFY: Eksik fonksiyon eklendi (V6.1)

Priority Değerleri (Düşük sayı = Yüksek öncelik):
- 10: Bayram/Tatil
- 30: Piyasa Kapalı
- 75: Günlük Haberler
"""

import logging
from datetime import datetime, date
from typing import Optional, List, Dict

# 🔥 V6.1: IMPORT'LARI ÜSTE TAŞINDI (Fonksiyon içi import kaldırıldı)
from utils.cache import get_cache
from config import Config

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
                "priority": 10 | 75,  # Düşük = Yüksek öncelik
                "date": "2026-01-30"
            }
        ]
    """
    today_str = date.today().strftime("%Y-%m-%d")
    current_time = datetime.now()
    events = []
    
    # 1. 🏦 BAYRAM KONTROLÜ (Gemini'den - Redis cache)
    try:
        bayram_key = Config.CACHE_KEYS.get('daily_bayram', 'daily:bayram')
        bayram_msg = get_cache(bayram_key)
        
        # Bayram varsa VE saat 15:00'dan önceyse göster
        if bayram_msg and current_time.hour < 15:
            events.append({
                "type": "bayram",
                "message": bayram_msg,
                "priority": 10,  # EN YÜKSEK ÖNCELİK
                "valid_until": "15:00",
                "date": today_str
            })
            logger.info(f"🏦 [BAYRAM] {bayram_msg} - 15:00'a kadar gösterilecek (Priority: 10)")
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
                "priority": 75,  # NORMAL ÖNCELİK
                "valid_until": "23:59",
                "date": today_str
            })
            logger.debug(f"📰 [HABER] Banner eklendi (Priority: 75)")
    except Exception as e:
        logger.warning(f"⚠️ [HABER] Banner eklenemedi (önemsiz): {e}")
    
    # Priority'ye göre sırala (DÜŞÜKTEN YÜKSEĞE - düşük sayı = yüksek öncelik)
    events.sort(key=lambda x: x['priority'])
    
    return events


# ======================================
# ANA FONKSİYON: BUGÜNÜN BANNER'I
# ======================================

def get_todays_banner() -> Optional[str]:
    """
    🔥 TEK BANNER KURALI: Sadece en yüksek priority'li banner gösterilir!
    
    ÖNCELİK SIRASI (Düşük sayı = Yüksek öncelik):
    1. Manuel Duyuru (Redis'ten - bu fonksiyon bilmez)
    2. 🏦 Bayram (Priority: 10, sadece 00:00-15:00 arası)
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
        # En yüksek priority'li event (Liste başı = en düşük sayı = en yüksek öncelik)
        top_event = events[0]
        logger.info(
            f"📅 [BANNER] {top_event['type'].upper()} (Priority: {top_event['priority']}): "
            f"{top_event['message'][:60]}..."
        )
        return top_event['message']
    
    # --- 2. PİYASA KAPALI MI? (Hafta Sonu - Priority: 30) ---
    # Cumartesi (5) - Pazar (6) tüm gün kapalı
    if weekday == 5 or weekday == 6:
        logger.info("📅 [BANNER] Piyasa kapalı (Hafta sonu)")
        return "Piyasalar kapalı, iyi hafta sonları! 🌙"
    
    # Cuma akşam 18:00 sonrası
    if weekday == 4 and current_time.hour >= 18:
        logger.info("📅 [BANNER] Piyasa kapalı (Cuma akşam)")
        return "Piyasalar kapandı, iyi hafta sonları! 🌙"
    
    # --- 3. HİÇBİR ŞEY YOK ---
    logger.info("📅 [BANNER] Bugün özel banner yok")
    return None


# ======================================
# 🔥 V6.1: EKSİK FONKSİYON EKLENDİ
# ======================================

def check_and_notify_events():
    """
    🔥 V6.1 YENİ: Bugünün etkinliklerini kontrol et ve Telegram'a bildir
    
    Bu fonksiyon maintenance_service.py içindeki calendar_check() 
    tarafından her gün sabah 08:00'da çağrılır.
    
    Görevleri:
    1. Bugünün etkinliklerini al
    2. Varsa Telegram'a bildir
    3. Log tut
    """
    try:
        logger.info("🗓️ [CALENDAR CHECK] Bugünün etkinlikleri kontrol ediliyor...")
        
        # Bugünün etkinliklerini al
        events = get_todays_events()
        
        if not events:
            logger.info("ℹ️ [CALENDAR CHECK] Bugün özel bir etkinlik yok")
            return
        
        # Etkinlik varsa Telegram'a bildir
        try:
            from utils.telegram_monitor import get_telegram_monitor
            
            telegram = get_telegram_monitor()
            if not telegram:
                logger.warning("⚠️ [CALENDAR CHECK] Telegram bot bulunamadı")
                return
            
            # Mesaj hazırla
            today_str = date.today().strftime("%d.%m.%Y")
            message_parts = [
                f"📅 *BUGÜNÜN ETKİNLİKLERİ* ({today_str})\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
            ]
            
            for i, event in enumerate(events, 1):
                event_type = event['type'].upper()
                priority = event['priority']
                event_msg = event['message']
                valid_until = event.get('valid_until', '23:59')
                
                # Emoji seç
                if event_type == 'BAYRAM':
                    emoji = "🏦"
                elif event_type == 'NEWS':
                    emoji = "📰"
                else:
                    emoji = "ℹ️"
                
                message_parts.append(
                    f"{i}. {emoji} *{event_type}* (Priority: {priority})\n"
                    f"   {event_msg}\n"
                    f"   Geçerlilik: {valid_until}'e kadar\n"
                )
            
            message = "\n".join(message_parts)
            
            # Telegram'a gönder
            telegram.send_message(message, level='report')
            logger.info(f"✅ [CALENDAR CHECK] {len(events)} etkinlik Telegram'a bildirildi")
            
        except Exception as telegram_err:
            logger.error(f"❌ [CALENDAR CHECK] Telegram bildirimi hatası: {telegram_err}")
        
    except Exception as e:
        logger.error(f"❌ [CALENDAR CHECK] Genel hata: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")


# ======================================
# TEST FONKSİYONU
# ======================================

def test_event_manager():
    """
    Terminal'den test etmek için:
    python -c "from utils.event_manager import test_event_manager; test_event_manager()"
    """
    print("🧪 Event Manager V6.1 📰🏦 Test Ediliyor...\n")
    print("Priority Sistemi: DÜŞÜK SAYI = YÜKSEK ÖNCELİK\n")
    
    # Bugünün banner'ı
    print("=" * 60)
    banner = get_todays_banner()
    if banner:
        print(f"✅ BUGÜNÜN BANNER'I:\n{banner}\n")
    else:
        print("ℹ️ Bugün özel bir mesaj yok.\n")
    print("=" * 60)
    print()
    
    # Bugünün etkinlikleri
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
    
    # Bayram kontrolü
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
    
    # 🔥 V6.1: Yeni test - check_and_notify_events
    print()
    print("=" * 60)
    print("🧪 check_and_notify_events() TEST EDİLİYOR...")
    print("=" * 60)
    try:
        check_and_notify_events()
        print("✅ Fonksiyon başarıyla çalıştı (Logları kontrol et)")
    except Exception as e:
        print(f"❌ Hata: {e}")
    print("=" * 60)


if __name__ == "__main__":
    test_event_manager()
