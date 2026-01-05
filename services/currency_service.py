"""
Currency Service - V4 API
Redis'e direkt yazar, PostgreSQL kullanmaz
"""
import requests
import logging
from utils.cache import set_cache

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 dakika


def get_safe_float(value):
    """
    V4 API'de değerler string olarak geliyor ve virgül kullanılıyor.
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


def fetch_currencies_to_cache():
    """
    V4 API'den dövizleri çek ve Redis'e yaz
    
    Returns:
        bool: Başarılı ise True, hata varsa False
    """
    try:
        # V4 API endpoint
        url = "https://finans.truncgil.com/v4/today.json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        logger.debug("🔄 V4 API'den döviz verileri çekiliyor...")
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
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
        
        if not currencies:
            logger.error("❌ Hiç döviz verisi çekilemedi!")
            return False
        
        # Redis'e yaz
        cache_data = {
            "success": True,
            "count": len(currencies),
            "data": currencies
        }
        
        set_cache('kurabak:currencies:all', cache_data, CACHE_TTL)
        logger.info(f"✅ {len(currencies)} döviz Redis'e yazıldı (V4 API)")
        
        return True
    
    except requests.RequestException as e:
        logger.error(f"❌ API bağlantı hatası: {e}")
        return False
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
