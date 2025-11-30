import time
import logging
from threading import Lock

logger = logging.getLogger(__name__)

# Thread-safe (Eşzamanlılık güvenli) RAM cache
_cache = {}
_cache_lock = Lock()
_cleared = False  # Çoklu temizleme koruması


def get_cache(key, ttl_seconds):
    """
    Cache'den veri al (eğer süresi dolmadıysa)
    
    Args:
        key: Cache anahtarı (örn: 'altin_verisi')
        ttl_seconds: Geçerlilik süresi (saniye)
    
    Returns:
        Cached data or None
    """
    with _cache_lock:
        if key in _cache:
            timestamp, data = _cache[key]
            # Şu anki zaman - Kayıt zamanı < İzin verilen süre
            if time.time() - timestamp < ttl_seconds:
                return data
            else:
                # Süresi dolmuş, sil ve yer aç
                del _cache[key]
    return None


def set_cache(key, data):
    """
    Cache'e veri kaydet
    """
    with _cache_lock:
        _cache[key] = (time.time(), data)


def clear_cache():
    """
    Tüm cache'i temizle (sadece bir kez log yapar)
    """
    global _cleared
    
    with _cache_lock:
        if not _cleared and len(_cache) > 0:
            _cache.clear()
            _cleared = True
            logger.info("🗑️ Cache temizlendi!")
        elif not _cleared:
            _cleared = True
