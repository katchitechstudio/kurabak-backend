"""
Gold Service - V4 API
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


def fetch_golds_to_cache():
    """
    V4 API'den altınları çek ve Redis'e yaz
    
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
        
        logger.debug("🔄 V4 API'den altın verileri çekiliyor...")
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
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
        logger.error(f"❌ API bağlantı hatası: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Altın çekme hatası: {e}", exc_info=True)
        return False


# Geriye uyumluluk için (eski kod çağırabilir)
def fetch_golds():
    """Eski fonksiyon adı - yeni fonksiyona yönlendir"""
    return fetch_golds_to_cache()
