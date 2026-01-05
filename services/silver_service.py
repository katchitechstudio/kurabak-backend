"""
Silver Service - V4 API
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


def fetch_silvers_to_cache():
    """
    V4 API'den gümüş fiyatını çek ve Redis'e yaz
    
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
        
        logger.debug("🔄 V4 API'den gümüş verisi çekiliyor...")
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
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
        logger.error(f"❌ API bağlantı hatası: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Gümüş çekme hatası: {e}", exc_info=True)
        return False


# Geriye uyumluluk için (eski kod çağırabilir)
def fetch_silvers():
    """Eski fonksiyon adı - yeni fonksiyona yönlendir"""
    return fetch_silvers_to_cache()
