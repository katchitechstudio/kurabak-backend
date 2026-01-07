"""
Gold Service - V4 API (İyileştirilmiş)
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

CACHE_TTL = 600  # 5 dakika
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 1  # İlk deneme için bekleme süresi (saniye)
API_TIMEOUT = 30  # API timeout süresi (saniye)

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
    
    logger.debug("🔄 V4 API'den altın verileri çekiliyor...")
    
    response = session.get(url, headers=headers, timeout=30)  # 30 saniye (yavaş API için)
    response.raise_for_status()
    return response.json()


def fetch_golds_to_cache():
    """
    V4 API'den altınları çek ve Redis'e yaz
    
    Returns:
        bool: Başarılı ise True, hata varsa False
    """
    try:
        # API'den veri çek (retry mekanizması ile)
        data = fetch_api_data()
        
        # V4'te altın kodları BÜYÜK HARFLE geliyor
        gold_mapping = {
            "GRA": "Gram Altın",
            "CEYREKALTIN": "Çeyrek Altın",
            "YARIMALTIN": "Yarım Altın",
            "TAMALTIN": "Tam Altın",
            "CUMHURIYETALTINI": "Cumhuriyet Altını"
        }
        
        golds = []
        
        for api_code, display_name in gold_mapping.items():
            # API'de var mı?
            if api_code not in data:
                logger.warning(f"⚠️ {api_code} API'de bulunamadı")
                continue
            
            item = data[api_code]
            
            # Type kontrolü
            if item.get("Type") != "Gold":
                logger.warning(f"⚠️ {api_code} Type != Gold: {item.get('Type')}")
                continue
            
            # Fiyat kontrolü
            selling = get_safe_float(item.get("Selling", 0))
            if selling <= 0:
                logger.warning(f"⚠️ {api_code} geçersiz fiyat: {selling}")
                continue
            
            # Değişim yüzdesi
            change_percent = get_safe_float(item.get("Change", 0))
            
            # Altın verisini hazırla
            golds.append({
                "name": display_name,
                "rate": round(selling, 2),  # Altın için 2 hane yeterli
                "change_percent": round(change_percent, 2)
            })
            
            logger.debug(f"✅ {display_name}: {selling:.2f} TL ({change_percent:+.2f}%)")
        
        if not golds:
            logger.error("❌ Hiç altın verisi çekilemedi!")
            return False
        
        # Redis'e yaz
        cache_data = {
            "success": True,
            "count": len(golds),
            "data": golds
        }
        
        set_cache('kurabak:golds:all', cache_data, CACHE_TTL)
        logger.info(f"✅ {len(golds)} altın fiyatı Redis'e yazıldı (V4 API)")
        
        return True
    
    except requests.RequestException as e:
        logger.error(f"❌ API bağlantı hatası (tüm denemeler başarısız): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Altın çekme hatası: {e}", exc_info=True)
        return False


# Geriye uyumluluk için (eski kod çağırabilir)
def fetch_golds():
    """Eski fonksiyon adı - yeni fonksiyona yönlendir"""
    return fetch_golds_to_cache()
