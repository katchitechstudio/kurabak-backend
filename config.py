"""
KuraBak Backend Configuration - PRODUCTION READY
================================================
✅ V5 Primary, V4/V3 Fallback
✅ Regional Currencies (21 döviz)
✅ Agresif Circuit Breaker
✅ RAM Cache Limiti
✅ DDoS Koruması
"""

import os
import logging

logger = logging.getLogger(__name__)

class Config:
    # ======================================
    # API CONFIGURATION (TRIPLE FALLBACK)
    # ======================================
    # 🚀 PRIMARY (YENİ NESİL - 92ms)
    API_V5_URL = "https://finance.truncgil.com/api/today.json"
    
    # 🛡️ FALLBACKS (6+ saniye)
    API_V4_URL = "https://finans.truncgil.com/v4/today.json"
    API_V3_URL = "https://finans.truncgil.com/v3/today.json"
    
    # Timeout (V5 daha hızlı, daha kısa timeout)
    API_V5_TIMEOUT = (5, 10)   # 5s connect, 10s read
    API_V4_TIMEOUT = (8, 15)   # 8s connect, 15s read
    API_V3_TIMEOUT = (8, 15)   # 8s connect, 15s read
    
    # Retry ayarları
    API_RETRY_TOTAL = 2
    API_RETRY_BACKOFF = 0.3
    
    # ======================================
    # CIRCUIT BREAKER (AGRESIF)
    # ======================================
    CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3  # 3 hata
    CIRCUIT_BREAKER_TIMEOUT = 120          # 2 dakika ban
    CIRCUIT_BREAKER_HALF_OPEN_SUCCESS = 2  # 2 başarılı test
    
    # ======================================
    # CACHE SETTINGS
    # ======================================
    UPDATE_INTERVAL = 120  # 2 dakika
    CACHE_TTL = 300        # 5 dakika
    
    # Bayat veri toleransı (API çökerse eski veri göster)
    STALE_CACHE_MAX_AGE = 600  # 10 dakika
    
    # RAM Cache limiti (memory leak önleme)
    RAM_CACHE_MAX_ENTRIES = 100
    RAM_CACHE_CLEANUP_INTERVAL = 300  # 5 dakika
    
    # ======================================
    # REDIS CONFIGURATION
    # ======================================
    REDIS_URL = os.environ.get("REDIS_URL")
    REDIS_SOCKET_TIMEOUT = 3
    REDIS_SOCKET_CONNECT_TIMEOUT = 3
    REDIS_RETRY_ON_TIMEOUT = True
    REDIS_MAX_CONNECTIONS = 20
    
    # ======================================
    # RATE LIMITING
    # ======================================
    # Normal kullanıcılar
    RATE_LIMIT_REQUESTS = 60
    RATE_LIMIT_WINDOW = 60
    
    # Agresif kullanıcılar (10 saniyede 100+ istek)
    RATE_LIMIT_AGGRESSIVE_THRESHOLD = 100
    RATE_LIMIT_AGGRESSIVE_WINDOW = 10
    RATE_LIMIT_AGGRESSIVE_BAN_DURATION = 3600  # 1 saat ban
    
    # ======================================
    # DATA CONFIGURATION (REGIONAL)
    # ======================================
    # 🌍 BÖLGESEL DÖVİZLER (21 adet)
    REGIONAL_CURRENCIES = {
        "north_america": ["USD", "CAD"],
        "europe": ["EUR", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "HUF"],
        "east_europe": ["RUB", "AZN", "BGN", "RON"],
        "middle_east": ["SAR", "AED", "KWD", "QAR"],
        "asia_pacific": ["CNY", "AUD"]
    }
    
    # Tüm dövizler (flat list)
    ALL_CURRENCIES = [
        "USD", "CAD",  # Kuzey Amerika
        "EUR", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "HUF",  # Avrupa
        "RUB", "AZN", "BGN", "RON",  # Doğu Avrupa
        "SAR", "AED", "KWD", "QAR",  # Orta Doğu
        "CNY", "AUD"  # Asya-Pasifik
    ]
    
    # Popüler altınlar (değişmedi)
    POPULAR_GOLDS = {
        "GRA": "Gram Altın",
        "CEYREKALTIN": "Çeyrek Altın",
        "YARIMALTIN": "Yarım Altın",
        "TAMALTIN": "Tam Altın",
        "CUMHURIYETALTINI": "Cumhuriyet Altını"
    }
    
    SILVER_CODE = "GUMUS"
    
    # ======================================
    # FLEXIBLE FORMAT SUPPORT
    # ======================================
    POSSIBLE_DATA_KEYS = ["Rates", "Data", "rates", "data", "items"]
    POSSIBLE_META_KEYS = ["Meta_Data", "metadata", "meta"]
    POSSIBLE_DATE_KEYS = ["Update_Date", "update_date", "Updated"]
    
    # ======================================
    # HEALTH CHECK
    # ======================================
    HEALTH_MIN_CURRENCIES = 15  # 21'in çoğu olmalı
    HEALTH_MIN_GOLDS = 3
    HEALTH_MIN_SILVERS = 1
    HEALTH_MAX_DATA_AGE = 300  # 5 dakika
    
    # ======================================
    # SCHEDULER
    # ======================================
    SCHEDULER_MAX_WORKERS = 1
    SCHEDULER_JOB_COALESCE = True
    SCHEDULER_MAX_INSTANCES = 1
    
    # ======================================
    # LOGGING & SERVER
    # ======================================
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", 5001))
    DEBUG = os.environ.get("FLASK_ENV") == "development"
    ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")
    
    # ======================================
    # VALIDATION
    # ======================================
    @classmethod
    def validate(cls):
        """Kritik validasyon"""
        if cls.CACHE_TTL <= cls.UPDATE_INTERVAL:
            raise ValueError(
                f"🔴 CRITICAL: CACHE_TTL ({cls.CACHE_TTL}s) must be > UPDATE_INTERVAL ({cls.UPDATE_INTERVAL}s)"
            )
        
        # Döviz sayısı kontrolü
        if len(cls.ALL_CURRENCIES) != 21:
            logger.warning(f"⚠️ Döviz sayısı 21 olmalı, şu an: {len(cls.ALL_CURRENCIES)}")
        
        return True
    
    @classmethod
    def display(cls):
        """Başlangıç banner'ı"""
        print("\n" + "=" * 70)
        print("🚀 KURABAK BACKEND - PRODUCTION READY")
        print("=" * 70)
        print(f"⚡ Primary API: V5 (timeout: {cls.API_V5_TIMEOUT[0]}+{cls.API_V5_TIMEOUT[1]}s)")
        print(f"🛡️  Fallback: V4 → V3 → Stale Cache")
        print(f"🔴 Circuit Breaker: {cls.CIRCUIT_BREAKER_FAILURE_THRESHOLD} fails → {cls.CIRCUIT_BREAKER_TIMEOUT}s")
        print(f"🌍 Currencies: {len(cls.ALL_CURRENCIES)} (Regional)")
        print(f"📦 Cache TTL: {cls.CACHE_TTL}s (Update: {cls.UPDATE_INTERVAL}s)")
        print(f"💾 Redis: {'✅ Enabled' if cls.REDIS_URL else '⚠️ RAM Fallback'}")
        print(f"📊 Log Level: {cls.LOG_LEVEL}")
        print("=" * 70 + "\n")

Config.validate()
