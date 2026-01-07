"""
Currency Service - Dual API (V3 + V4) - İyileştirilmiş
Her iki API'yi kontrol eder, en güncel olanı kullanır
Redis'e direkt yazar, PostgreSQL kullanmaz

İyileştirmeler:
- Retry mekanizması ile otomatik tekrar deneme
- Connection pooling ile daha stabil bağlantı
- Exponential backoff ile akıllı bekleme
- 30 saniye timeout (yavaş API için)
- Detaylı hata loglama
"""
import requests
import logging
import time
from functools import wraps
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from utils.cache import set_cache

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 dakika
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 1
API_TIMEOUT = 30  # 30 saniye (yavaş API için)

# API Endpoints
API_V3 = "https://finans.truncgil.com/v3/today.json"
API_V4 = "https://finans.truncgil.com/v4/today.json"

# Connection pooling için session oluştur
session = requests.Session()
retry_strategy = Retry(
    total=2,  # 2 deneme (3 yerine, daha hızlı fail için)
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
    """
    Bağlantı hatası durumunda exponential backoff ile tekrar dener
    """
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
                    
                    wait_time = delay * (2 ** (attempt - 1))  # Exponential backoff
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
    """
    V3 ve V4 API'de değerler string olarak geliyor ve virgül kullanılıyor.
    Change değerleri '%0,03' formatında geliyor.
    
    Örnekler:
    - "5.953,42" → 5953.42
    - "89,85" → 89.85
    - "%0,03" → 0.03
    - "%-1,61" → -1.61
    - "$4.330,99" → 4330.99
    """
    try:
        if isinstance(value, (int, float)):
            return float(value)
        
        value_str = str(value).strip()
        
        # Gereksiz karakterleri temizle
        value_str = value_str.replace("%", "").replace("$", "").replace(" ", "")
        
        # "5.953,42" formatı (binlik ayracı nokta, ondalık virgül)
        if '.' in value_str and ',' in value_str:
            value_str = value_str.replace(".", "").replace(",", ".")
        # "89,85" formatı (sadece ondalık virgül)
        else:
            value_str = value_str.replace(",", ".")
        
        return float(value_str)
    except Exception as e:
        logger.warning(f"Float dönüşüm hatası: {value} → {e}")
        return 0.0


def parse_update_date(date_str):
    """
    Update_Date string'ini datetime objesine çevirir
    Format: "2026-01-06 18:15:54"
    
    Returns:
        datetime or None: Başarılı ise datetime, hata varsa None
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logger.warning(f"Tarih parse hatası: {date_str} → {e}")
        return None


@retry_on_failure(max_attempts=3, delay=1)
def fetch_api_data(url, api_name):
    """
    Belirtilen API'den veri çeker ve Update_Date ile birlikte döner (retry mekanizması ile)
    
    Args:
        url (str): API endpoint URL'i
        api_name (str): API ismi (loglama için)
    
    Returns:
        tuple: (data, update_date) veya (None, None)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    
    logger.debug(f"🔄 {api_name} API'den veri çekiliyor...")
    
    response = session.get(url, headers=headers, timeout=API_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    
    # Update_Date kontrolü
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
    """
    V3 ve V4 API'lerini kontrol eder, en güncel olanı döner
    Her iki API de retry mekanizması ile çekilir
    
    Returns:
        tuple: (data, api_name) veya (None, None)
    """
    v3_data, v3_date = None, None
    v4_data, v4_date = None, None
    
    # V3 API'yi dene
    try:
        v3_data, v3_date = fetch_api_data(API_V3, "V3")
    except Exception as e:
        logger.error(f"❌ V3 API başarısız (tüm denemeler tükendi): {e}")
    
    # V4 API'yi dene
    try:
        v4_data, v4_date = fetch_api_data(API_V4, "V4")
    except Exception as e:
        logger.error(f"❌ V4 API başarısız (tüm denemeler tükendi): {e}")
    
    # Her iki API de başarısız
    if v3_data is None and v4_data is None:
        logger.error("❌ Her iki API de başarısız!")
        return None, None
    
    # Sadece V3 başarılı
    if v3_data and v4_data is None:
        logger.info("🎯 V3 API kullanılıyor (V4 başarısız)")
        return v3_data, "V3"
    
    # Sadece V4 başarılı
    if v4_data and v3_data is None:
        logger.info("🎯 V4 API kullanılıyor (V3 başarısız)")
        return v4_data, "V4"
    
    # Her ikisi de başarılı - tarihe göre karşılaştır
    if v3_date and v4_date:
        if v3_date > v4_date:
            time_diff = (v3_date - v4_date).total_seconds()
            logger.info(f"🎯 V3 API kullanılıyor (V4'ten {time_diff:.0f} saniye daha yeni)")
            return v3_data, "V3"
        elif v4_date > v3_date:
            time_diff = (v4_date - v3_date).total_seconds()
            logger.info(f"🎯 V4 API kullanılıyor (V3'ten {time_diff:.0f} saniye daha yeni)")
            return v4_data, "V4"
        else:
            logger.info("🎯 Her iki API de aynı tarihli - V4 tercih ediliyor")
            return v4_data, "V4"
    
    # Fallback (teorik olarak buraya gelmemeli)
    logger.warning("⚠️ Beklenmeyen durum - V4 kullanılıyor")
    return v4_data if v4_data else v3_data, "V4" if v4_data else "V3"


def process_currencies_from_data(data, api_source):
    """
    API verisinden dövizleri işler ve liste olarak döner
    
    Args:
        data (dict): API'den gelen ham veri
        api_source (str): Kaynak API ismi (V3 veya V4)
    
    Returns:
        list: İşlenmiş döviz listesi
    """
    # Popüler döviz kodları
    currency_codes = [
        "USD", "EUR", "GBP", "JPY", "CHF",
        "CNY", "CAD", "AUD", "DKK", "SEK",
        "NOK", "SAR", "QAR", "KWD", "AED"
    ]
    
    currencies = []
    
    for code in currency_codes:
        # API'de var mı?
        if code not in data:
            logger.warning(f"⚠️ {code} API'de bulunamadı")
            continue
        
        item = data[code]
        
        # Type kontrolü
        if item.get("Type") != "Currency":
            logger.warning(f"⚠️ {code} Type != Currency: {item.get('Type')}")
            continue
        
        # İsim ve fiyatlar
        name = item.get("Name", code)
        selling = get_safe_float(item.get("Selling", 0))
        buying = get_safe_float(item.get("Buying", 0))
        change_percent = get_safe_float(item.get("Change", 0))
        
        # Fiyat kontrolü
        if selling <= 0:
            logger.warning(f"⚠️ {code} geçersiz fiyat: {selling}")
            continue
        
        # Fiyatları yuvarla - büyük değerler için 2, küçükler için 4 hane
        if selling >= 10:
            rate = round(selling, 2)  # 42.7352 → 42.73
        else:
            rate = round(selling, 4)  # 0.5355 → 0.5355
        
        # Döviz verisini hazırla
        currencies.append({
            "code": code,
            "name": name,
            "rate": rate,
            "change_percent": round(change_percent, 2)
        })
        
        logger.debug(f"✅ {code} ({name}): {rate:.4f} TL ({change_percent:+.2f}%)")
    
    return currencies


def fetch_currencies_to_cache():
    """
    V3 ve V4 API'lerinden en güncel veriyi çek ve Redis'e yaz
    Her iki API'yi kontrol eder, tarih olarak hangisi daha yeniyse onu kullanır
    Retry mekanizması ile bağlantı kopmaları otomatik düzelir
    
    Returns:
        bool: Başarılı ise True, hata varsa False
    """
    try:
        # En güncel API'yi bul (retry mekanizması ile)
        data, api_source = get_latest_api_data()
        
        if not data:
            logger.error("❌ Hiçbir API'den veri çekilemedi!")
            return False
        
        # Update_Date'i al
        update_date = data.get("Update_Date", "Bilinmiyor")
        
        # Dövizleri işle
        currencies = process_currencies_from_data(data, api_source)
        
        if not currencies:
            logger.error("❌ Hiç döviz verisi işlenemedi!")
            return False
        
        # Redis'e yaz
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


# Geriye uyumluluk için (eski kod çağırabilir)
def fetch_currencies():
    """Eski fonksiyon adı - yeni fonksiyona yönlendir"""
    return fetch_currencies_to_cache()


# cleanup_database fonksiyonu artık gereksiz (PostgreSQL kullanmıyoruz)
# Eski kodlar çağırabilir diye boş bırakıyoruz
def cleanup_database():
    """
    Artık kullanılmıyor - PostgreSQL yok
    Geriye uyumluluk için boş fonksiyon
    """
    logger.info("ℹ️ cleanup_database çağrıldı ama PostgreSQL kullanılmıyor")
    return True
