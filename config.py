"""
Configuration - PRODUCTION READY V4.5 🧠
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
"""
import os

class Config:
    # ======================================
    # UYGULAMA AYARLARI
    # ======================================
    APP_NAME = "KuraBak Backend API"
    APP_VERSION = "4.5.0"  # 🔔 Fiyat Alarm Sistemi Eklendi
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
    UPDATE_INTERVAL = 60  # 1 Dakika ⚡ (değiştirildi: 120 → 60)
    
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
        # Canlı veriler
        'currencies_all': 'kurabak:currencies:all',
        'golds_all': 'kurabak:golds:all',
        'silvers_all': 'kurabak:silvers:all',
        
        # Yedek sistemler
        'backup': 'kurabak:backup:all',
        
        # Worker + Snapshot + Şef sistemleri
        'yesterday_prices': 'kurabak:yesterday_prices',
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
        
        # 🔥 Fiyat Alarm Sistemi (Yeni!)
        'alarm_last_check': 'alarm:price:last_check',
        
        # 🔥 Akıllı Loglama & Tracking
        'market_closed_logged': 'market:closed:logged',
        'api_request_stats': 'api:request:stats',
        
        # 🔥 Circuit Breaker & Temizlik
        'circuit_breaker_state': 'circuit:breaker:state',
        'circuit_breaker_failures': 'circuit:breaker:failures',
        'circuit_breaker_last_open': 'circuit:breaker:last_open',
        'cleanup_last_run': 'cleanup:last_run'
    }
    
    # ======================================
    # TREND ANALİZİ (ALEV ROZETİ 🔥)
    # ======================================
    # Kaç yüzde değişimde "Sert Hareket" sayılsın?
    TREND_HIGH_THRESHOLD = 5.0    # %5 ve üzeri -> HIGH_UP / HIGH_DOWN ✅ DEĞİŞTİ!
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
