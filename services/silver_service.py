"""
Silver Service - V4 API (İyileştirilmiş)
Redis'e direkt yazar, PostgreSQL kullanmaz

İyileştirmeler:
- Retry mekanizması ile otomatik tekrar deneme
- Connection pooling ile daha stabil bağlantı
- Exponential backoff ile akıllı bekleme
- Detaylı hata loglama
"""
import requests
import logging
import time
from functools import wraps
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from utils.cache import set_cache

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 dakika
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 1  # İlk deneme için bekleme süresi (saniye)

# Connection pooling için session oluştur
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
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
    V4 API'de değerler string olarak geliyor ve virgül kullanılıyor.
    Change değerleri '%0,03' formatında geliyor.
    
    Örnekler:
    - "5.953,42" → 5953.42
    - "89,85" → 89.85
    - "%0,03" → 0.03
    - "%-1,61" → -1.61
    """
    try:
        if isinstance(value, (int, float)):
            return float(value)
        
        value_str = str(value).strip()
        
        # % işaretini temizle (V4'te "%0,03" veya "%-1,61" formatı var)
        value_str = value_str.replace("%", "")
        
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


@retry_on_failure(max_attempts=3, delay=1)
def fetch_api_data():
    """
    V4 API'den veri çek (retry mekanizması ile)
    """
    url = "https://finans.truncgil.com/v4/today.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    
    logger.debug("🔄 V4 API'den gümüş verisi çekiliyor...")
    
    response = session.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()


def fetch_silvers_to_cache():
    """
    V4 API'den gümüş fiyatını çek ve Redis'e yaz
    
    Returns:
        bool: Başarılı ise True, hata varsa False
    """
    try:
        # API'den veri çek (retry mekanizması ile)
        data = fetch_api_data()
        
        silvers = []
        
        # V4'te gümüş kodu "GUMUS" (BÜYÜK HARF)
        if "GUMUS" not in data:
            logger.error("❌ GUMUS API'de bulunamadı!")
            return False
        
        item = data["GUMUS"]
        
        # Type kontrolü - API'de bazen "Gold" olarak geliyor
        item_type = item.get("Type")
        if item_type not in ["Gold", "Silver"]:
            logger.warning(f"⚠️ GUMUS Type beklenen değil: {item_type}")
            # Yine de devam et, çünkü bazı versiyonlarda "Gold" olarak geliyor
        
        # Fiyat kontrolü
        selling = get_safe_float(item.get("Selling", 0))
        if selling <= 0:
            logger.error(f"❌ GUMUS geçersiz fiyat: {selling}")
            return False
        
        # Değişim yüzdesi
        change_percent = get_safe_float(item.get("Change", 0))
        
        # Gümüş verisini hazırla
        silvers.append({
            "name": "Gümüş",
            "rate": round(selling, 4),  # Gümüş için 4 hane (daha hassas)
            "change_percent": round(change_percent, 2)
        })
        
        logger.debug(f"✅ Gümüş: {selling:.4f} TL ({change_percent:+.2f}%)")
        
        # Redis'e yaz
        cache_data = {
            "success": True,
            "count": len(silvers),
            "data": silvers
        }
        
        set_cache('kurabak:silvers:all', cache_data, CACHE_TTL)
        logger.info(f"✅ {len(silvers)} gümüş fiyatı Redis'e yazıldı (V4 API)")
        
        return True
    
    except requests.RequestException as e:
        logger.error(f"❌ API bağlantı hatası (tüm denemeler başarısız): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Gümüş çekme hatası: {e}", exc_info=True)
        return False


# Geriye uyumluluk için (eski kod çağırabilir)
def fetch_silvers():
    """Eski fonksiyon adı - yeni fonksiyona yönlendir"""
    return fetch_silvers_to_cache()
