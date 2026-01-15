"""
KuraBak Backend Configuration - PRODUCTION READY
================================================
✅ V5 Primary, V4/V3 Fallback
✅ Regional Currencies (21 döviz)
✅ Agresif Circuit Breaker
✅ RAM Cache Limiti
✅ DDoS Koruması
✅ Telegram Monitoring
✅ Health Check System
✅ Enhanced Security
✅ No Hardcoded Secrets
"""

import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SecurityConfig:
    """Güvenlik ile ilgili konfigürasyonlar"""
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    redis_url: Optional[str] = None
    allowed_origins: List[str] = None
    secret_key: Optional[str] = None
    
    def __post_init__(self):
        if self.allowed_origins is None:
            self.allowed_origins = ["*"]
    
    def has_telegram_config(self) -> bool:
        """Telegram config tam mı?"""
        return bool(self.telegram_bot_token and self.telegram_chat_id)
    
    def has_redis(self) -> bool:
        """Redis config var mı?"""
        return bool(self.redis_url)
    
    def validate_secrets(self) -> List[str]:
        """Eksik güvenlik config'lerini kontrol et"""
        warnings = []
        
        if not self.telegram_bot_token:
            warnings.append("TELEGRAM_BOT_TOKEN eksik - monitoring devre dışı")
        
        if not self.telegram_chat_id:
            warnings.append("TELEGRAM_CHAT_ID eksik - monitoring devre dışı")
        
        if not self.secret_key and Config.is_production():
            warnings.append("SECRET_KEY eksik - production'da önerilir")
        
        return warnings

class Config:
    # ======================================
    # SERVER & DEPLOYMENT
    # ======================================
    APP_NAME = "KuraBak Backend"
    APP_VERSION = "2.0.0"
    ENVIRONMENT = os.environ.get("FLASK_ENV", "production")
    DEBUG = ENVIRONMENT == "development"
    
    # Server Configuration
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", 5001))
    WORKER_COUNT = int(os.environ.get("WORKER_COUNT", 2))
    
    # ======================================
    # SECURITY CONFIGURATION 🔒
    # ======================================
    # ❌ NO HARDCODED SECRETS - ENVIRONMENT VARIABLES ONLY
    SECURITY = SecurityConfig(
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID"),
        redis_url=os.environ.get("REDIS_URL"),
        allowed_origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","),
        secret_key=os.environ.get("SECRET_KEY")
    )
    
    # CORS & Security Headers
    CORS_MAX_AGE = 3600
    
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
    # TELEGRAM MONITORING 🤖
    # ======================================
    # Telegram config artık SECURITY class'ında
    
    # Monitoring Intervals
    TELEGRAM_DAILY_REPORT_HOUR = 9  # Sabah 09:00 (UTC+3)
    TELEGRAM_HEALTH_CHECK_INTERVAL = 1800  # 30 dakika
    TELEGRAM_ALERT_COOLDOWN_CRITICAL = 1800  # 30 dakika
    TELEGRAM_ALERT_COOLDOWN_WARNING = 7200  # 2 saat
    
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
    
    # Cache Keys (organizasyon için)
    CACHE_KEY_PREFIX = "kurabak:"
    CACHE_KEYS = {
        'currencies_all': f"{CACHE_KEY_PREFIX}currencies:all",
        'golds_all': f"{CACHE_KEY_PREFIX}golds:all",
        'silvers_all': f"{CACHE_KEY_PREFIX}silvers:all",
        'summary': f"{CACHE_KEY_PREFIX}summary",
        'metrics': f"{CACHE_KEY_PREFIX}metrics",
        'circuit_breaker': f"{CACHE_KEY_PREFIX}circuit:breaker"
    }
    
    # ======================================
    # REDIS CONFIGURATION
    # ======================================
    # Redis config artık SECURITY class'ında
    REDIS_SOCKET_TIMEOUT = 3
    REDIS_SOCKET_CONNECT_TIMEOUT = 3
    REDIS_RETRY_ON_TIMEOUT = True
    REDIS_MAX_CONNECTIONS = 20
    
    # ======================================
    # RATE LIMITING & SECURITY
    # ======================================
    # Normal kullanıcılar
    RATE_LIMIT_REQUESTS = 60
    RATE_LIMIT_WINDOW = 60
    
    # Agresif kullanıcılar (10 saniyede 100+ istek)
    RATE_LIMIT_AGGRESSIVE_THRESHOLD = 100
    RATE_LIMIT_AGGRESSIVE_WINDOW = 10
    RATE_LIMIT_AGGRESSIVE_BAN_DURATION = 3600  # 1 saat ban
    
    # IP Blacklist
    IP_BLACKLIST_CLEANUP_INTERVAL = 3600  # 1 saat
    IP_BLACKLIST_MAX_ENTRIES = 1000
    
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
    # HEALTH CHECK & MONITORING
    # ======================================
    HEALTH_MIN_CURRENCIES = 15  # 21'in çoğu olmalı
    HEALTH_MIN_GOLDS = 3
    HEALTH_MIN_SILVERS = 1
    HEALTH_MAX_DATA_AGE = 300  # 5 dakika
    
    # Performance thresholds
    HEALTH_MAX_RESPONSE_TIME = 3.0  # 3 saniye
    HEALTH_MIN_SUCCESS_RATE = 95.0  # %95
    
    # Health check intervals
    HEALTH_CHECK_INTERNAL = 60  # 1 dakika (internal)
    HEALTH_CHECK_EXTERNAL = 300  # 5 dakika (external services)
    
    # ======================================
    # SCHEDULER
    # ======================================
    SCHEDULER_MAX_WORKERS = 1
    SCHEDULER_JOB_COALESCE = True
    SCHEDULER_MAX_INSTANCES = 1
    SCHEDULER_MISFIRE_GRACE_TIME = 30
    
    # ======================================
    # LOGGING
    # ======================================
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    
    # File logging (production only)
    LOG_FILE = os.environ.get("LOG_FILE", "kurabak_backend.log")
    LOG_MAX_BYTES = 10485760  # 10MB
    LOG_BACKUP_COUNT = 5
    
    # ======================================
    # METRICS & ANALYTICS
    # ======================================
    METRICS_RETENTION_DAYS = 7
    METRICS_UPDATE_INTERVAL = 60  # 1 dakika
    
    # Alert thresholds
    METRICS_ALERT_HIGH_ERROR_RATE = 5.0  # %5
    METRICS_ALERT_HIGH_LATENCY = 2.0  # 2 saniye
    METRICS_ALERT_LOW_SUCCESS_RATE = 90.0  # %90
    
    # ======================================
    # TIMEZONE & LOCALE
    # ======================================
    DEFAULT_TIMEZONE = "Europe/Istanbul"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    DATE_FORMAT_SHORT = "%H:%M"
    
    # ======================================
    # ERROR HANDLING
    # ======================================
    ERROR_RETRY_ATTEMPTS = 2
    ERROR_RETRY_DELAY = 1.0
    ERROR_LOG_FULL_TRACEBACK = DEBUG
    
    # ======================================
    # MAINTENANCE MODE
    # ======================================
    MAINTENANCE_MODE = os.environ.get("MAINTENANCE_MODE", "false").lower() == "true"
    MAINTENANCE_MESSAGE = "Sistem bakımda, lütfen daha sonra tekrar deneyin."
    
    # ======================================
    # VALIDATION METHODS
    # ======================================
    @classmethod
    def validate(cls) -> bool:
        """
        Tüm kritik konfigürasyonları validate et
        Returns: bool - Tüm validasyonlar başarılı mı?
        """
        errors = []
        warnings = []
        
        # Cache TTL validasyonu
        if cls.CACHE_TTL <= cls.UPDATE_INTERVAL:
            errors.append(f"CACHE_TTL ({cls.CACHE_TTL}s) > UPDATE_INTERVAL ({cls.UPDATE_INTERVAL}s) olmalı")
        
        # Circuit Breaker validasyonu
        if cls.CIRCUIT_BREAKER_FAILURE_THRESHOLD < 2:
            errors.append(f"CIRCUIT_BREAKER_FAILURE_THRESHOLD en az 2 olmalı")
        
        if cls.CIRCUIT_BREAKER_TIMEOUT < 60:
            warnings.append(f"CIRCUIT_BREAKER_TIMEOUT ({cls.CIRCUIT_BREAKER_TIMEOUT}s) kısa, 60s+ önerilir")
        
        # Security validasyonları
        security_warnings = cls.SECURITY.validate_secrets()
        warnings.extend(security_warnings)
        
        # Döviz sayısı kontrolü
        expected_currency_count = 21
        if len(cls.ALL_CURRENCIES) != expected_currency_count:
            warnings.append(f"Döviz sayısı {expected_currency_count} olmalı, şu an: {len(cls.ALL_CURRENCIES)}")
        
        # API timeout kontrolü
        if cls.API_V5_TIMEOUT[0] >= cls.API_V4_TIMEOUT[0]:
            warnings.append("API_V5 timeout, API_V4'ten kısa olmalı (daha hızlı)")
        
        # Health check threshold'ları
        if cls.HEALTH_MIN_SUCCESS_RATE < 90.0:
            warnings.append(f"HEALTH_MIN_SUCCESS_RATE ({cls.HEALTH_MIN_SUCCESS_RATE}%) düşük, 95%+ önerilir")
        
        # Log errors
        for error in errors:
            logger.error(f"❌ Config Error: {error}")
        
        for warning in warnings:
            logger.warning(f"⚠️ Config Warning: {warning}")
        
        if errors:
            raise ValueError(f"Kritik konfigürasyon hataları: {', '.join(errors)}")
        
        # Eğer production'da ve kritik secret'lar eksikse warning log'la
        if cls.is_production():
            if not cls.SECURITY.has_telegram_config():
                logger.warning("📵 Production'da Telegram monitoring devre dışı!")
            
            if not cls.SECURITY.secret_key:
                logger.warning("🔓 Production'da SECRET_KEY eksik - güvenlik riski!")
        
        return True
    
    @classmethod
    def display(cls) -> None:
        """Başlangıç banner'ı ve config özeti"""
        import platform
        
        print("\n" + "=" * 70)
        print(f"🚀 {cls.APP_NAME} v{cls.APP_VERSION}")
        print("=" * 70)
        print(f"📱 Environment: {cls.ENVIRONMENT.upper()}")
        print(f"🐍 Python: {platform.python_version()}")
        print(f"🌐 Server: {cls.HOST}:{cls.PORT}")
        
        print(f"\n⚡ API Configuration:")
        print(f"  • Primary: V5 ({cls.API_V5_TIMEOUT[0]}+{cls.API_V5_TIMEOUT[1]}s)")
        print(f"  • Fallbacks: V4 → V3 → Stale Cache")
        
        print(f"\n🛡️  Circuit Breaker:")
        print(f"  • Threshold: {cls.CIRCUIT_BREAKER_FAILURE_THRESHOLD} fails")
        print(f"  • Timeout: {cls.CIRCUIT_BREAKER_TIMEOUT}s")
        
        print(f"\n🌍 Data Configuration:")
        print(f"  • Currencies: {len(cls.ALL_CURRENCIES)} regional")
        print(f"  • Golds: {len(cls.POPULAR_GOLDS)} types")
        
        print(f"\n📦 Cache & Performance:")
        print(f"  • Update Interval: {cls.UPDATE_INTERVAL}s")
        print(f"  • Cache TTL: {cls.CACHE_TTL}s")
        print(f"  • Redis: {'✅ Enabled' if cls.SECURITY.has_redis() else '⚠️ RAM Fallback'}")
        
        print(f"\n🤖 Monitoring:")
        telegram_status = "✅ Enabled" if cls.SECURITY.has_telegram_config() else "❌ Disabled"
        print(f"  • Telegram: {telegram_status}")
        print(f"  • Daily Report: {cls.TELEGRAM_DAILY_REPORT_HOUR}:00")
        
        print(f"\n📊 Health Checks:")
        print(f"  • Min Success Rate: {cls.HEALTH_MIN_SUCCESS_RATE}%")
        print(f"  • Max Response Time: {cls.HEALTH_MAX_RESPONSE_TIME}s")
        
        print(f"\n🔒 Security:")
        print(f"  • CORS Origins: {len(cls.SECURITY.allowed_origins)} allowed")
        print(f"  • Secret Key: {'✅ Set' if cls.SECURITY.secret_key else '⚠️ Not set'}")
        
        print(f"\n🔧 Technical:")
        print(f"  • Log Level: {cls.LOG_LEVEL}")
        print(f"  • Workers: {cls.WORKER_COUNT}")
        print(f"  • Timezone: {cls.DEFAULT_TIMEZONE}")
        
        print("=" * 70)
        print("✅ Configuration validated successfully")
        print("=" * 70 + "\n")
    
    @classmethod
    def get_telegram_config(cls) -> Dict[str, Any]:
        """Telegram config için düzenlenmiş dict"""
        if not cls.SECURITY.has_telegram_config():
            return {}
        
        return {
            'bot_token': cls.SECURITY.telegram_bot_token,
            'chat_id': cls.SECURITY.telegram_chat_id,
            'daily_report_hour': cls.TELEGRAM_DAILY_REPORT_HOUR,
            'alert_cooldowns': {
                'critical': cls.TELEGRAM_ALERT_COOLDOWN_CRITICAL,
                'warning': cls.TELEGRAM_ALERT_COOLDOWN_WARNING
            }
        }
    
    @classmethod
    def get_cache_config(cls) -> Dict[str, Any]:
        """Cache config için düzenlenmiş dict"""
        return {
            'ttl': cls.CACHE_TTL,
            'stale_max_age': cls.STALE_CACHE_MAX_AGE,
            'update_interval': cls.UPDATE_INTERVAL,
            'ram_max_entries': cls.RAM_CACHE_MAX_ENTRIES,
            'keys': cls.CACHE_KEYS
        }
    
    @classmethod
    def get_api_config(cls) -> Dict[str, Any]:
        """API config için düzenlenmiş dict"""
        return {
            'v5': {'url': cls.API_V5_URL, 'timeout': cls.API_V5_TIMEOUT},
            'v4': {'url': cls.API_V4_URL, 'timeout': cls.API_V4_TIMEOUT},
            'v3': {'url': cls.API_V3_URL, 'timeout': cls.API_V3_TIMEOUT},
            'retry': {'total': cls.API_RETRY_TOTAL, 'backoff': cls.API_RETRY_BACKOFF}
        }
    
    @classmethod
    def get_redis_config(cls) -> Dict[str, Any]:
        """Redis config için düzenlenmiş dict"""
        if not cls.SECURITY.has_redis():
            return {}
        
        return {
            'url': cls.SECURITY.redis_url,
            'socket_timeout': cls.REDIS_SOCKET_TIMEOUT,
            'socket_connect_timeout': cls.REDIS_SOCKET_CONNECT_TIMEOUT,
            'retry_on_timeout': cls.REDIS_RETRY_ON_TIMEOUT,
            'max_connections': cls.REDIS_MAX_CONNECTIONS
        }
    
    @classmethod
    def is_production(cls) -> bool:
        """Production ortamında mıyız?"""
        return cls.ENVIRONMENT == "production"
    
    @classmethod
    def is_development(cls) -> bool:
        """Development ortamında mıyız?"""
        return cls.ENVIRONMENT == "development"
    
    @classmethod
    def should_log_to_file(cls) -> bool:
        """File logging aktif mi?"""
        return cls.is_production() and cls.LOG_FILE

# Auto-validate on import
try:
    Config.validate()
    if not Config.DEBUG:
        Config.display()
except Exception as e:
    logger.critical(f"❌ CRITICAL: Configuration validation failed: {e}")
    if Config.is_production():
        raise
