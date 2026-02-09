"""
Configuration - PRODUCTION READY V5.3 🧠📰🏦💰🔥
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
✅ 💰 MARKET MARGIN SYSTEM: Ham/Kuyumcu fiyat profilleri
✅ 🔥 DYNAMIC HALF MARGIN: Gemini ile günlük otomatik marj güncelleme (YENİ!)
"""
import os

class Config:
    # ======================================
    # UYGULAMA AYARLARI
    # ======================================
    APP_NAME = "KuraBak Backend API"
    APP_VERSION = "5.3.0"  # 🔥 Dynamic Half Margin System
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
    # 💰 MARKET MARGIN SYSTEM V2.0 (YENİ!)
    # ======================================
    """
    FİYAT PROFİLLERİ:
    - raw: Ham fiyat (API'den direk gelen, borsa/toptan fiyatı)
    - jeweler: Kuyumcu/Fiziki piyasa fiyatı (YARIM MARJ eklenmiş)
    
    KULLANIM:
    - Kullanıcı ayarlardan "Ham Fiyat" veya "Kuyumcu Fiyatı" seçer
    - Backend her iki fiyat serisini de tutar (ayrı snapshot'lar)
    - Yüzdelik değişimler kendi snapshot'larına göre hesaplanır
    
    DİNAMİK MARJ SİSTEMİ (YENİ!):
    - Günde 1 kere (00:00) Harem fiyatları kontrol edilir
    - Gemini AI ile gerçek marjlar hesaplanır
    - Hesaplanan marjın YARISI kullanılır (alarm patlaması önlenir)
    - Gümüş için özel: %75'i kullanılır (%100 yerine)
    - Redis'e kaydedilir (24 saat TTL)
    - Fallback: Gemini patlarsa aşağıdaki varsayılan marjlar kullanılır
    
    MARJ ORANLARI (Fallback - Gemini kullanılamazsa):
    - Altınlar: %0-2.6 (Harem marjının yarısı)
    - Dövizler: %0.3-0.8 (Kuyumcu gişe farkı)
    - Gümüş: %15 (Harem marjının %75'i)
    """
    
    PRICE_PROFILES = {
        # RAW PROFILE - Ham Fiyat (API'den gelen)
        "raw": {},  # Hiç marj yok, direkt API fiyatı
        
        # JEWELER PROFILE - Kuyumcu/Fiziki Piyasa Fiyatı (YARIM MARJ)
        "jeweler": {
            # 🟡 ALTINLAR - YARIM MARJ (Fallback değerler)
            # Redis'te 'dynamic_half_margins' varsa onlar kullanılır
            "GRA": 0.026,              # Gram Altın: %2.6 (varsayılan yarım marj)
            "HAS": 0.026,              # Has Altın: %2.6
            "CEYREKALTIN": 0.001,      # Çeyrek: %0.1
            "C22": 0.001,              # Çeyrek (alternatif kod): %0.1
            "YARIMALTIN": 0.0005,      # Yarım: %0.05
            "YAR": 0.0005,             # Yarım (alternatif kod): %0.05
            "TAMALTIN": 0.0,           # Tam: %0
            "TAM": 0.0,                # Tam (alternatif kod): %0
            "CUMHURIYETALTINI": 0.0,   # Cumhuriyet: %0
            "CUM": 0.0,                # Cumhuriyet (alternatif kod): %0
            "ATAALTIN": 0.0,           # Ata: %0
            "ATA": 0.0,                # Ata (alternatif kod): %0
            
            # ⚪ GÜMÜŞ - %15 MARJ (Fallback - Harem marjının %75'i)
            "GUMUS": 0.15,             # Gümüş: %15
            "AG": 0.15,                # Gümüş (alternatif kod): %15
            "SILVER": 0.15,            # Gümüş (İngilizce): %15
            
            # 💵 DÖVİZLER - KÜÇÜK SABİT MARJ (Kuyumcu gişe farkı)
            "USD": 0.005,              # Dolar: %0.5
            "EUR": 0.003,              # Euro: %0.3
            "GBP": 0.006,              # Sterlin: %0.6
            "CHF": 0.004,              # Frank: %0.4
            "CAD": 0.008,              # Kanada Doları: %0.8
            "AUD": 0.004,              # Avustralya Doları: %0.4
            "RUB": 0.005,              # Ruble: %0.5
            "SAR": 0.005,              # Suudi Riyali: %0.5
            "AED": 0.005,              # BAE Dirhemi: %0.5
            "KWD": 0.005,              # Kuveyt Dinarı: %0.5
            "BHD": 0.005,              # Bahreyn Dinarı: %0.5
            "OMR": 0.005,              # Umman Riyali: %0.5
            "QAR": 0.005,              # Katar Riyali: %0.5
            "CNY": 0.005,              # Çin Yuanı: %0.5
            "SEK": 0.005,              # İsveç Kronu: %0.5
            "NOK": 0.005,              # Norveç Kronu: %0.5
            "PLN": 0.005,              # Polonya Zlotisi: %0.5
            "RON": 0.005,              # Romanya Leyi: %0.5
            "CZK": 0.005,              # Çek Kronu: %0.5
            "EGP": 0.005,              # Mısır Lirası: %0.5
            "RSD": 0.005,              # Sırp Dinarı: %0.5
            "HUF": 0.005,              # Macar Forinti: %0.5
            "BAM": 0.005,              # Bosna Markı: %0.5
        }
    }
    
    # Varsayılan fiyat profili (uygulama ilk açıldığında)
    DEFAULT_PRICE_PROFILE = "jeweler"  # Kuyumcu fiyatı varsayılan
    
    # Profil tanımlanmamış varlıklar için varsayılan marj
    DEFAULT_MARKET_MARGIN = 0.0  # %0 (marj yok)
    
    # ======================================
    # 🔥 DİNAMİK MARJ SİSTEMİ AYARLARI (YENİ!)
    # ======================================
    # Harem veri kaynağı (HTML parse edilecek)
    HAREM_PRICE_URL = "https://altin.doviz.com/harem"
    HAREM_FETCH_TIMEOUT = 10  # 10 saniye
    
    # Marj güncelleme saati (Gece 00:00 - Sabah vardiyası ile birlikte)
    MARGIN_UPDATE_HOUR = 0
    MARGIN_UPDATE_MINUTE = 0
    
    # Marj hesaplama stratejisi
    MARGIN_CALCULATION_STRATEGY = "half"  # "half" = Yarım marj, "full" = Tam marj
    
    # Gümüş için özel çarpan
    SILVER_MARGIN_MULTIPLIER = 0.75  # %75 kullan (%100 yerine)
    
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
    
    # Alarm TTL (Time To Live) - Alarmların Redis'te ne kadar süre saklanacağı
    ALARM_TTL = 90 * 24 * 60 * 60  # 90 gün (saniye cinsinden)
    
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
    # 🔥 V5.3: Piyasa saatleri düzeltildi
    
    # Cuma günü piyasa kapanış saati (Türkiye saati)
    MARKET_CLOSE_FRIDAY_HOUR = 18  # Cuma 18:00 (Forex standardı)
    
    # Pazar gecesi kaçta piyasalar açılır? (Asya piyasaları)
    WEEKEND_REOPEN_HOUR = 0  # 🔥 DEĞİŞTİ: Pazar 00:00 (API bu saatte başlıyor)
    
    # ⚠️ Eski değer: 23 (Pazar 23:00) → Yanlıştı, API pazar 00:00'da başlıyor
    
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
        
        # Worker + Snapshot + Şef sistemleri
        'yesterday_prices': 'kurabak:yesterday_prices:raw',
        'yesterday_prices_jeweler': 'kurabak:yesterday_prices:jeweler',
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
        
        # 📰 GÜNLÜK HABER SİSTEMİ V2.0
        'news_morning_shift': 'news:morning_shift',
        'news_evening_shift': 'news:evening_shift',
        'news_last_update': 'news:last_update',
        'daily_bayram': 'daily:bayram',
        
        # 🔥 DİNAMİK YARIM MARJ SİSTEMİ (YENİ!)
        'dynamic_half_margins': 'dynamic:half_margins',  # 24 saat TTL
        'margin_last_update': 'margin:last_update',       # Son güncelleme zamanı
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
