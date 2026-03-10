"""
Configuration - PRODUCTION READY V5.6 🧠📰🏦💰🔥
=====================================================
✅ API V5: Tek kaynak (Primary & Only)
✅ BACKUP SYSTEM: 15 dakikalık yedek sistem
✅ TELEGRAM: Rapor ve bildirim sistemi
✅ TAKVİM BİLDİRİMLERİ: Günü gelen etkinlikler için otomatik uyarı
✅ BAKIM & SELF-HEALING ALARM SİSTEMİ
✅ FIREBASE PUSH NOTIFICATIONS: Android bildirimler
✅ FİYAT ALARM SİSTEMİ: Redis tabanlı kullanıcı alarmları
✅ SUMMARY SYNC FIX: Özet currencies içinde (Sterlin sorunu çözüldü!)
✅ AKILLI LOGLAMA: Piyasa kapalı spam önleme
✅ GELİŞMİŞ TRACKING: Header bazlı kullanıcı takibi
✅ TREND ANALİZİ: %5 eşiği ile güçlü trend tespiti
✅ CIRCUIT BREAKER: API hata yönetimi
✅ PUSH NOTIFICATION: Öğlen 14:00 günlük özet
✅ TEMİZLİK MEKANİZMASI: 7 günlük otomatik temizlik
✅ WORKER INTERVAL: 1 dakika (daha hızlı güncellemeler)
✅ 📰 GÜNLÜK HABER SİSTEMİ V3.0: Hazırlama + Yayınlama ayrı (23:55 + 11:55)
✅ 💰 MARKET MARGIN SYSTEM: Ham/Kuyumcu fiyat profilleri + İki Snapshot
✅ 🔥 DYNAMIC FULL MARGIN V5.6: TAM MARJ + Smooth Geçiş + HİBRİT SİSTEM
✅ 🔥 SMART SCHEDULER V5.5: CPU spike önleme (haberler 5 dakika önce hazırlanır)
✅ 🔥 STATIC GOLD MARGINS: Cumhuriyet Altını statik marj desteği

V5.6 Değişiklikler (HİBRİT MARJ SİSTEMİ):
- 🔥 ALTIN + GÜMÜŞ: Harem + Gemini (6 varlık - dinamik)
- 🔥 MAJÖR DÖVİZLER: Ziraat Bankası + Gemini (11 döviz - dinamik)
- 🔥 EXOTIC DÖVİZLER: Config sabit marjlar (12 döviz - statik)
- 🔥 ALTIN STATİK: Cumhuriyet Altını sabit marj (Harem'de yok)
- 🔥 TAM MARJ: Yarım değil, TAM marj kullanılıyor (kuyumcu gerçeği)
- 🔥 SMOOTH GEÇİŞ: Marj değişimi kademeli (3-4 gün), alarm patlaması önlenir
"""
import os

class Config:
    # ======================================
    # UYGULAMA AYARLARI
    # ======================================
    APP_NAME = "KuraBak Backend API"
    APP_VERSION = "5.6"  # 🔥 Hibrit Margin System (Harem + Ziraat + Config)
    ENVIRONMENT = os.environ.get("FLASK_ENV", "production")
    
    # Zaman Dilimi (Çok Önemli - Loglar, Snapshot ve Raporlar için)
    DEFAULT_TIMEZONE = "Europe/Istanbul"
    
    # ======================================
    # 🔥 API KAYNAK (V5 ONLY)
    # ======================================
    # V5 API (Tek ve Ana Kaynak)
    API_V5_URL = "https://finance.truncgil.com/api/today.json"
    API_V5_TIMEOUT = (5, 10)  # 5sn bağlanma, 10sn okuma
    
    # ======================================
    # 💰 MARKET MARGIN SYSTEM V5.6 (HİBRİT)
    # ======================================
    """
    FİYAT PROFİLLERİ:
    - raw: Ham fiyat (API'den direk gelen, borsa/toptan fiyatı)
    - jeweler: Kuyumcu/Fiziki piyasa fiyatı (DİNAMİK TAM MARJ eklenmiş)
    
    KULLANIM:
    - Kullanıcı ayarlardan "Ham Fiyat" veya "Kuyumcu Fiyatı" seçer
    - Backend her iki fiyat serisini de tutar (İKİ AYRI SNAPSHOT)
    - Yüzdelik değişimler kendi snapshot'larına göre hesaplanır
    
    HİBRİT MARJ SİSTEMİ V5.6:
    
    1. DİNAMİK MARJLAR (Gemini AI hesaplar):
       - ALTIN + GÜMÜŞ: Harem.com HTML parse (5 varlık - GRA, C22, YAR, TAM, ATA, AG)
       - MAJÖR DÖVİZLER: Ziraat Bankası HTML parse (11 döviz)
       Toplam: 16 varlık dinamik
    
    2. STATİK MARJLAR (Config'den):
       - ALTIN: Cumhuriyet Altını (Harem'de yok)
       - EXOTIC DÖVİZLER: Manuel tanımlı (12 döviz)
       Toplam: 13 varlık statik
    
    SMOOTH GEÇİŞ (sadece dinamik marjlar için):
    - Marj değişimi kademeli (3-4 gün)
      Örnek: %2 → %4 değişimi:
        Gün 1: %3 (ortalama)
        Gün 2: %3.5 (ortalama)
        Gün 3: %3.75 (ortalama)
        Gün 4: %4 (hedef)
    - Alarmlar patlamaz, kullanıcı şaşırmaz ✅
    
    İKİ SNAPSHOT SİSTEMİ V5.6:
    - raw_snapshot: Ham fiyatlar (00:00'da kaydedilir, asla değişmez)
    - jeweler_snapshot: Marjlı fiyatlar (00:00'da + marj değişiminde güncellenir)
    
    ZAMANLAMA (CPU Spike Önleme):
    - 23:55:00 → Sabah haberlerini hazırla (Gemini)
    - 00:00:00 → Snapshot kaydet (RAW + JEWELER) + Sabah haberlerini yayınla
    - 00:05:00 → Dinamik Marj Güncelle (Harem + Ziraat + Config exotic + gold merge)
    - 11:55:00 → Akşam haberlerini hazırla (Gemini)
    - 12:00:00 → Akşam haberlerini yayınla
    - 14:00:00 → Push notification gönder
    
    AKILLI FALLBACK SİSTEMİ V5.6:
    1. Redis (bugünkü Gemini marjları + exotic + gold) → EN GÜNCEL ✅
    2. margin_last_update (en son başarılı + exotic + gold) → SMOOTH FALLBACK ✅
    3. BOOTSTRAP (ilk kurulum + exotic + gold) → HEMEN GEMİNİ ÇAĞIR! ✅
    """
    
    PRICE_PROFILES = {
        # RAW PROFILE - Ham Fiyat (API'den gelen)
        "raw": {},  # Hiç marj yok, direkt API fiyatı
        
        # JEWELER PROFILE - Kuyumcu/Fiziki Piyasa Fiyatı (HİBRİT MARJ)
        # 🔥 V5.6: Dinamik (Harem + Ziraat) + Statik (Config exotic + gold)
        "jeweler": {}  # Gemini + Config dolduracak
    }
    
    # Varsayılan fiyat profili (uygulama ilk açıldığında)
    DEFAULT_PRICE_PROFILE = "jeweler"  # Kuyumcu fiyatı varsayılan
    
    # Profil tanımlanmamış varlıklar için varsayılan marj
    DEFAULT_MARKET_MARGIN = 0.0  # %0 (marj yok - ham fiyat gibi)
    
    # ======================================
    # 🔥 DİNAMİK MARJ SİSTEMİ AYARLARI V5.6
    # ======================================
    # Harem veri kaynağı (Altın + Gümüş için HTML parse)
    HAREM_PRICE_URL = "https://altin.doviz.com/harem"
    HAREM_FETCH_TIMEOUT = 10  # 10 saniye
    
    # 🔥 V5.6: Ziraat Bankası veri kaynağı (Majör dövizler için HTML parse)
    ZIRAAT_CURRENCY_URL = "https://kur.doviz.com/ziraat-bankasi"
    ZIRAAT_FETCH_TIMEOUT = 10  # 10 saniye
    
    # 🔥 Marj güncelleme saati (AYRI JOB - CPU spike önleme)
    MARGIN_UPDATE_HOUR = 0     # Gece 00:05 (snapshot'tan SONRA)
    MARGIN_UPDATE_MINUTE = 5   # 00:00:00 Snapshot → 00:05:00 Marj → Haberler zaten hazır
    
    # 🔥 V5.6: TAM MARJ + SMOOTH GEÇİŞ
    MARGIN_CALCULATION_STRATEGY = "full"  # "full" = Tam marj (kuyumcu gerçeği)
    MARGIN_SMOOTH_TRANSITION = True  # Kademeli geçiş aktif (sadece dinamik marjlar için)
    MARGIN_SMOOTH_THRESHOLD = 0.015  # %1.5'ten fazla fark varsa smooth geçiş yap
    
    # ======================================
    # 🔥 ALTIN MARJLARI (STATİK) V5.6
    # ======================================
    """
    Harem.com'da OLMAYAN altınlar için sabit marjlar.
    
    CUMHURİYET ALTINI SORUNU:
    - API'de var ama Harem.com'da satılmıyor
    - Gemini marj hesaplayamıyor
    - Çözüm: Statik %1.5 marj (Gram Altın ile aynı seviyede)
    """
    STATIC_GOLD_MARGINS = {
        "CUM": 0.015, 
        "ATA": 0.017,  
    }
    
    # ======================================
    # 🔥 EXOTIC DÖVİZ MARJLARI (STATİK) V5.6
    # ======================================
    """
    Ziraat Bankası'nda OLMAYAN 12 döviz için sabit marjlar.
    Bu marjlar değişmez, Gemini hesaplamaz.
    
    MANTIK:
    - Majör dövizler (USD, EUR, GBP) → Ziraat'tan dinamik
    - Exotic dövizler (RUB, CNY, PLN) → Config'den statik
    
    MARJ ORANLARI:
    - Orta Doğu: %1.5-1.8 (düşük spread)
    - Asya: %2.0 (orta spread)
    - Avrupa exotic: %2.0-2.2 (orta-yüksek spread)
    - Afrika/Rusya: %2.5 (yüksek spread)
    """
    STATIC_EXOTIC_MARGINS = {
        # Orta Doğu (Ziraat'ta yok)
        "AED": 0.015,  # %1.5 - BAE Dirhemi
        "KWD": 0.018,  # %1.8 - Kuveyt Dinarı
        "BHD": 0.018,  # %1.8 - Bahreyn Dinarı
        "OMR": 0.018,  # %1.8 - Umman Riyali
        "QAR": 0.015,  # %1.5 - Katar Riyali
        
        # Asya (Ziraat'ta yok)
        "CNY": 0.020,  # %2.0 - Çin Yuanı
        
        # Avrupa Exotic (Ziraat'ta yok)
        "PLN": 0.020,  # %2.0 - Polonya Zlotisi
        "RON": 0.020,  # %2.0 - Romanya Leyi
        "CZK": 0.020,  # %2.0 - Çek Korunası
        "HUF": 0.022,  # %2.2 - Macar Forinti
        "RSD": 0.022,  # %2.2 - Sırp Dinarı
        "BAM": 0.020,  # %2.0 - Bosna Markı
        
        # Afrika (Ziraat'ta yok)
        "EGP": 0.025,  # %2.5 - Mısır Lirası
        
        # Rusya (Ziraat'ta yok)
        "RUB": 0.025,  # %2.5 - Rus Rublesi
    }
    
    # ======================================
    # 🔥 FIREBASE PUSH NOTIFICATIONS
    # ======================================
    # Firebase Admin SDK Credentials dosya yolu (Render Secret Files)
    FIREBASE_CREDENTIALS_PATH = os.environ.get(
        "FIREBASE_CREDENTIALS_PATH", 
        "/etc/secrets/firebase_credentials.json"
    )
    
    # Firebase bildirim ayarları
    FIREBASE_NOTIFICATION_ENABLED = True  # Bildirimleri aç/kapat
    FIREBASE_PRIORITY = "high"  # high | normal
    FIREBASE_SOUND = "default"  # Bildirim sesi
    
    # ======================================
    # ZAMANLAYICI & PERFORMANS
    # ======================================
    # 👷 İşçi (Worker) - Veri güncelleme sıklığı (Saniye)
    UPDATE_INTERVAL = 60  # 1 Dakika ⚡
    
    # 📸 Fotoğrafçı (Snapshot) - Gece kaçta çalışacak?
    SNAPSHOT_HOUR = 0    # Saat 00
    SNAPSHOT_MINUTE = 0  # Dakika 00
    SNAPSHOT_SECOND = 0  # Saniye 00 (00:00:00)
    
    # 👮 Şef (Controller) - Sistem denetim sıklığı (Dakika)
    SUPERVISOR_INTERVAL = 10  # 10 Dakika (CPU/RAM kontrolü için)
    
    # 📊 Telegram Günlük Rapor Saati (Sabah 09:00)
    TELEGRAM_DAILY_REPORT_HOUR = 9
    
    # 🔔 Push Notification Günlük Özet Saati (Öğlen 14:00)
    PUSH_NOTIFICATION_DAILY_HOUR = 14
    PUSH_NOTIFICATION_DAILY_MINUTE = 0
    
    # 🛡️ Circuit Breaker (Sigorta) Ayarları
    CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3  # 3 kere üst üste hata alırsa dur
    CIRCUIT_BREAKER_TIMEOUT = 60           # 60 saniye bekle (Soğuma süresi)
    
    # ======================================
    # 🧹 TEMİZLİK MEKANİZMASI
    # ======================================
    # Disk backup temizlik ayarları
    CLEANUP_BACKUP_AGE_DAYS = 7  # 7 günden eski backup'ları sil
    CLEANUP_CHECK_INTERVAL = 86400  # Her gün kontrol et (24 saat)
    
    # ======================================
    # 🚧 BAKIM MODU AYARLARI
    # ======================================
    # Bakım modu varsayılan mesajı
    MAINTENANCE_DEFAULT_MESSAGE = "Sistem bakımda. Veriler güncel olmayabilir."
    
    # ======================================
    # 🚨 SELF-HEALING ALARM SİSTEMİ V5.3.1
    # ======================================
    # 🔥 CPU Eşiği (LOG SPAM FİX!)
    CPU_THRESHOLD = 80  # %80 (eski: %70) → RAM %70-80 arası SESSİZ
    
    # 🔥 RAM Eşiği (LOG SPAM FİX!)
    RAM_THRESHOLD = 95  # %95 (eski: %85) → RAM %85-95 arası SESSİZ
    
    # Müdahale sonrası bekleme süresi (Saniye)
    ALARM_COOLDOWN = 300  # 5 dakika
    
    # Alarm bildirimi aralığı (Saniye)
    ALARM_NOTIFICATION_INTERVAL = 1800  # 30 dakika
    
    # CPU yüksek kalma süresi (Saniye)
    CPU_HIGH_DURATION = 300  # 5 dakika
    
    # ======================================
    # 🔔 FİYAT ALARM SİSTEMİ (Redis-based)
    # ======================================
    # 🔥 Fiyat alarmları kontrol sıklığı (Dakika) - ARTTIRILDI!
    ALARM_CHECK_INTERVAL = 15  # 15 dakika (eski: 10) → RAM tasarrufu
    
    # Alarm TTL (Time To Live) - Alarmların Redis'te ne kadar süre saklanacağı
    ALARM_TTL = 30 * 24 * 60 * 60  # 30 gün (saniye cinsinden)
    
    # Kullanıcı başına maksimum alarm sayısı
    MAX_ALARMS_PER_USER = 50  # Her kullanıcı en fazla 50 alarm kurabilir
    
    # ======================================
    # 🗓️ TAKVİM BİLDİRİMLERİ
    # ======================================
    # Takvim kontrol saati (Her gün sabah 08:00)
    CALENDAR_CHECK_HOUR = 8
    CALENDAR_CHECK_MINUTE = 0
    
    # Banner otomatik aktif olma saati (Etkinlik günü 09:00)
    CALENDAR_BANNER_HOUR = 9
    CALENDAR_BANNER_MINUTE = 0
    
    # ======================================
    # 📰 GÜNLÜK HABER SİSTEMİ V3.0 (PREPARE + PUBLISH)
    # ======================================
    # 🔥 V5.5: Haber hazırlama ve yayınlama AYRI!
    
    # SABAH VARDİYASI
    NEWS_MORNING_PREPARE_HOUR = 23    # 23:55 - Sabah haberlerini hazırla (Gemini)
    NEWS_MORNING_PREPARE_MINUTE = 55
    
    NEWS_MORNING_PUBLISH_HOUR = 0     # 00:00 - Sabah haberlerini yayınla
    NEWS_MORNING_PUBLISH_MINUTE = 0
    
    # AKŞAM VARDİYASI
    NEWS_EVENING_PREPARE_HOUR = 11    # 11:55 - Akşam haberlerini hazırla (Gemini)
    NEWS_EVENING_PREPARE_MINUTE = 55
    
    NEWS_EVENING_PUBLISH_HOUR = 12    # 12:00 - Akşam haberlerini yayınla
    NEWS_EVENING_PUBLISH_MINUTE = 0
    
    # Haber kaynakları ayarları
    NEWS_MAX_RESULTS_PER_SOURCE = 30  # Her API'den max 30 haber
    NEWS_GEMINI_TIMEOUT = 30  # Gemini timeout (saniye)
    NEWS_BATCH_SIZE = 40  # Tek seferde max 40 haber özetle
    
    # ======================================
    # HAFTA SONU KİLİDİ
    # ======================================
    # Cuma günü piyasa kapanış saati (Türkiye saati)
    MARKET_CLOSE_FRIDAY_HOUR = 18  # Cuma 18:00 (Forex standardı)
    
    # Pazar gecesi kaçta piyasalar açılır? (Asya piyasaları)
    WEEKEND_REOPEN_HOUR = 0  # Pazar 00:00 (API bu saatte başlıyor)
    
    # ======================================
    # REDIS & CACHE ANAHTARLARI
    # ======================================
    # Redis URL (Render otomatik verir, yoksa localhost)
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    
    # Anahtar İsimleri
    CACHE_KEYS = {
        # Canlı veriler (HAM FİYAT - RAW)
        'currencies_all': 'kurabak:currencies:raw',
        'golds_all': 'kurabak:golds:raw',
        'silvers_all': 'kurabak:silvers:raw',
        
        # 💰 Kuyumcu fiyatları (JEWELER)
        'currencies_jeweler': 'kurabak:currencies:jeweler',
        'golds_jeweler': 'kurabak:golds:jeweler',
        'silvers_jeweler': 'kurabak:silvers:jeweler',
        
        # Yedek sistemler
        'backup': 'kurabak:backup:all',
        
        # 🔥 V5.6: İKİ SNAPSHOT SİSTEMİ
        'raw_snapshot': 'kurabak:raw_snapshot',           # Ham fiyatlar (asla değişmez)
        'jeweler_snapshot': 'kurabak:jeweler_snapshot',   # Marjlı fiyatlar (marj değişince güncellenir)
        
        # 🔙 BACKWARD COMPATIBILITY (Eski kodlar için)
        'yesterday_prices': 'kurabak:raw_snapshot',           # → raw_snapshot ile aynı
        'yesterday_prices_jeweler': 'kurabak:jeweler_snapshot',  # → jeweler_snapshot ile aynı
        
        # Worker + Şef sistemleri
        'last_worker_run': 'kurabak:last_worker_run',
        'backup_timestamp': 'kurabak:backup:timestamp',
        
        # Bakım ve Alarm Sistemleri
        'maintenance': 'system_maintenance',
        'banner': 'system_banner',
        'mute': 'system_mute',
        'alarm_cpu_state': 'alarm:cpu:state',
        'alarm_ram_state': 'alarm:ram:state',
        'alarm_last_notification': 'alarm:last_notification',
        'system_was_down': 'system_was_down',
        
        # Takvim Bildirimleri
        'calendar_last_check': 'calendar:last_check',
        'calendar_notified_events': 'calendar:notified_events',
        
        # 🔥 Firebase Push Notifications
        'fcm_tokens': 'firebase:fcm_tokens',
        'fcm_last_notification': 'firebase:last_notification',
        
        # 🔥 Fiyat Alarm Sistemi
        'alarm_last_check': 'alarm:price:last_check',
        
        # 🔥 Akıllı Loglama & Tracking
        'market_closed_logged': 'market:closed:logged',
        'api_request_stats': 'api:request:stats',
        
        # 🔥 Circuit Breaker & Temizlik
        'circuit_breaker_state': 'circuit:breaker:state',
        'circuit_breaker_failures': 'circuit:breaker:failures',
        'circuit_breaker_last_open': 'circuit:breaker:last_open',
        'cleanup_last_run': 'cleanup:last_run',
        
        # 📰 GÜNLÜK HABER SİSTEMİ V3.0
        'news_morning_pending': 'news:morning_pending',   # 23:55'te hazırlanan (geçici)
        'news_morning_shift': 'news:morning_shift',       # 00:00'da yayınlanan
        'news_evening_pending': 'news:evening_pending',   # 11:55'te hazırlanan (geçici)
        'news_evening_shift': 'news:evening_shift',       # 12:00'da yayınlanan
        'news_last_update': 'news:last_update',
        'daily_bayram': 'daily:bayram',
        
        # 🔥 DİNAMİK MARJ SİSTEMİ V5.6 (HİBRİT)
        'dynamic_margins': 'dynamic:margins',          # 24 saat TTL (dinamik + exotic + gold birleşmiş)
        'margin_last_update': 'margin:last_update',    # TTL=0 süresiz (en son başarılı marjlar + timestamp)
    }
    
    # ======================================
    # TREND ANALİZİ (ALEV ROZETİ 🔥)
    # ======================================
    # Kaç yüzde değişimde "Sert Hareket" sayılsın?
    TREND_HIGH_THRESHOLD = 5.0    # %5 ve üzeri -> HIGH_UP / HIGH_DOWN
    TREND_MEDIUM_THRESHOLD = 1.0  # %1-5 arası -> MEDIUM
    
    # ======================================
    # BÖLGESEL FİLTRELEME
    # ======================================
    REGIONAL_CURRENCIES = {
        "north_america": ["USD", "CAD"],
        "europe": ["EUR", "GBP", "CHF", "SEK", "NOK"],
        "middle_east": ["SAR", "AED", "KWD", "BHD", "OMR", "QAR"],
        "asia_pacific": ["CNY", "AUD"],
        "eastern_europe": ["RUB"],
        "balkans_europe": ["PLN", "RON", "CZK", "HUF", "RSD", "BAM"],
        "africa": ["EGP"]
    }
    
    # ======================================
    # MOBİL UYGULAMANIN GÖSTERDIĞI VARLIKLAR
    # ======================================
    # 23 Döviz
    MOBILE_CURRENCIES = [
        "USD", "EUR", "GBP", "CHF", "CAD", "AUD", "RUB",
        "SAR", "AED", "KWD", "BHD", "OMR", "QAR",
        "CNY", "SEK", "NOK",
        "PLN", "RON", "CZK", "EGP", "RSD", "HUF", "BAM"
    ]
    
    # 6 Altın
    MOBILE_GOLDS = ["GRA", "C22", "YAR", "TAM", "CUM", "ATA"]
    
    # 1 Gümüş
    MOBILE_SILVER = "AG"
    
    # ======================================
    # GÜVENLİK (CORS & RATE LIMIT)
    # ======================================
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "")  # ✅ Boş = Sadece mobil
    SECRET_KEY = os.environ.get("SECRET_KEY", "gizli-anahtar-degistir")
    
    # ======================================
    # TELEGRAM BOT (BİLDİRİMLER)
    # ======================================
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
    
    # Telegram Sessiz Mod
    TELEGRAM_SILENT_MODE = True
    
    # ======================================
    # ŞEF (CONTROLLER) AYARLARI
    # ======================================
    SUPERVISOR_WORKER_TIMEOUT = 600  # 10 dakika
    SUPERVISOR_WARNING_TIMEOUT = 300  # 5 dakika
    
    # ======================================
    # YEDEKLEME (BACKUP) SİSTEMİ
    # ======================================
    BACKUP_INTERVAL = 900  # 15 dakika
    BACKUP_TTL = 86400  # 24 saat
    
    # ======================================
    # GELIŞTIRME AYARLARI
    # ======================================
    DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
