"""
KuraBak Backend Configuration
Redis-only architecture (no PostgreSQL)
Dual API support (V3 + V4)
"""
import os

class Config:
    """KuraBak Backend genel ayarları"""
    
    # ======================================
    # REDIS (Cache/Storage)
    # ======================================
    REDIS_URL = os.environ.get("REDIS_URL")
    
    # ======================================
    # CACHE AYARLARI
    # ======================================
    CACHE_TTL = 300  # 5 dakika (saniye)
    UPDATE_INTERVAL = 90  # 1.5 dakika (saniye) - API çekme aralığı
    
    # ======================================
    # API AYARLARI - DUAL API SUPPORT
    # ======================================
    API_TIMEOUT = 15  # saniye
    
    # V3 ve V4 API endpoint'leri
    API_V3_URL = "https://finans.truncgil.com/v3/today.json"
    API_V4_URL = "https://finans.truncgil.com/v4/today.json"
    
    # Geriye uyumluluk için (eski kodlar kullanabilir)
    API_BASE_URL = API_V4_URL  # Deprecated - artık dual API kullanılıyor
    
    # ======================================
    # POPÜLER DÖVİZLER (15 adet)
    # Android uygulamada gösterilecek
    # ======================================
    POPULAR_CURRENCIES = [
        "USD",  # Dolar
        "EUR",  # Euro
        "GBP",  # Sterlin
        "JPY",  # Japon Yeni
        "CHF",  # İsviçre Frangı
        "CNY",  # Çin Yuanı
        "CAD",  # Kanada Doları
        "AUD",  # Avustralya Doları
        "DKK",  # Danimarka Kronu
        "SEK",  # İsveç Kronu
        "NOK",  # Norveç Kronu
        "SAR",  # Suudi Arabistan Riyali
        "QAR",  # Katar Riyali
        "KWD",  # Kuveyt Dinarı
        "AED"   # BAE Dirhemi
    ]
    
    # ======================================
    # POPÜLER ALTINLAR (5 adet)
    # Android uygulamada gösterilecek
    # ======================================
    POPULAR_GOLDS = [
        "Gram Altın",
        "Çeyrek Altın",
        "Yarım Altın",
        "Tam Altın",
        "Cumhuriyet Altını"
    ]
    
    # ======================================
    # GÜMÜŞ (1 adet)
    # ======================================
    SILVER_NAME = "Gümüş"
    
    # ======================================
    # DEPRECATED (Geriye uyumluluk için)
    # Artık kullanılmıyor ama eski kod referans edebilir
    # ======================================
    DATABASE_URL = None  # PostgreSQL kullanılmıyor
    DB_HOST = None
    DB_PORT = None
    DB_USER = None
    DB_PASSWORD = None
    DB_NAME = None
    COLLECTAPI_TOKEN = None  # Artık finans.truncgil.com kullanılıyor
    
    # Eski liste isimleri (geriye uyumluluk)
    CURRENCIES_LIST = POPULAR_CURRENCIES
    GOLD_FORMATS = POPULAR_GOLDS
    SILVER_FORMATS = [SILVER_NAME]
