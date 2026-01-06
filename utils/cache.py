"""
Redis Cache Utility - 2 dakikalık güncelleme için optimize edilmiş
Cache TTL: 3 dakika (180 saniye)
Update Interval: 2 dakika (120 saniye)
"""
import os
import json
import logging
import time
from threading import Lock

logger = logging.getLogger(__name__)

redis_client = None
REDIS_ENABLED = False


def init_redis():
    """Redis bağlantısını başlat"""
    global redis_client, REDIS_ENABLED
    
    redis_url = os.getenv("REDIS_URL")
    
    if not redis_url:
        logger.warning("⚠️ REDIS_URL bulunamadı, RAM cache kullanılacak")
        REDIS_ENABLED = False
        return False
    
    try:
        import redis
        redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        
        redis_client.ping()
        REDIS_ENABLED = True
        logger.info("✅ Redis bağlantısı başarılı")
        return True
        
    except ImportError:
        logger.warning("⚠️ redis paketi yüklü değil: pip install redis")
        REDIS_ENABLED = False
        return False
    except Exception as e:
        logger.error(f"❌ Redis bağlantı hatası: {e}")
        REDIS_ENABLED = False
        return False


# Başlangıçta Redis'i dene
init_redis()

# RAM Cache (Redis yoksa yedek)
_ram_cache = {}
_ram_cache_lock = Lock()


def ram_get(key, ttl_seconds):
    """RAM'den veri al"""
    with _ram_cache_lock:
        if key in _ram_cache:
            timestamp, data = _ram_cache[key]
            if time.time() - timestamp < ttl_seconds:
                return data
            else:
                del _ram_cache[key]
    return None


def ram_set(key, data):
    """RAM'e veri yaz"""
    with _ram_cache_lock:
        _ram_cache[key] = (time.time(), data)


def ram_clear():
    """RAM cache'i temizle"""
    with _ram_cache_lock:
        _ram_cache.clear()


def get_cache(key, ttl_seconds=180):
    """
    Cache'den veri al (önce Redis, yoksa RAM)
    
    Args:
        key: Cache key
        ttl_seconds: TTL süresi (varsayılan: 180 saniye = 3 dakika)
    
    Returns:
        Cached data or None
    """
    # Önce Redis'e bak
    if REDIS_ENABLED and redis_client:
        try:
            data = redis_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"❌ Redis get hatası: {e}")
    
    # Redis yoksa veya hata varsa RAM'e bak
    return ram_get(key, ttl_seconds)


def set_cache(key, data, ttl_seconds=180):
    """
    Cache'e veri yaz (hem Redis hem RAM)
    
    Args:
        key: Cache key
        data: Yazılacak veri
        ttl_seconds: TTL süresi (varsayılan: 180 saniye = 3 dakika)
    
    Returns:
        bool: Başarılı ise True
    """
    # Önce Redis'e yaz
    if REDIS_ENABLED and redis_client:
        try:
            redis_client.setex(
                key,
                ttl_seconds,
                json.dumps(data, default=str)
            )
            return True
        except Exception as e:
            logger.error(f"❌ Redis set hatası: {e}")
    
    # Redis yoksa veya hata varsa RAM'e yaz
    ram_set(key, data)
    return True


def clear_cache():
    """Tüm cache'i temizle (hem Redis hem RAM)"""
    # Redis temizle
    if REDIS_ENABLED and redis_client:
        try:
            keys = redis_client.keys('kurabak:*')
            if keys:
                redis_client.delete(*keys)
                logger.info(f"🗑️ Redis cache temizlendi ({len(keys)} key)")
        except Exception as e:
            logger.error(f"❌ Redis clear hatası: {e}")
    
    # RAM temizle
    ram_clear()
    logger.info("🗑️ RAM cache temizlendi")
