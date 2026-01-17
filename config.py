"""
Configuration - PRODUCTION READY (CENTRAL BRAIN) 🧠
===================================================
✅ API URLS: V5 (Primary), V4 & V3 (Fallbacks)
✅ TIMEOUTS: Hızlı yanıt için optimize edilmiş süreler.
✅ CACHE KEYS: Redis anahtarlarının tek merkezi.
✅ REGIONS: 20 Döviz için Bölgesel Gruplama.
"""

import os

class Config:
    # ======================================
    # UYGULAMA AYARLARI
    # ======================================
    APP_NAME = "KuraBak Backend"
    APP_VERSION = "2.0.0 (Ultimate)"
    ENVIRONMENT = os.environ.get("FLASK_ENV", "production")
    
    # Zaman Dilimi (Çok Önemli - Loglar ve Raporlar için)
    DEFAULT_TIMEZONE = "Europe/Istanbul"
    
    # ======================================
    # API KAYNAKLARI (TRIPLE FALLBACK)
    # ======================================
    # 1. Primary (En Hızlı ve Güncel)
    API_V5_URL = "https://finance.truncgil.com/api/today.json"
    API_V5_TIMEOUT = (5, 10) # 5sn bağlanma, 10sn okuma
    
    # 2. Secondary (Yedek)
    API_V4_URL = "https://finans.truncgil.com/v4/today.json"
    API_V4_TIMEOUT = (8, 15) # Biraz daha toleranslı
    
    # 3. Tertiary (Son Çare - Farklı Format)
    API_V3_URL = "https://finans.truncgil.com/v3/today.json"
    API_V3_TIMEOUT = (8, 15)

    # ======================================
    # ZAMANLAYICI & PERFORMANS
    # ======================================
    # Veri güncelleme sıklığı (Saniye)
    UPDATE_INTERVAL = 120  # 2 Dakika
    
    # Telegram Günlük Rapor Saati (09:00)
    TELEGRAM_DAILY_REPORT_HOUR = 9 
    
    # Circuit Breaker (Sigorta) Ayarları
    CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3  # 3 kere üst üste hata alırsa dur
    CIRCUIT_BREAKER_TIMEOUT = 60           # 60 saniye bekle (Soğuma süresi)

    # ======================================
    # REDIS & CACHE ANAHTARLARI
    # ======================================
    # Redis URL (Render otomatik verir, yoksa localhost)
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    
    # Anahtar İsimleri (Kod içinde elle yazmamak için)
    CACHE_KEYS = {
        'currencies_all': 'kurabak:currencies:all',
        'golds_all': 'kurabak:golds:all',
        'silvers_all': 'kurabak:silvers:all',
        'summary': 'kurabak:summary',
        'backup': 'kurabak:backup:all' # 15 dakikalık kara kutu
    }

    # ======================================
    # BÖLGESEL FİLTRELEME (20 DÖVİZ)
    # ======================================
    # Frontend'de "Asya", "Avrupa" sekmeleri için gruplama
    REGIONAL_CURRENCIES = {
        "north_america": ["USD", "CAD"],
        "europe": ["EUR", "GBP", "CHF", "DKK", "SEK", "NOK"],
        "east_europe": ["RUB", "ILS", "BGN"], # ILS ve BGN coğrafi/ekonomik yakınlık
        "middle_east": ["SAR", "AED", "KWD", "IQD", "IRR", "LYD", "BHD"],
        "asia_pacific": ["JPY", "AUD", "ZAR"] # ZAR (Afrika) genelde Diğer/Asya grubunda sunulur
    }

    # ======================================
    # GÜVENLİK (CORS & RATE LIMIT)
    # ======================================
    # Hangi siteler bu API'ye erişebilir? ("*" = Herkes)
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
    
    # Manuel güncelleme için API Anahtarı (Opsiyonel güvenlik)
    SECRET_KEY = os.environ.get("SECRET_KEY", "gizli-anahtar-degistir")
