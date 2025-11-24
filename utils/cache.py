import time
from threading import Lock

# Basit RAM cache
_cache = {}
_cache_lock = Lock()

def get_cache(key, ttl_seconds):
    """
    Cache'den veri al (eğer süresi dolmadıysa)
    
    Args:
        key: Cache anahtarı
        ttl_seconds: Geçerlilik süresi (saniye)
    
    Returns:
        Cached data or None
    """
    with _cache_lock:
        if key in _cache:
            timestamp, data = _cache[key]
            if time.time() - timestamp < ttl_seconds:
                return data
            else:
                # Süresi dolmuş, sil
                del _cache[key]
    return None

def set_cache(key, data):
    """
    Cache'e veri kaydet
    
    Args:
        key: Cache anahtarı
        data: Kaydedilecek veri
    """
    with _cache_lock:
        _cache[key] = (time.time(), data)

def clear_cache():
    """
    🔥 YENİ: Tüm cache'i temizle
    Scheduler yeni veri çektiğinde kullanılır
    """
    with _cache_lock:
        _cache.clear()
        print("🗑️ Cache temizlendi!")
