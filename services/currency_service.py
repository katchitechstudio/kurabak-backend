import requests
import logging
import time
from functools import wraps
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from utils.cache import set_cache

logger = logging.getLogger(__name__)

CACHE_TTL = 300
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 1
API_TIMEOUT = 30

API_V3 = "https://finans.truncgil.com/v3/today.json"
API_V4 = "https://finans.truncgil.com/v4/today.json"

session = requests.Session()
retry_strategy = Retry(
    total=2,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(
    max_retries=retry_strategy,
    pool_connections=10,
    pool_maxsize=20,
    pool_block=False
)
session.mount("http://", adapter)
session.mount("https://", adapter)


def retry_on_failure(max_attempts=MAX_RETRY_ATTEMPTS, delay=RETRY_DELAY):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    if attempt == max_attempts:
                        logger.error(f"❌ {func.__name__} başarısız (tüm denemeler tükendi): {e}")
                        raise
                    
                    wait_time = delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"⚠️ {func.__name__} başarısız (deneme {attempt}/{max_attempts}), "
                        f"{wait_time}s sonra tekrar denenecek... Hata: {e}"
                    )
                    time.sleep(wait_time)
                except Exception as e:
                    logger.error(f"❌ {func.__name__} beklenmeyen hata: {e}", exc_info=True)
                    raise
            return None
        return wrapper
    return decorator


def get_safe_float(value):
    try:
        if isinstance(value, (int, float)):
            return float(value)
        
        value_str = str(value).strip()
        value_str = value_str.replace("%", "").replace("$", "").replace(" ", "")
        
        if '.' in value_str and ',' in value_str:
            value_str = value_str.replace(".", "").replace(",", ".")
        else:
            value_str = value_str.replace(",", ".")
        
        return float(value_str)
    except Exception as e:
        logger.warning(f"Float dönüşüm hatası: {value} → {e}")
        return 0.0


def parse_update_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logger.warning(f"Tarih parse hatası: {date_str} → {e}")
        return None


@retry_on_failure(max_attempts=3, delay=1)
def fetch_api_data(url, api_name):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    
    logger.debug(f"🔄 {api_name} API'den veri çekiliyor...")
    
    response = session.get(url, headers=headers, timeout=API_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    
    update_date_str = data.get("Update_Date")
    if not update_date_str:
        logger.warning(f"⚠️ {api_name} API'de Update_Date yok!")
        return None, None
    
    update_date = parse_update_date(update_date_str)
    if not update_date:
        logger.warning(f"⚠️ {api_name} API'de geçersiz tarih: {update_date_str}")
        return None, None
    
    logger.info(f"✅ {api_name} API başarılı - Tarih: {update_date_str}")
    return data, update_date


def get_latest_api_data():
    v4_data, v4_date = None, None
    v3_data, v3_date = None, None
    
    try:
        v4_data, v4_date = fetch_api_data(API_V4, "V4")
    except Exception as e:
        logger.error(f"❌ V4 API başarısız (tüm denemeler tükendi): {e}")
    
    if v4_data:
        logger.info("🎯 V4 API kullanılıyor")
        return v4_data, "V4"
    
    logger.warning("⚠️ V4 başarısız, V3'e geçiliyor...")
    
    try:
        v3_data, v3_date = fetch_api_data(API_V3, "V3")
    except Exception as e:
        logger.error(f"❌ V3 API başarısız (tüm denemeler tükendi): {e}")
    
    if v3_data:
        logger.info("🎯 V3 API kullanılıyor (V4 başarısız)")
        return v3_data, "V3"
    
    logger.error("❌ Her iki API de başarısız!")
    return None, None


def process_currencies_from_data(data, api_source):
    currency_codes = [
        "USD", "EUR", "GBP", "JPY", "CHF",
        "CNY", "CAD", "AUD", "DKK", "SEK",
        "NOK", "SAR", "QAR", "KWD", "AED"
    ]
    
    currencies = []
    
    for code in currency_codes:
        if code not in data:
            logger.warning(f"⚠️ {code} API'de bulunamadı")
            continue
        
        item = data[code]
        
        if item.get("Type") != "Currency":
            logger.warning(f"⚠️ {code} Type != Currency: {item.get('Type')}")
            continue
        
        name = item.get("Name", code)
        selling = get_safe_float(item.get("Selling", 0))
        buying = get_safe_float(item.get("Buying", 0))
        change_percent = get_safe_float(item.get("Change", 0))
        
        if selling <= 0:
            logger.warning(f"⚠️ {code} geçersiz fiyat: {selling}")
            continue
        
        if selling >= 10:
            rate = round(selling, 2)
        else:
            rate = round(selling, 4)
        
        currencies.append({
            "code": code,
            "name": name,
            "rate": rate,
            "change_percent": round(change_percent, 2)
        })
        
        logger.debug(f"✅ {code} ({name}): {rate:.4f} TL ({change_percent:+.2f}%)")
    
    return currencies


def fetch_currencies_to_cache():
    try:
        data, api_source = get_latest_api_data()
        
        if not data:
            logger.error("❌ Hiçbir API'den veri çekilemedi!")
            return False
        
        update_date = data.get("Update_Date", "Bilinmiyor")
        
        currencies = process_currencies_from_data(data, api_source)
        
        if not currencies:
            logger.error("❌ Hiç döviz verisi işlenemedi!")
            return False
        
        cache_data = {
            "success": True,
            "count": len(currencies),
            "data": currencies,
            "api_source": api_source,
            "update_date": update_date
        }
        
        set_cache('kurabak:currencies:all', cache_data, CACHE_TTL)
        logger.info(f"✅ {len(currencies)} döviz Redis'e yazıldı ({api_source} API, {update_date})")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Döviz çekme hatası: {e}", exc_info=True)
        return False


def fetch_currencies():
    return fetch_currencies_to_cache()


def cleanup_database():
    logger.info("ℹ️ cleanup_database çağrıldı ama PostgreSQL kullanılmıyor")
    return True
