"""
Silver Service - V4 API (Optimize Edilmiş)
Redis'e direkt yazar, PostgreSQL kullanmaz

Optimizasyonlar:
- ❌ Session retry KALDIRILDI (çatışma önlendi)
- ✅ Timeout düşürüldü: 30s → (5, 10)s
- ✅ Pool size azaltıldı: 20 → 4
- ✅ JSON hatasında retry YOK (boşuna deneme)
- ✅ Exponential backoff düzeltildi: 1s → 2s → 4s
"""
import requests
import logging
import time
from functools import wraps
from requests.adapters import HTTPAdapter
from utils.cache import set_cache

logger = logging.getLogger(__name__)

# ======================================
# OPTİMİZE EDİLMİŞ AYARLAR
# ======================================
CACHE_TTL = 600
MAX_RETRY_ATTEMPTS = 3
API_TIMEOUT = (5, 10)  # (connect, read) - Daha gerçekçi
API_URL = "https://finans.truncgil.com/v4/today.json"

# ======================================
# OPTİMİZE EDİLMİŞ SESSION
# ======================================
session = requests.Session()

# ❌ RETRY STRATEGY KALDIRILDI - Sadece decorator retry
adapter = HTTPAdapter(
    pool_connections=2,   # Sadece 2 host gerekli
    pool_maxsize=4,       # Her host için max 2 bağlantı
    pool_block=False
)
session.mount("http://", adapter)
session.mount("https://", adapter)


def retry_on_failure(max_attempts=MAX_RETRY_ATTEMPTS):
    """
    Optimize edilmiş retry decorator
    - Exponential backoff: 1s → 2s → 4s
    - Sadece bağlantı hatalarında retry
    - JSON hatalarında RETRY YOK
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
                        logger.error(f"❌ {func.__name__} timeout (tüm denemeler)")
                        raise
                    
                    wait_time = 2 ** (attempt - 1)  # 1s, 2s, 4s
                    logger.warning(
                        f"⚠️ {func.__name__} timeout (deneme {attempt}/{max_attempts}), "
                        f"{wait_time}s sonra tekrar..."
                    )
                    time.sleep(wait_time)
                
                except requests.exceptions.ConnectionError as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(f"❌ {func.__name__} bağlantı hatası (tüm denemeler)")
                        raise
                    
                    wait_time = 2 ** (attempt - 1)
                    logger.warning(
                        f"⚠️ {func.__name__} bağlantı hatası (deneme {attempt}/{max_attempts}), "
                        f"{wait_time}s sonra tekrar..."
                    )
                    time.sleep(wait_time)
                
                except requests.exceptions.JSONDecodeError as e:
                    # ❌ JSON hatası - RETRY YAPMA!
                    logger.error(f"❌ API bozuk JSON döndürdü (gümüş servisi)")
                    raise
                
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    logger.error(f"❌ {func.__name__} beklenmeyen hata: {e}")
                    raise
                
                except Exception as e:
                    logger.error(f"❌ {func.__name__} kritik hata: {e}", exc_info=True)
                    raise
            
            if last_exception:
                raise last_exception
            
        return wrapper
    return decorator


def get_safe_float(value):
    """
    Float dönüşümü - Türk formatı desteği
    
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
        value_str = value_str.replace("%", "").replace("$", "").replace(" ", "")
        
        # Türk formatı: 5.953,42 → 5953.42
        if '.' in value_str and ',' in value_str:
            value_str = value_str.replace(".", "").replace(",", ".")
        # Tek virgül: 89,85 → 89.85
        elif ',' in value_str:
            value_str = value_str.replace(",", ".")
        
        return float(value_str)
    except Exception as e:
        logger.warning(f"⚠️ Float dönüşüm hatası: '{value}' → {e}")
        return 0.0


@retry_on_failure(max_attempts=3)
def fetch_api_data():
    """
    V4 API'den gümüş verisi çek
    
    Optimizasyon:
    - Timeout: (5, 10) → 5s connect, 10s read
    - Session retry YOK (decorator yeterli)
    """
    headers = {
        "User-Agent": "KuraBak-Backend/2.0 (Python/requests)",
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive"
    }
    
    logger.debug(f"🔄 V4 API çağrılıyor (gümüş): {API_URL}")
    
    # ✅ Timeout tuple
    response = session.get(API_URL, headers=headers, timeout=API_TIMEOUT)
    response.raise_for_status()
    
    # JSON parse - hata varsa JSONDecodeError fırlatır
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError as e:
        logger.error("❌ V4 API bozuk JSON döndürdü (gümüş)")
        logger.debug(f"Response text (ilk 500 char): {response.text[:500]}")
        raise


def fetch_silvers_to_cache():
    """
    V4 API'den gümüş fiyatını çek ve Redis'e yaz
    
    Returns:
        bool: Başarılı ise True, hata varsa False
    """
    try:
        # 1. API'den veri çek
        data = fetch_api_data()
        
        # 2. GUMUS kontrolü (V4'te BÜYÜK HARF)
        if "GUMUS" not in data:
            logger.error("❌ GUMUS API'de bulunamadı!")
            return False
        
        item = data["GUMUS"]
        
        # 3. Type kontrolü (API'de bazen "Gold" olarak geliyor)
        item_type = item.get("Type")
        if item_type not in ["Gold", "Silver"]:
            logger.warning(f"⚠️ GUMUS beklenmeyen Type: {item_type}")
            # Yine de devam et (bazı versiyonlarda "Gold" oluyor)
        
        # 4. Fiyat al
        selling = get_safe_float(item.get("Selling", 0))
        if selling <= 0:
            logger.error(f"❌ GUMUS geçersiz fiyat: {selling}")
            return False
        
        # 5. Değişim yüzdesi
        change_percent = get_safe_float(item.get("Change", 0))
        
        # 6. Gümüş verisi hazırla
        silvers = [{
            "name": "Gümüş",
            "rate": round(selling, 4),  # 4 hane (daha hassas)
            "change_percent": round(change_percent, 2)
        }]
        
        logger.debug(f"✅ Gümüş: {selling:.4f} TL ({change_percent:+.2f}%)")
        
        # 7. Redis'e yaz
        cache_data = {
            "success": True,
            "count": len(silvers),
            "data": silvers
        }
        
        set_cache('kurabak:silvers:all', cache_data, CACHE_TTL)
        logger.info(f"✅ {len(silvers)} gümüş fiyatı Redis'e yazıldı (V4 API)")
        
        return True
    
    except requests.RequestException as e:
        logger.error(f"❌ API bağlantı hatası (tüm denemeler başarısız): {type(e).__name__}")
        return False
    except Exception as e:
        logger.error(f"❌ Gümüş çekme hatası: {e}", exc_info=True)
        return False


def fetch_silvers():
    """Public API - geriye uyumluluk"""
    return fetch_silvers_to_cache()
