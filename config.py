"""
KuraBak Backend Configuration
==============================

Architecture:
- Redis-only (no PostgreSQL)
- Dual API support (V3 + V4 fallback)
- Auto-update every 2 minutes
- Circuit breaker protection
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

# ======================================
# ENVIRONMENT VALIDATION
# ======================================

def validate_environment():
    """
    Kritik environment variable'ları kontrol et
    Eksikse uyarı ver veya default değer kullan
    """
    warnings = []
    
    # Redis URL kontrolü
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        warnings.append("⚠️ REDIS_URL bulunamadı, memory fallback kullanılacak")
    
    # CORS origin kontrolü
    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*")
    if allowed_origins == "*":
        warnings.append("⚠️ ALLOWED_ORIGINS='*' (tüm originler kabul ediliyor, production için önerilmez)")
    
    # Log level kontrolü
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    if log_level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        warnings.append(f"⚠️ Geçersiz LOG_LEVEL: {log_level}, INFO kullanılacak")
    
    # Uyarıları göster
    for warning in warnings:
        logger.warning(warning)
    
    return len(warnings) == 0

# ======================================
# CONFIGURATION CLASS
# ======================================

class Config:
    """
    KuraBak Backend Ana Yapılandırması
    
    Environment Variables:
    - REDIS_URL: Redis connection string (opsiyonel, yoksa memory fallback)
    - ALLOWED_ORIGINS: CORS allowed origins (default: *)
    - LOG_LEVEL: Logging seviyesi (default: INFO)
    - PORT: Server port (default: 5001)
    - FLASK_ENV: development/production (default: production)
    """
    
    # ======================================
    # REDIS CONFIGURATION
    # ======================================
    REDIS_URL = os.environ.get("REDIS_URL")
    REDIS_SOCKET_TIMEOUT = 5  # saniye
    REDIS_SOCKET_CONNECT_TIMEOUT = 5  # saniye
    REDIS_RETRY_ON_TIMEOUT = True
    REDIS_MAX_CONNECTIONS = 10
    
    # ======================================
    # CACHE SETTINGS
    # ======================================
    # ÖNEMLI: TTL, UPDATE_INTERVAL'dan uzun olmalı!
    UPDATE_INTERVAL = 120  # 2 dakika (API fetch aralığı)
    CACHE_TTL = 240        # 4 dakika (TTL > UPDATE_INTERVAL * 2)
    
    # Açıklama:
    # UPDATE_INTERVAL = 120s → Her 2 dakikada API çağrısı
    # CACHE_TTL = 240s → Cache 4 dakika canlı kalır
    # Böylece bir güncelleme başarısız olsa bile eski veri hâlâ geçerli
    
    # ======================================
    # API CONFIGURATION (DUAL API SUPPORT)
    # ======================================
    API_V4_URL = "https://finans.truncgil.com/v4/today.json"
    API_V3_URL = "https://finans.truncgil.com/v3/today.json"
    
    # API Timeout ayarları (tuple: connect, read)
    API_TIMEOUT_CONNECT = 12  # Bağlantı timeout (saniye)
    API_TIMEOUT_READ = 25     # Okuma timeout (saniye)
    API_TIMEOUT = (API_TIMEOUT_CONNECT, API_TIMEOUT_READ)
    
    # Retry ayarları (urllib3.Retry için)
    API_RETRY_TOTAL = 3
    API_RETRY_BACKOFF_FACTOR = 1  # 1s, 2s, 4s
    API_RETRY_STATUS_FORCELIST = [429, 500, 502, 503, 504]
    
    # ======================================
    # CIRCUIT BREAKER SETTINGS
    # ======================================
    CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5  # Kaç başarısızlıkta devre açılır
    CIRCUIT_BREAKER_TIMEOUT = 300          # Kaç saniye sonra test edilir (5 dakika)
    CIRCUIT_BREAKER_HALF_OPEN_SUCCESS_THRESHOLD = 3  # Test modunda kaç başarı gerekir
    
    # ======================================
    # RATE LIMITING
    # ======================================
    # General API endpoints
    RATE_LIMIT_REQUESTS = 60  # İstek sayısı
    RATE_LIMIT_WINDOW = 60    # Saniye cinsinden
    
    # /api/update endpoint (özel)
    UPDATE_RATE_LIMIT_REQUESTS = 5   # İstek sayısı
    UPDATE_RATE_LIMIT_WINDOW = 60    # Saniye cinsinden
    
    # ======================================
    # DATA CONFIGURATION
    # ======================================
    
    # Popüler dövizler (15 adet)
    POPULAR_CURRENCIES = [
        "USD",  # Amerikan Doları
        "EUR",  # Euro
        "GBP",  # İngiliz Sterlini
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
    
    # Popüler altınlar (5 adet)
    POPULAR_GOLDS = {
        "GRA": "Gram Altın",
        "CEYREKALTIN": "Çeyrek Altın",
        "YARIMALTIN": "Yarım Altın",
        "TAMALTIN": "Tam Altın",
        "CUMHURIYETALTINI": "Cumhuriyet Altını"
    }
    
    # Gümüş
    SILVER_CODE = "GUMUS"
    SILVER_NAME = "Gümüş"
    
    # ======================================
    # REDIS KEYS
    # ======================================
    REDIS_KEY_CURRENCIES = "kurabak:currencies:all"
    REDIS_KEY_GOLDS = "kurabak:golds:all"
    REDIS_KEY_SILVERS = "kurabak:silvers:all"
    
    # ======================================
    # HEALTH CHECK THRESHOLDS
    # ======================================
    HEALTH_MIN_CURRENCIES = 10  # En az 10 döviz olmalı
    HEALTH_MIN_GOLDS = 3        # En az 3 altın olmalı
    HEALTH_MIN_SILVERS = 1      # En az 1 gümüş olmalı
    HEALTH_MAX_DATA_AGE = 300   # Veri 5 dakikadan eski olmamalı (saniye)
    
    # ======================================
    # LOGGING
    # ======================================
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    
    # ======================================
    # SERVER SETTINGS
    # ======================================
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", 5001))
    DEBUG = os.environ.get("FLASK_ENV") == "development"
    
    # ======================================
    # CORS SETTINGS
    # ======================================
    # Environment'tan al, yoksa tüm originlere izin ver (⚠️ production'da değiştir)
    ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")
    
    # Örnek production ayarı:
    # ALLOWED_ORIGINS=https://kurabak.com,https://www.kurabak.com,https://app.kurabak.com
    
    # ======================================
    # SCHEDULER SETTINGS
    # ======================================
    SCHEDULER_MAX_WORKERS = 1  # Tek worker yeterli (tek API çağrısı)
    SCHEDULER_JOB_COALESCE = True  # Kaçırılan job'ları birleştir
    SCHEDULER_MAX_INSTANCES = 1    # Aynı anda sadece 1 instance
    SCHEDULER_MISFIRE_GRACE_TIME = 30  # 30s içinde kaçırılan job'ları çalıştır
    
    # ======================================
    # SESSION SETTINGS (HTTP)
    # ======================================
    SESSION_POOL_CONNECTIONS = 2
    SESSION_POOL_MAXSIZE = 5
    SESSION_POOL_BLOCK = False
    
    # ======================================
    # DEPRECATED (Backward Compatibility)
    # ======================================
    # Eski kodlar için geriye uyumluluk
    # Yeni kod bunları kullanmamalı
    
    # Legacy API
    API_BASE_URL = API_V4_URL  # Deprecated: Artık dual API kullan
    
    # Legacy database (PostgreSQL artık yok)
    DATABASE_URL = None
    DB_HOST = None
    DB_PORT = None
    DB_USER = None
    DB_PASSWORD = None
    DB_NAME = None
    
    # Legacy API token
    COLLECTAPI_TOKEN = None  # Artık finans.truncgil.com kullanılıyor
    
    # Legacy list names
    CURRENCIES_LIST = POPULAR_CURRENCIES
    GOLD_FORMATS = list(POPULAR_GOLDS.values())
    SILVER_FORMATS = [SILVER_NAME]
    
    # ======================================
    # VALIDATION
    # ======================================
    @classmethod
    def validate(cls):
        """
        Konfigurasyon doğrulaması
        Çelişki veya hata varsa uyarı ver
        """
        issues = []
        
        # TTL kontrolü
        if cls.CACHE_TTL <= cls.UPDATE_INTERVAL:
            issues.append(
                f"⚠️ CACHE_TTL ({cls.CACHE_TTL}s) <= UPDATE_INTERVAL ({cls.UPDATE_INTERVAL}s). "
                f"Cache, güncelleme aralığından uzun olmalı!"
            )
        
        # Timeout kontrolü
        if cls.API_TIMEOUT_CONNECT + cls.API_TIMEOUT_READ > cls.UPDATE_INTERVAL:
            issues.append(
                f"⚠️ Total API timeout ({cls.API_TIMEOUT_CONNECT + cls.API_TIMEOUT_READ}s) "
                f"> UPDATE_INTERVAL ({cls.UPDATE_INTERVAL}s). "
                f"Timeout, update interval'dan kısa olmalı!"
            )
        
        # Health threshold kontrolü
        if cls.HEALTH_MAX_DATA_AGE > cls.CACHE_TTL:
            issues.append(
                f"⚠️ HEALTH_MAX_DATA_AGE ({cls.HEALTH_MAX_DATA_AGE}s) > CACHE_TTL ({cls.CACHE_TTL}s). "
                f"Sağlık kontrolü cache TTL'den kısa olmalı!"
            )
        
        # Log issues
        for issue in issues:
            logger.warning(issue)
        
        return len(issues) == 0
    
    @classmethod
    def display(cls):
        """
        Konfigurasyon özetini göster (startup'ta kullanılır)
        """
        redis_status = "Enabled" if cls.REDIS_URL else "Disabled (memory fallback)"
        
        print("=" * 60)
        print("📋 KURABAK BACKEND CONFIGURATION")
        print("=" * 60)
        print(f"🔧 Environment: {os.environ.get('FLASK_ENV', 'production')}")
        print(f"🌍 Host: {cls.HOST}:{cls.PORT}")
        print(f"💾 Redis: {redis_status}")
        print(f"⏱️  Update Interval: {cls.UPDATE_INTERVAL}s ({cls.UPDATE_INTERVAL / 60:.1f} min)")
        print(f"📦 Cache TTL: {cls.CACHE_TTL}s ({cls.CACHE_TTL / 60:.1f} min)")
        print(f"🔌 API Timeout: {cls.API_TIMEOUT_CONNECT}s connect, {cls.API_TIMEOUT_READ}s read")
        print(f"🔴 Circuit Breaker: {cls.CIRCUIT_BREAKER_FAILURE_THRESHOLD} failures → {cls.CIRCUIT_BREAKER_TIMEOUT}s timeout")
        print(f"🌐 CORS Origins: {cls.ALLOWED_ORIGINS}")
        print(f"📊 Log Level: {cls.LOG_LEVEL}")
        print("=" * 60)

# ======================================
# STARTUP VALIDATION
# ======================================

# Config'i validate et
Config.validate()
