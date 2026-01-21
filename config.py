"""
Configuration - PRODUCTION READY V3.0 (BAKIM & ALARM SİSTEMİ) 🧠
===================================================
✅ API URLS: V5 (Primary), V4 & V3 (Fallbacks)
✅ TIMEOUTS: Hızlı yanıt için optimize edilmiş süreler.
✅ CACHE KEYS: Redis anahtarlarının tek merkezi.
✅ REGIONS: 20 Döviz için Bölgesel Gruplama.
✅ WORKER + SNAPSHOT + ŞEF SİSTEMİ: Akıllı backend yapılandırması
✅ YENİ: BAKIM MODU & SELF-HEALING ALARM SİSTEMİ
"""
import os

class Config:
    # ======================================
    # UYGULAMA AYARLARI
    # ======================================
    APP_NAME = "KuraBak Backend API"
    APP_VERSION = "3.0.0"  # 🔥 YENİ VERSIYON
    ENVIRONMENT = os.environ.get("FLASK_ENV", "production")
    
    # Zaman Dilimi (Çok Önemli - Loglar, Snapshot ve Raporlar için)
    DEFAULT_TIMEZONE = "Europe/Istanbul"
    
    # ======================================
    # API KAYNAĞI (SADECE V5)
    # ======================================
    # V5 API (Tek ve Güvenilir Kaynak)
    API_V5_URL = "https://finance.truncgil.com/api/today.json"
    API_V5_TIMEOUT = (5, 10)  # 5sn bağlanma, 10sn okuma
    
    # ======================================
    # ZAMANLAYICI & PERFORMANS
    # ======================================
    # 👷 İşçi (Worker) - Veri güncelleme sıklığı (Saniye)
    UPDATE_INTERVAL = 120  # 2 Dakika
    
    # 📸 Fotoğrafçı (Snapshot) - Gece kaçta çalışacak?
    SNAPSHOT_HOUR = 0    # Saat 00
    SNAPSHOT_MINUTE = 0  # Dakika 00
    SNAPSHOT_SECOND = 5  # Saniye 05 (00:00:05)
    
    # 👮 Şef (Controller) - Sistem denetim sıklığı (Dakika)
    SUPERVISOR_INTERVAL = 10  # 🔥 YENİ: 10 Dakika (CPU/RAM kontrolü için)
    
    # 📊 Telegram Günlük Rapor Saati (Sabah 09:00)
    TELEGRAM_DAILY_REPORT_HOUR = 9
    
    # 🛡️ Circuit Breaker (Sigorta) Ayarları
    CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3  # 3 kere üst üste hata alırsa dur
    CIRCUIT_BREAKER_TIMEOUT = 60           # 60 saniye bekle (Soğuma süresi)
    
    # ======================================
    # 🚧 BAKIM MODU AYARLARI (YENİ!)
    # ======================================
    # Bakım modu varsayılan mesajı
    MAINTENANCE_DEFAULT_MESSAGE = "Sistem bakımda. Veriler güncel olmayabilir."
    
    # ======================================
    # 🚨 SELF-HEALING ALARM SİSTEMİ (YENİ!)
    # ======================================
    # CPU Eşiği (Varsayılan %)
    CPU_THRESHOLD = 80  # %80
    
    # RAM Eşiği (Varsayılan %)
    RAM_THRESHOLD = 85  # %85
    
    # Alarm kontrol sıklığı (Saniye) - 🔥 HIZLI MÜDAHALE için 1 dakika!
    ALARM_CHECK_INTERVAL = 60  # 1 dakika (60 saniye) - Kritik sorunları hızlıca yakalar
    
    # Müdahale sonrası bekleme süresi (Saniye)
    ALARM_COOLDOWN = 300  # 5 dakika (Tekrar müdahale etmeden önce bekle)
    
    # Alarm bildirimi aralığı (Saniye) - Aynı alarm için tekrar bildirim göndermeden önce bekle
    ALARM_NOTIFICATION_INTERVAL = 1800  # 30 dakika
    
    # CPU yüksek kalma süresi (Saniye) - CPU bu kadar süre yüksekse müdahale et
    CPU_HIGH_DURATION = 300  # 5 dakika
    
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
    
    # Anahtar İsimleri (Kod içinde elle yazmamak için)
    CACHE_KEYS = {
        # Canlı veriler
        'currencies_all': 'kurabak:currencies:all',
        'golds_all': 'kurabak:golds:all',
        'silvers_all': 'kurabak:silvers:all',
        'summary': 'kurabak:summary',
        
        # Yedek sistemler
        'backup': 'kurabak:backup:all',  # 15 dakikalık kara kutu
        
        # Worker + Snapshot + Şef sistemleri
        'yesterday_prices': 'kurabak:yesterday_prices',  # 📸 Snapshot referans fiyatları
        'last_worker_run': 'kurabak:last_worker_run',    # 👷 İşçi son çalışma zamanı
        'backup_timestamp': 'kurabak:backup:timestamp',  # 📦 Backup son kayıt zamanı
        
        # 🔥 YENİ: Bakım ve Alarm Sistemleri
        'maintenance': 'system_maintenance',             # 🚧 Bakım modu durumu
        'banner': 'system_banner',                       # 📢 Banner mesajı
        'mute': 'system_mute',                          # 🔇 Death Star modu
        'alarm_cpu_state': 'alarm:cpu:state',           # 🧠 CPU alarm durumu
        'alarm_ram_state': 'alarm:ram:state',           # 💾 RAM alarm durumu
        'alarm_last_notification': 'alarm:last_notification',  # 🔔 Son bildirim zamanı
        'system_was_down': 'system_was_down'            # 🔄 Sistem çökmüş mü?
    }
    
    # ======================================
    # TREND ANALİZİ (ALEV ROZETİ 🔥)
    # ======================================
    # Kaç yüzde değişimde "Sert Hareket" sayılsın?
    TREND_HIGH_THRESHOLD = 2.0    # %2 ve üzeri -> HIGH_UP / HIGH_DOWN
    TREND_MEDIUM_THRESHOLD = 1.0  # %1-2 arası -> MEDIUM (Gelecekte eklenebilir)
    
    # ======================================
    # BÖLGESEL FİLTRELEME (LEGACY - Kullanılmıyor ama backward compatibility için duruyor)
    # ======================================
    # Frontend'de "Asya", "Avrupa" sekmeleri için gruplama
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
    # 23 Döviz (Halk Tipi Güncellenmiş Liste - TRY Hariç)
    MOBILE_CURRENCIES = [
        # Ana Dövizler (7)
        "USD", "EUR", "GBP", "CHF", "CAD", "AUD", "RUB",
        
        # Orta Doğu (6)
        "SAR", "AED", "KWD", "BHD", "OMR", "QAR",
        
        # Asya (1)
        "CNY",
        
        # İskandinav (2)
        "SEK", "NOK",
        
        # Halk Tipi Yeni Eklenenler (7)
        "PLN",  # Polonya Zlotisi - Erasmus & Nakliye
        "RON",  # Romanya Leyi - Komşu ticaret
        "CZK",  # Çek Korunası - Prag turizmi
        "EGP",  # Mısır Lirası - Vizesiz tatil
        "RSD",  # Sırbistan Dinarı - Balkan turları
        "HUF",  # Macar Forinti - Budapeşte
        "BAM"   # Bosna-Hersek Markı - Duygusal bağ
    ]
    
    # 6 Altın
    MOBILE_GOLDS = [
        "GRA",   # Gram Altın
        "C22",   # Çeyrek Altın
        "YAR",   # Yarım Altın
        "TAM",   # Tam Altın
        "CUM",   # Cumhuriyet Altını
        "ATA"    # Atatürk Altını
    ]
    
    # 1 Gümüş
    MOBILE_SILVER = "AG"
    
    # ======================================
    # GÜVENLİK (CORS & RATE LIMIT)
    # ======================================
    # Hangi siteler bu API'ye erişebilir? ("*" = Herkes)
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
    
    # Manuel güncelleme için API Anahtarı (Opsiyonel güvenlik)
    SECRET_KEY = os.environ.get("SECRET_KEY", "gizli-anahtar-degistir")
    
    # ======================================
    # TELEGRAM BOT (BİLDİRİMLER)
    # ======================================
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
    
    # Telegram Sessiz Mod (Sadece kritik ve rapor bildirimler)
    TELEGRAM_SILENT_MODE = True
    
    # ======================================
    # ŞEF (CONTROLLER) AYARLARI
    # ======================================
    # İşçi (Worker) kaç dakika uyursa "kritik" kabul edilsin?
    SUPERVISOR_WORKER_TIMEOUT = 600  # 10 dakika (saniye cinsinden)
    
    # Şef kaç dakika önce uyarı versin? (Warning seviyesi)
    SUPERVISOR_WARNING_TIMEOUT = 300  # 5 dakika
    
    # ======================================
    # YEDEKLEME (BACKUP) SİSTEMİ
    # ======================================
    # Backup kaç dakikada bir alınacak?
    BACKUP_INTERVAL = 900  # 15 dakika (saniye cinsinden)
    
    # Backup kaç gün saklanacak? (Redis TTL)
    BACKUP_TTL = 86400  # 24 saat (saniye cinsinden)
    
    # ======================================
    # GELIŞTIRME AYARLARI
    # ======================================
    # Debug modu (Sadece local development için)
    DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
    
    # Log seviyesi
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
