import requests
import logging
import time
from functools import wraps
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from utils.cache import set_cache

logger = logging.getLogger(__name__)

# ======================================
# OPTİMİZE EDİLMİŞ AYARLAR
# ======================================
CACHE_TTL = 600
MAX_RETRY_ATTEMPTS = 3  # Sadece decorator retry kullanılacak
API_TIMEOUT = (5, 10)   # (connect_timeout, read_timeout) - Daha gerçekçi

API_V3 = "https://finans.truncgil.com/v3/today.json"
API_V4 = "https://finans.truncgil.com/v4/today.json"

# ======================================
# OPTİMİZE EDİLMİŞ SESSION
# ======================================
session = requests.Session()

# ❌ RETRY STRATEGY KALDIRILDI - Sadece decorator retry kullanılacak
# Çünkü: İki retry mekanizması çatışıyordu (2×3=6 retry!)

adapter = HTTPAdapter(
    pool_connections=2,   # ✅ Sadece 2 host (V3 + V4)
    pool_maxsize=4,       # ✅ Her host için max 2 bağlantı
    pool_block=False
)
session.mount("http://", adapter)
session.mount("https://", adapter)


def retry_on_failure(max_attempts=MAX_RETRY_ATTEMPTS):
    """
    Optimize edilmiş retry decorator
    - Exponential backoff: 1s → 2s → 4s
    - Sadece bağlantı hatalarında retry
    - JSON hatalarında retry YOK (boşuna deneme)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                
                except requests.exceptions.Timeout as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(f"❌ {func.__name__} timeout (tüm denemeler tükendi)")
                        raise
                    
                    wait_time = 2 ** (attempt - 1)  # 1s, 2s, 4s
                    logger.warning(
                        f"⚠️ {func.__name__} timeout (deneme {attempt}/{max_attempts}), "
                        f"{wait_time}s sonra tekrar denenecek..."
                    )
                    time.sleep(wait_time)
                
                except requests.exceptions.ConnectionError as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(f"❌ {func.__name__} bağlantı hatası (tüm denemeler tükendi)")
                        raise
                    
                    wait_time = 2 ** (attempt - 1)
                    logger.warning(
                        f"⚠️ {func.__name__} bağlantı hatası (deneme {attempt}/{max_attempts}), "
                        f"{wait_time}s sonra tekrar denenecek..."
                    )
                    time.sleep(wait_time)
                
                except requests.exceptions.JSONDecodeError as e:
                    # ❌ JSON hatası - RETRY YAPMA! API bozuk döndürüyor
                    logger.error(f"❌ API bozuk JSON döndürdü: {str(e)[:100]}")
                    raise
                
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    logger.error(f"❌ {func.__name__} beklenmeyen hata: {e}")
                    raise
                
                except Exception as e:
                    logger.error(f"❌ {func.__name__} kritik hata: {e}", exc_info=True)
                    raise
            
            # Bu noktaya normalde gelmemeli ama yine de
            if last_exception:
                raise last_exception
            
        return wrapper
    return decorator


def get_safe_float(value):
    """Float dönüşümü - daha güvenli"""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        
        value_str = str(value).strip()
        value_str = value_str.replace("%", "").replace("$", "").replace(" ", "")
        
        # Türk formatı: 1.234,56 → 1234.56
        if '.' in value_str and ',' in value_str:
            value_str = value_str.replace(".", "").replace(",", ".")
        # Tek virgül: 123,45 → 123.45
        elif ',' in value_str:
            value_str = value_str.replace(",", ".")
        
        return float(value_str)
    except Exception as e:
        logger.warning(f"⚠️ Float dönüşüm hatası: '{value}' → {e}")
        return 0.0


def parse_update_date(date_str):
    """Tarih parse - hata toleranslı"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logger.warning(f"⚠️ Tarih parse hatası: '{date_str}' → {e}")
        return None


@retry_on_failure(max_attempts=3)
def fetch_api_data(url, api_name):
    """
    API'den veri çek - Optimize edilmiş versiyon
    
    Değişiklikler:
    - Timeout: (5, 10) → 5s bağlantı, 10s okuma
    - Session retry KALDIRILDI
    - User-Agent güncellendi
    """
    headers = {
        "User-Agent": "KuraBak-Backend/2.0 (Python/requests)",
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive"
    }
    
    logger.debug(f"🔄 {api_name} API çağrılıyor: {url}")
    
    # ✅ Timeout tuple: (connect_timeout, read_timeout)
    response = session.get(url, headers=headers, timeout=API_TIMEOUT)
    response.raise_for_status()
    
    # JSON parse - hata varsa JSONDecodeError fırlatır (retry yok!)
    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError as e:
        logger.error(f"❌ {api_name} API bozuk JSON döndürdü!")
        logger.debug(f"Response text (ilk 500 char): {response.text[:500]}")
        raise
    
    # Update_Date kontrolü
    update_date_str = data.get("Update_Date")
    if not update_date_str:
        logger.warning(f"⚠️ {api_name} API'de Update_Date yok!")
        return None, None
    
    update_date = parse_update_date(update_date_str)
    if not update_date:
        logger.warning(f"⚠️ {api_name} geçersiz tarih: {update_date_str}")
        return None, None
    
    logger.info(f"✅ {api_name} API başarılı - Tarih: {update_date_str}")
    return data, update_date


def get_latest_api_data():
    """
    V4 → V3 fallback mantığı
    
    Değişiklik: Daha detaylı loglama
    """
    # Önce V4 dene
    try:
        v4_data, v4_date = fetch_api_data(API_V4, "V4")
        if v4_data:
            logger.info("🎯 V4 API kullanılıyor")
            return v4_data, "V4"
    except Exception as e:
        logger.error(f"❌ V4 API başarısız: {type(e).__name__}: {str(e)[:100]}")
    
    # V4 başarısız, V3'e geç
    logger.warning("⚠️ V4 başarısız, V3'e geçiliyor...")
    
    try:
        v3_data, v3_date = fetch_api_data(API_V3, "V3")
        if v3_data:
            logger.info("🎯 V3 API kullanılıyor (V4 fallback)")
            return v3_data, "V3"
    except Exception as e:
        logger.error(f"❌ V3 API başarısız: {type(e).__name__}: {str(e)[:100]}")
    
    # Her ikisi de başarısız
    logger.error("❌ V4 ve V3 API'leri başarısız!")
    return None, None


def process_currencies_from_data(data, api_source):
    """
    API verisinden döviz listesi oluştur
    
    Değişiklik: Daha iyi hata yönetimi
    """
    currency_codes = [
        "USD", "EUR", "GBP", "JPY", "CHF",
        "CNY", "CAD", "AUD", "DKK", "SEK",
        "NOK", "SAR", "QAR", "KWD", "AED"
    ]
    
    currencies = []
    skipped_count = 0
    
    for code in currency_codes:
        if code not in data:
            logger.debug(f"⚠️ {code} API'de yok")
            skipped_count += 1
            continue
        
        item = data[code]
        
        # Type kontrolü
        if item.get("Type") != "Currency":
            logger.debug(f"⚠️ {code} Type != Currency: {item.get('Type')}")
            skipped_count += 1
            continue
        
        # Veri çıkarma
        name = item.get("Name", code)
        selling = get_safe_float(item.get("Selling", 0))
        buying = get_safe_float(item.get("Buying", 0))
        change_percent = get_safe_float(item.get("Change", 0))
        
        # Validasyon
        if selling <= 0:
            logger.warning(f"⚠️ {code} geçersiz fiyat: {selling}")
            skipped_count += 1
            continue
        
        # Rate formatlama
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
    
    if skipped_count > 0:
        logger.info(f"ℹ️ {skipped_count} döviz atlandı")
    
    return currencies


def fetch_currencies_to_cache():
    """
    Ana fonksiyon: API'den çek → İşle → Redis'e yaz
    
    Değişiklik: Daha iyi hata yönetimi ve loglama
    """
    try:
        # 1. API'den veri çek
        data, api_source = get_latest_api_data()
        
        if not data:
            logger.error("❌ Hiçbir API'den veri alınamadı!")
            return False
        
        update_date = data.get("Update_Date", "Bilinmiyor")
        
        # 2. Veriyi işle
        currencies = process_currencies_from_data(data, api_source)
        
        if not currencies:
            logger.error("❌ Hiç döviz verisi işlenemedi!")
            return False
        
        # 3. Redis'e yaz
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
        logger.error(f"❌ fetch_currencies_to_cache kritik hata: {e}", exc_info=True)
        return False


def fetch_currencies():
    """Public API - geriye uyumluluk için"""
    return fetch_currencies_to_cache()


def cleanup_database():
    """Deprecated - PostgreSQL yok artık"""
    logger.debug("ℹ️ cleanup_database çağrıldı (no-op)")
    return True
