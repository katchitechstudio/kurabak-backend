"""
Configuration - PRODUCTION READY V5.2 🧠📰🏦💰
===================================================
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
✅ PUSH NOTIFICATION: Öğlen 12:00 günlük özet
✅ TEMİZLİK MEKANİZMASI: 7 günlük otomatik temizlik
✅ WORKER INTERVAL: 1 dakika (daha hızlı güncellemeler)
✅ 📰 GÜNLÜK HABER SİSTEMİ V2.0: Sabah + Akşam vardiyası + Gemini 2.0 + Bayram kontrolü
✅ 💰 MARKET MARGIN SYSTEM: Ham/Kuyumcu fiyat profilleri (YENİ!)
"""
import os

class Config:
    # ======================================
    # UYGULAMA AYARLARI
    # ======================================
    APP_NAME = "KuraBak Backend API"
    APP_VERSION = "5.2.0"  # 💰 Market Margin System
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
    # 💰 MARKET MARGIN SYSTEM (YENİ!)
    # ======================================
    """
    FİYAT PROFİLLERİ:
    - raw: Ham fiyat (API'den direk gelen, borsa/toptan fiyatı)
    - jeweler: Kuyumcu/Fiziki piyasa fiyatı (marj eklenmiş)
    
    KULLANIM:
    - Kullanıcı ayarlardan "Ham Fiyat" veya "Kuyumcu Fiyatı" seçer
    - Backend her iki fiyat serisini de tutar (ayrı snapshot'lar)
    - Yüzdelik değişimler kendi snapshot'larına göre hesaplanır
    
    MARJ ORANLARI (Gerçek piyasa verilerine göre):
    - Altınlar: %2-7 (işçilik + KDV + kâr)
    - Dövizler: %0 (zaten piyasa fiyatı)
    - Gümüş: %25 (KDV %20 + işçilik + likidite düşük)
    """
    
    PRICE_PROFILES = {
        # RAW PROFILE - Ham Fiyat (API'den gelen)
        "raw": {},  # Hiç marj yok, direkt API fiyatı
        
        # JEWELER PROFILE - Kuyumcu/Fiziki Piyasa Fiyatı
        "jeweler": {
            # ALTINLAR (Yüksek marj - işçilik + KDV + kâr)
            "GRA": 0.072,              # Gram Altın: %7.2
            "HAS": 0.065,              # Has Altın: %6.5
            "CEYREKALTIN": 0.025,      # Çeyrek: %2.5
            "C22": 0.025,              # Çeyrek (alternatif kod): %2.5
            "YARIMALTIN": 0.025,       # Yarım: %2.5
            "YAR": 0.025,              # Yarım (alternatif kod): %2.5
            "TAMALTIN": 0.022,         # Tam: %2.2
            "TAM": 0.022,              # Tam (alternatif kod): %2.2
            "CUMHURIYETALTINI": 0.015, # Cumhuriyet: %1.5
            "CUM": 0.015,              # Cumhuriyet (alternatif kod): %1.5
            "ATAALTIN": 0.028,         # Ata: %2.8
            "ATA": 0.028,              # Ata (alternatif kod): %2.8
            
            # GÜMÜŞ (ÇOK YÜKSEK MARJ - KDV %20 + işçilik + likidite düşük)
            "GUMUS": 0.25,             # Gümüş: %25
            "AG": 0.25,                # Gümüş (alternatif kod): %25
            "SILVER": 0.25,            # Gümüş (İngilizce): %25
            
            # DÖVİZLER (Marj yok - zaten piyasa fiyatı)
            # API'den gelen döviz fiyatları gerçek piyasa fiyatına çok yakın
            # Bu yüzden dövizlere marj eklemiyoruz
            "USD": 0.0,                # Dolar: %0
            "EUR": 0.0,                # Euro: %0
            "GBP": 0.0,                # Sterlin: %0
            "CHF": 0.0,                # Frank: %0
            "CAD": 0.0,                # Kanada Doları: %0
            "AUD": 0.0,                # Avustralya Doları: %0
            "RUB": 0.0,                # Ruble: %0
            "SAR": 0.0,                # Suudi Riyali: %0
            "AED": 0.0,                # BAE Dirhemi: %0
            "KWD": 0.0,                # Kuveyt Dinarı: %0
            "BHD": 0.0,                # Bahreyn Dinarı: %0
            "OMR": 0.0,                # Umman Riyali: %0
            "QAR": 0.0,                # Katar Riyali: %0
            "CNY": 0.0,                # Çin Yuanı: %0
            "SEK": 0.0,                # İsveç Kronu: %0
            "NOK": 0.0,                # Norveç Kronu: %0
            "PLN": 0.0,                # Polonya Zlotisi: %0
            "RON": 0.0,                # Romanya Leyi: %0
            "CZK": 0.0,                # Çek Kronu: %0
            "EGP": 0.0,                # Mısır Lirası: %0
            "RSD": 0.0,                # Sırp Dinarı: %0
            "HUF": 0.0,                # Macar Forinti: %0
            "BAM": 0.0,                # Bosna Markı: %0
        }
    }
    
    # Varsayılan fiyat profili (uygulama ilk açıldığında)
    DEFAULT_PRICE_PROFILE = "jeweler"  # Kuyumcu fiyatı varsayılan
    
    # Profil tanımlanmamış varlıklar için varsayılan marj
    DEFAULT_MARKET_MARGIN = 0.0  # %0 (marj yok)
    
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
    SNAPSHOT_SECOND = 5  # Saniye 05 (00:00:05)
    
    # 👮 Şef (Controller) - Sistem denetim sıklığı (Dakika)
    SUPERVISOR_INTERVAL = 10  # 10 Dakika (CPU/RAM kontrolü için)
    
    # 📊 Telegram Günlük Rapor Saati (Sabah 09:00)
    TELEGRAM_DAILY_REPORT_HOUR = 9
    
    # 🔔 Push Notification Günlük Özet Saati (Öğlen 12:00)
    PUSH_NOTIFICATION_DAILY_HOUR = 12
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
    # 🚨 SELF-HEALING ALARM SİSTEMİ
    # ======================================
    # CPU Eşiği (Varsayılan %)
    CPU_THRESHOLD = 80  # %80
    
    # RAM Eşiği (Varsayılan %)
    RAM_THRESHOLD = 85  # %85
    
    # Müdahale sonrası bekleme süresi (Saniye)
    ALARM_COOLDOWN = 300  # 5 dakika
    
    # Alarm bildirimi aralığı (Saniye)
    ALARM_NOTIFICATION_INTERVAL = 1800  # 30 dakika
    
    # CPU yüksek kalma süresi (Saniye)
    CPU_HIGH_DURATION = 300  # 5 dakika
    
    # ======================================
    # 🔔 FİYAT ALARM SİSTEMİ (Redis-based)
    # ======================================
    # Fiyat alarmları kontrol sıklığı (Dakika)
    # 5-15 dakika arası önerilir (10 dakika optimal)
    ALARM_CHECK_INTERVAL = 10  # 10 dakika
    
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
    # 📰 GÜNLÜK HABER SİSTEMİ V2.0 (GÜNCELLENDİ!)
    # ======================================
    # Haber vardiyası saatleri
    NEWS_MORNING_SHIFT_HOUR = 0   # Gece 00:00 - Sabah vardiyası hazırlanır
    NEWS_MORNING_SHIFT_MINUTE = 0
    
    NEWS_EVENING_SHIFT_HOUR = 12   # Öğlen 12:00 - Akşam vardiyası hazırlanır
    NEWS_EVENING_SHIFT_MINUTE = 0
    
    # Haber kaynakları ayarları
    NEWS_MAX_RESULTS_PER_SOURCE = 10  # Her API'den max 10 haber
    NEWS_GEMINI_TIMEOUT = 30  # Gemini timeout (saniye)
    NEWS_BATCH_SIZE = 20  # Tek seferde max 20 haber özetle
    
    # ======================================
    # HAFTA SONU KİLİDİ
    # ======================================
    # Pazar gecesi kaçta piyasalar açılır? (Asya piyasaları)
    WEEKEND_REOPEN_HOUR = 23  # Pazar 23:00
    
    # ======================================
    # REDIS & CACHE ANAHTARLARI
    # ======================================
    # Redis URL (Render otomatik verir, yoksa localhost)
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    
    # Anahtar İsimleri
    CACHE_KEYS = {
        # Canlı veriler (HAM FİYAT - RAW)
        'currencies_all': 'kurabak:currencies:raw',      # 🔥 DEĞİŞTİ
        'golds_all': 'kurabak:golds:raw',                # 🔥 DEĞİŞTİ
        'silvers_all': 'kurabak:silvers:raw',            # 🔥 DEĞİŞTİ
        
        # 💰 Kuyumcu fiyatları (JEWELER - YENİ!)
        'currencies_jeweler': 'kurabak:currencies:jeweler',  # YENİ
        'golds_jeweler': 'kurabak:golds:jeweler',            # YENİ
        'silvers_jeweler': 'kurabak:silvers:jeweler',        # YENİ
        
        # Yedek sistemler
        'backup': 'kurabak:backup:all',
        
        # Worker + Snapshot + Şef sistemleri
        'yesterday_prices': 'kurabak:yesterday_prices:raw',      # 🔥 DEĞİŞTİ
        'yesterday_prices_jeweler': 'kurabak:yesterday_prices:jeweler',  # YENİ
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
        
        # 📰 GÜNLÜK HABER SİSTEMİ V2.0 (GÜNCELLENDİ!)
        'news_morning_shift': 'news:morning_shift',      # Sabah vardiyası (00:00-12:00)
        'news_evening_shift': 'news:evening_shift',      # Akşam vardiyası (12:00-00:00)
        'news_last_update': 'news:last_update',          # Son güncelleme zamanı
        'daily_bayram': 'daily:bayram',                  # 🏦 BAYRAM CACHE (YENİ!)
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
