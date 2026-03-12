import os

class Config:
    APP_NAME = "KuraBak Backend API"
    APP_VERSION = "5.7"
    ENVIRONMENT = os.environ.get("FLASK_ENV", "production")

    DEFAULT_TIMEZONE = "Europe/Istanbul"

    API_V5_URL = "https://finance.truncgil.com/api/today.json"
    API_V5_TIMEOUT = (5, 10)

    PRICE_PROFILES = {
        "raw": {},
        "jeweler": {}
    }

    DEFAULT_PRICE_PROFILE = "jeweler"
    DEFAULT_MARKET_MARGIN = 0.0

    HAREM_PRICE_URL = "https://altin.doviz.com/harem"
    HAREM_FETCH_TIMEOUT = 10

    ZIRAAT_CURRENCY_URL = "https://kur.doviz.com/ziraat-bankasi"
    ZIRAAT_FETCH_TIMEOUT = 10

    MARGIN_UPDATE_HOUR = 0
    MARGIN_UPDATE_MINUTE = 5

    MARGIN_CALCULATION_STRATEGY = "full"
    MARGIN_SMOOTH_TRANSITION = True
    MARGIN_SMOOTH_THRESHOLD = 0.015

    STATIC_GOLD_MARGINS = {
        "CUM": 0.015,
        "ATA": 0.017,
        "HAS": 0.010,
    }

    STATIC_EXOTIC_MARGINS = {
        "AED": 0.015,
        "KWD": 0.018,
        "BHD": 0.018,
        "OMR": 0.018,
        "QAR": 0.015,
        "CNY": 0.020,
        "PLN": 0.020,
        "RON": 0.020,
        "CZK": 0.020,
        "HUF": 0.022,
        "RSD": 0.022,
        "BAM": 0.020,
        "EGP": 0.025,
        "RUB": 0.025,
    }

    FIREBASE_CREDENTIALS_PATH = os.environ.get(
        "FIREBASE_CREDENTIALS_PATH",
        "/etc/secrets/firebase_credentials.json"
    )
    FIREBASE_NOTIFICATION_ENABLED = True
    FIREBASE_PRIORITY = "high"
    FIREBASE_SOUND = "default"

    UPDATE_INTERVAL = 60

    SNAPSHOT_HOUR = 0
    SNAPSHOT_MINUTE = 0
    SNAPSHOT_SECOND = 0

    SUPERVISOR_INTERVAL = 10

    TELEGRAM_DAILY_REPORT_HOUR = 9

    PUSH_NOTIFICATION_DAILY_HOUR = 14
    PUSH_NOTIFICATION_DAILY_MINUTE = 0

    CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
    CIRCUIT_BREAKER_TIMEOUT = 60

    CLEANUP_BACKUP_AGE_DAYS = 7
    CLEANUP_CHECK_INTERVAL = 86400

    MAINTENANCE_DEFAULT_MESSAGE = "Sistem bakımda. Veriler güncel olmayabilir."

    CPU_THRESHOLD = 80
    RAM_THRESHOLD = 95
    ALARM_COOLDOWN = 300
    ALARM_NOTIFICATION_INTERVAL = 1800
    CPU_HIGH_DURATION = 300

    ALARM_CHECK_INTERVAL = 15
    ALARM_TTL = 30 * 24 * 60 * 60
    MAX_ALARMS_PER_USER = 50

    CALENDAR_CHECK_HOUR = 8
    CALENDAR_CHECK_MINUTE = 0
    CALENDAR_BANNER_HOUR = 9
    CALENDAR_BANNER_MINUTE = 0

    NEWS_MORNING_PREPARE_HOUR = 23
    NEWS_MORNING_PREPARE_MINUTE = 55
    NEWS_MORNING_PUBLISH_HOUR = 0
    NEWS_MORNING_PUBLISH_MINUTE = 0
    NEWS_EVENING_PREPARE_HOUR = 11
    NEWS_EVENING_PREPARE_MINUTE = 55
    NEWS_EVENING_PUBLISH_HOUR = 12
    NEWS_EVENING_PUBLISH_MINUTE = 0
    NEWS_MAX_RESULTS_PER_SOURCE = 30
    NEWS_GEMINI_TIMEOUT = 30
    NEWS_BATCH_SIZE = 40

    MARKET_CLOSE_FRIDAY_HOUR = 18
    WEEKEND_REOPEN_HOUR = 0

    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    CACHE_KEYS = {
        'currencies_all': 'kurabak:currencies:raw',
        'golds_all': 'kurabak:golds:raw',
        'silvers_all': 'kurabak:silvers:raw',
        'currencies_jeweler': 'kurabak:currencies:jeweler',
        'golds_jeweler': 'kurabak:golds:jeweler',
        'silvers_jeweler': 'kurabak:silvers:jeweler',
        'backup': 'kurabak:backup:all',
        'raw_snapshot': 'kurabak:raw_snapshot',
        'jeweler_snapshot': 'kurabak:jeweler_snapshot',
        'yesterday_prices': 'kurabak:raw_snapshot',
        'yesterday_prices_jeweler': 'kurabak:jeweler_snapshot',
        'last_worker_run': 'kurabak:last_worker_run',
        'backup_timestamp': 'kurabak:backup:timestamp',
        'maintenance': 'system_maintenance',
        'banner': 'system_banner',
        'mute': 'system_mute',
        'alarm_cpu_state': 'alarm:cpu:state',
        'alarm_ram_state': 'alarm:ram:state',
        'alarm_last_notification': 'alarm:last_notification',
        'system_was_down': 'system_was_down',
        'calendar_last_check': 'calendar:last_check',
        'calendar_notified_events': 'calendar:notified_events',
        'fcm_tokens': 'firebase:fcm_tokens',
        'fcm_last_notification': 'firebase:last_notification',
        'alarm_last_check': 'alarm:price:last_check',
        'market_closed_logged': 'market:closed:logged',
        'api_request_stats': 'api:request:stats',
        'circuit_breaker_state': 'circuit:breaker:state',
        'circuit_breaker_failures': 'circuit:breaker:failures',
        'circuit_breaker_last_open': 'circuit:breaker:last_open',
        'cleanup_last_run': 'cleanup:last_run',
        'news_morning_pending': 'news:morning_pending',
        'news_morning_shift': 'news:morning_shift',
        'news_evening_pending': 'news:evening_pending',
        'news_evening_shift': 'news:evening_shift',
        'news_last_update': 'news:last_update',
        'daily_bayram': 'daily:bayram',
        'dynamic_margins': 'dynamic:margins',
        'margin_last_update': 'margin:last_update',
    }

    TREND_HIGH_THRESHOLD = 5.0
    TREND_MEDIUM_THRESHOLD = 1.0

    REGIONAL_CURRENCIES = {
        "north_america": ["USD", "CAD"],
        "europe": ["EUR", "GBP", "CHF", "SEK", "NOK"],
        "middle_east": ["SAR", "AED", "KWD", "BHD", "OMR", "QAR"],
        "asia_pacific": ["CNY", "AUD"],
        "eastern_europe": ["RUB"],
        "balkans_europe": ["PLN", "RON", "CZK", "HUF", "RSD", "BAM"],
        "africa": ["EGP"]
    }

    MOBILE_CURRENCIES = [
        "USD", "EUR", "GBP", "CHF", "CAD", "AUD", "RUB",
        "SAR", "AED", "KWD", "BHD", "OMR", "QAR",
        "CNY", "SEK", "NOK",
        "PLN", "RON", "CZK", "EGP", "RSD", "HUF", "BAM"
    ]

    MOBILE_GOLDS = ["GRA", "C22", "YAR", "TAM", "CUM", "ATA"]

    MOBILE_SILVER = "AG"

    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "")
    SECRET_KEY = os.environ.get("SECRET_KEY", "gizli-anahtar-degistir")

    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
    TELEGRAM_SILENT_MODE = True

    SUPERVISOR_WORKER_TIMEOUT = 600
    SUPERVISOR_WARNING_TIMEOUT = 300

    BACKUP_INTERVAL = 900
    BACKUP_TTL = 86400

    DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
