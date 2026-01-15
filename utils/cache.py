"""
Redis Cache Utility - Production Ready
=======================================

Features:
✅ Redis with automatic reconnection
✅ RAM fallback (zero downtime)
✅ Thread-safe operations
✅ TTL-based memory cleanup
✅ Metrics and monitoring
✅ Config integration
✅ Batch operations (multi-get)
✅ Connection pooling
"""

import os
import json
import logging
import time
import threading
from datetime import datetime
from typing import Optional, Any, Dict, List, Tuple, Union
from collections import defaultdict

logger = logging.getLogger(__name__)

# ======================================
# REDIS CLIENT
# ======================================

class RedisClient:
    """
    Thread-safe Redis client wrapper
    Features: Auto-reconnection, health checks, fallback
    """
    
    def __init__(self):
        self._client = None
        self._lock = threading.Lock()
        self._enabled = False
        self._last_check = 0
        self._check_interval = 30  # 30 saniyede bir health check
        
        # Metrikler
        self.metrics = {
            'redis_hits': 0,
            'redis_misses': 0,
            'redis_errors': 0,
            'ram_hits': 0,
            'ram_misses': 0,
            'connection_attempts': 0,
            'last_connection_attempt': None,
            'last_error': None,
            'pipeline_operations': 0,
            'bulk_operations': 0
        }
    
    def _create_client(self) -> Optional[Any]:
        """Redis client oluştur"""
        redis_url = os.environ.get("REDIS_URL")
        
        if not redis_url:
            logger.warning("⚠️ REDIS_URL bulunamadı, RAM cache kullanılacak")
            return None
        
        try:
            import redis
            
            # Connection pool oluştur
            client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
                retry_on_timeout=True,
                max_connections=10,
                retry_on_error=[redis.exceptions.ConnectionError],
                socket_keepalive_options={
                    'interval': 60,  # 60 saniyede bir keepalive
                }
            )
            
            # Bağlantı testi
            client.ping()
            logger.info("✅ Redis bağlantısı başarılı")
            
            return client
            
        except ImportError:
            logger.warning("⚠️ redis paketi yüklü değil: pip install redis")
            return None
        
        except Exception as e:
            logger.error(f"❌ Redis bağlantı hatası: {e}")
            self.metrics['last_error'] = str(e)
            return None
    
    def get_client(self) -> Optional[Any]:
        """
        Redis client'ı al (lazy initialization + auto-reconnect)
        Returns:
            Redis client instance or None
        """
        # Zaten bağlıysa ve yakın zamanda kontrol edildiyse direkt dön
        if self._client and self._enabled:
            now = time.time()
            if now - self._last_check < self._check_interval:
                return self._client
            
            # Health check zamanı
            try:
                self._client.ping()
                self._last_check = now
                return self._client
            except Exception as e:
                logger.error(f"❌ Redis health check başarısız: {e}")
                self._enabled = False
                self._client = None
        
        # Client yoksa veya sağlıksızsa yeniden bağlan
        with self._lock:
            # Double-check locking
            if self._client and self._enabled:
                return self._client
            
            self.metrics['connection_attempts'] += 1
            self.metrics['last_connection_attempt'] = datetime.now().isoformat()
            
            if self.metrics['connection_attempts'] == 1:
                logger.info("🔄 Redis'e bağlanılıyor...")
            
            self._client = self._create_client()
            
            if self._client:
                self._enabled = True
                self._last_check = time.time()
                logger.info(f"✅ Redis client başlatıldı (attempt #{self.metrics['connection_attempts']})")
                return self._client
            else:
                self._enabled = False
                logger.warning(f"❌ Redis bağlantısı başarısız (attempt #{self.metrics['connection_attempts']})")
                return None
    
    def is_enabled(self) -> bool:
        """Redis aktif mi?"""
        return self._enabled and self._client is not None
    
    def get(self, key: str) -> Optional[str]:
        """Redis'ten veri al"""
        client = self.get_client()
        if not client:
            return None
        
        try:
            data = client.get(key)
            
            if data:
                self.metrics['redis_hits'] += 1
            else:
                self.metrics['redis_misses'] += 1
            
            return data
            
        except Exception as e:
            logger.error(f"❌ Redis GET hatası ({key}): {e}")
            self.metrics['redis_errors'] += 1
            self._enabled = False  # Otomatik reconnect için
            return None
    
    def get_multi(self, keys: List[str]) -> Dict[str, Optional[str]]:
        """
        Multiple keys get (pipeline kullanarak)
        
        Args:
            keys: List of keys to fetch
            
        Returns:
            Dict of {key: value}
        """
        client = self.get_client()
        if not client:
            return {key: None for key in keys}
        
        try:
            # Pipeline oluştur
            pipeline = client.pipeline()
            for key in keys:
                pipeline.get(key)
            
            results = pipeline.execute()
            self.metrics['pipeline_operations'] += 1
            
            # Sonuçları dictionary'e çevir
            result_dict = {}
            for key, value in zip(keys, results):
                if value:
                    self.metrics['redis_hits'] += 1
                else:
                    self.metrics['redis_misses'] += 1
                result_dict[key] = value
            
            return result_dict
            
        except Exception as e:
            logger.error(f"❌ Redis MGET hatası: {e}")
            self.metrics['redis_errors'] += 1
            return {key: None for key in keys}
    
    def set(self, key: str, value: str, ttl: int) -> bool:
        """Redis'e veri yaz"""
        client = self.get_client()
        if not client:
            return False
        
        try:
            client.setex(key, ttl, value)
            return True
            
        except Exception as e:
            logger.error(f"❌ Redis SET hatası ({key}): {e}")
            self.metrics['redis_errors'] += 1
            self._enabled = False  # Otomatik reconnect için
            return False
    
    def set_multi(self, items: Dict[str, Tuple[str, int]]) -> Dict[str, bool]:
        """
        Multiple keys set (pipeline kullanarak)
        
        Args:
            items: Dict of {key: (value, ttl)}
            
        Returns:
            Dict of {key: success_status}
        """
        client = self.get_client()
        if not client:
            return {key: False for key in items}
        
        try:
            pipeline = client.pipeline()
            results = {}
            
            for key, (value, ttl) in items.items():
                pipeline.setex(key, ttl, value)
            
            pipeline_results = pipeline.execute()
            self.metrics['pipeline_operations'] += 1
            self.metrics['bulk_operations'] += 1
            
            # Sonuçları dictionary'e çevir
            for key, success in zip(items.keys(), pipeline_results):
                results[key] = bool(success)
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Redis MSET hatası: {e}")
            self.metrics['redis_errors'] += 1
            return {key: False for key in items}
    
    def delete(self, *keys: str) -> int:
        """Redis'ten veri sil"""
        client = self.get_client()
        if not client:
            return 0
        
        try:
            return client.delete(*keys)
        except Exception as e:
            logger.error(f"❌ Redis DELETE hatası: {e}")
            self.metrics['redis_errors'] += 1
            return 0
    
    def keys(self, pattern: str) -> List[str]:
        """Redis key'lerini listele"""
        client = self.get_client()
        if not client:
            return []
        
        try:
            return client.keys(pattern)
        except Exception as e:
            logger.error(f"❌ Redis KEYS hatası: {e}")
            self.metrics['redis_errors'] += 1
            return []
    
    def flush_cache(self, pattern: str = "kurabak:*") -> int:
        """
        Cache'i temizle (pattern'a göre)
        
        Args:
            pattern: Key pattern to delete
            
        Returns:
            Number of keys deleted
        """
        client = self.get_client()
        if not client:
            return 0
        
        try:
            keys = client.keys(pattern)
            if not keys:
                return 0
            
            deleted = client.delete(*keys)
            logger.info(f"🗑️ Redis cache flushed: {deleted} keys deleted")
            return deleted
            
        except Exception as e:
            logger.error(f"❌ Redis flush hatası: {e}")
            self.metrics['redis_errors'] += 1
            return 0
    
    def get_info(self) -> Dict[str, Any]:
        """
        Redis server info al
        """
        client = self.get_client()
        if not client:
            return {"status": "disabled"}
        
        try:
            info = client.info()
            return {
                "status": "connected",
                "version": info.get("redis_version", "unknown"),
                "used_memory": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_days": info.get("uptime_in_days", 0),
                "keyspace": info.get("db0", {})
            }
        except Exception as e:
            logger.error(f"❌ Redis INFO hatası: {e}")
            return {"status": "error", "error": str(e)}

# ======================================
# GLOBAL INSTANCE & INIT
# ======================================

# Global Redis client
redis_client = RedisClient()

# İlk bağlantıyı burada zorluyoruz!
redis_client.get_client()

REDIS_ENABLED = redis_client.is_enabled()

# ======================================
# RAM CACHE (FALLBACK)
# ======================================

class RAMCache:
    """
    Thread-safe RAM cache
    Features: TTL-based expiration, automatic cleanup, LRU-like behavior
    """
    
    def __init__(self, max_size_mb: int = 50):
        self._cache: Dict[str, Tuple[float, Any]] = {}  # {key: (timestamp, data)}
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        self._last_cleanup = time.time()
        self._cleanup_interval = 60  # 1 dakikada bir cleanup
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._access_times: Dict[str, float] = {}  # LRU için
        
        # Statistics
        self._stats = {
            'total_stored': 0,
            'total_evicted': 0,
            'total_hits': 0,
            'total_misses': 0
        }
    
    def get(self, key: str, ttl: int) -> Optional[Any]:
        """RAM'den veri al"""
        with self._lock:
            self._cleanup_if_needed()
            
            if key in self._cache:
                timestamp, data = self._cache[key]
                age = time.time() - timestamp
                
                if age < ttl:
                    # Update access time for LRU
                    self._access_times[key] = time.time()
                    self._stats['total_hits'] += 1
                    redis_client.metrics['ram_hits'] += 1
                    return data
                else:
                    # Expired - sil
                    del self._cache[key]
                    if key in self._access_times:
                        del self._access_times[key]
                    self._stats['total_evicted'] += 1
                    redis_client.metrics['ram_misses'] += 1
                    self._stats['total_misses'] += 1
            else:
                redis_client.metrics['ram_misses'] += 1
                self._stats['total_misses'] += 1
            
            return None
    
    def get_multi(self, keys: List[str], ttl: int) -> Dict[str, Optional[Any]]:
        """
        Multiple keys get from RAM cache
        
        Args:
            keys: List of keys to fetch
            ttl: TTL for cache validation
            
        Returns:
            Dict of {key: value}
        """
        with self._lock:
            self._cleanup_if_needed()
            
            results = {}
            now = time.time()
            
            for key in keys:
                if key in self._cache:
                    timestamp, data = self._cache[key]
                    age = now - timestamp
                    
                    if age < ttl:
                        self._access_times[key] = now
                        self._stats['total_hits'] += 1
                        redis_client.metrics['ram_hits'] += 1
                        results[key] = data
                    else:
                        # Expired
                        del self._cache[key]
                        if key in self._access_times:
                            del self._access_times[key]
                        self._stats['total_evicted'] += 1
                        redis_client.metrics['ram_misses'] += 1
                        self._stats['total_misses'] += 1
                        results[key] = None
                else:
                    redis_client.metrics['ram_misses'] += 1
                    self._stats['total_misses'] += 1
                    results[key] = None
            
            return results
    
    def set(self, key: str, data: Any) -> bool:
        """RAM'e veri yaz"""
        with self._lock:
            # Eğer cache doluysa, en eski erişileni sil (LRU)
            self._evict_if_full()
            
            self._cache[key] = (time.time(), data)
            self._access_times[key] = time.time()
            self._stats['total_stored'] += 1
            self._cleanup_if_needed()
            return True
    
    def set_multi(self, items: Dict[str, Any]) -> Dict[str, bool]:
        """
        Multiple keys set to RAM cache
        
        Args:
            items: Dict of {key: value}
            
        Returns:
            Dict of {key: success_status}
        """
        with self._lock:
            self._evict_if_full()
            
            results = {}
            now = time.time()
            
            for key, data in items.items():
                self._cache[key] = (now, data)
                self._access_times[key] = now
                self._stats['total_stored'] += 1
                results[key] = True
            
            self._cleanup_if_needed()
            return results
    
    def _evict_if_full(self):
        """Cache doluysa eski item'ları sil"""
        if self._get_cache_size() < self._max_size_bytes:
            return
        
        # LRU: En az erişileni bul ve sil
        if not self._access_times:
            return
        
        # En eski erişim zamanlı key'i bul
        oldest_key = min(self._access_times.items(), key=lambda x: x[1])[0]
        
        # Sil
        if oldest_key in self._cache:
            del self._cache[oldest_key]
        if oldest_key in self._access_times:
            del self._access_times[oldest_key]
        
        self._stats['total_evicted'] += 1
        logger.debug(f"🧹 RAM cache eviction: {oldest_key}")
    
    def _get_cache_size(self) -> int:
        """Cache'in tahmini byte boyutu"""
        total = 0
        for _, data in self._cache.values():
            try:
                total += len(str(data).encode('utf-8'))
            except:
                total += 100  # Fallback
        return total
    
    def clear(self) -> int:
        """Tüm cache'i temizle"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._access_times.clear()
            
            if count > 0:
                logger.info(f"🗑️ RAM cache temizlendi ({count} key)")
            
            return count
    
    def _cleanup_if_needed(self):
        """Expired key'leri temizle (periyodik)"""
        now = time.time()
        
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        # Cleanup zamanı
        expired_keys = []
        
        for key, (timestamp, _) in list(self._cache.items()):
            # 10 dakikadan eski tüm veriler silinir (max TTL)
            if now - timestamp > 600:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
            if key in self._access_times:
                del self._access_times[key]
        
        self._last_cleanup = now
        
        if expired_keys:
            logger.debug(f"🧹 RAM cleanup: {len(expired_keys)} expired key silindi")
            self._stats['total_evicted'] += len(expired_keys)
    
    def get_stats(self) -> dict:
        """RAM cache istatistikleri"""
        with self._lock:
            total_size = self._get_cache_size()
            current_items = len(self._cache)
            
            # Hit rate hesapla
            total_access = self._stats['total_hits'] + self._stats['total_misses']
            hit_rate = (self._stats['total_hits'] / total_access * 100) if total_access > 0 else 0
            
            # LRU stats
            if self._access_times:
                oldest_access = min(self._access_times.values())
                newest_access = max(self._access_times.values())
            else:
                oldest_access = newest_access = time.time()
            
            return {
                'current_keys': current_items,
                'total_size_bytes': total_size,
                'max_size_bytes': self._max_size_bytes,
                'utilization_percent': (total_size / self._max_size_bytes * 100) if self._max_size_bytes > 0 else 0,
                'hit_rate_percent': hit_rate,
                'total_hits': self._stats['total_hits'],
                'total_misses': self._stats['total_misses'],
                'total_stored': self._stats['total_stored'],
                'total_evicted': self._stats['total_evicted'],
                'oldest_access_seconds': time.time() - oldest_access,
                'newest_access_seconds': time.time() - newest_access
            }

# Global RAM cache
ram_cache = RAMCache(max_size_mb=50)

# ======================================
# PUBLIC API
# ======================================

def get_cache(key: str, ttl: Optional[int] = None) -> Optional[Any]:
    """
    Cache'den veri al (Redis → RAM fallback)
    
    Args:
        key: Cache key
        ttl: Time to live in seconds
        
    Returns:
        Cached value or None
    """
    # TTL default değeri
    if ttl is None:
        try:
            from config import Config
            ttl = Config.CACHE_TTL
        except ImportError:
            ttl = 300
    
    # 1. Redis'e bak
    if redis_client.is_enabled():
        try:
            data = redis_client.get(key)
            if data:
                return json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parse hatası ({key}): {e}")
        except Exception as e:
            logger.error(f"❌ Cache get hatası ({key}): {e}")
    
    # 2. RAM'e bak
    return ram_cache.get(key, ttl)


def get_multiple_cache(keys: List[str], ttl: Optional[int] = None) -> List[Optional[Dict]]:
    """
    Get multiple cache keys in a single operation
    
    Args:
        keys: List of cache keys
        ttl: Optional TTL for fallback cache
        
    Returns:
        List of cached values (same order as keys)
    """
    if ttl is None:
        try:
            from config import Config
            ttl = Config.CACHE_TTL
        except ImportError:
            ttl = 300
    
    # 1. Redis multi-get (pipeline)
    if redis_client.is_enabled():
        try:
            redis_results = redis_client.get_multi(keys)
            
            # Parse results
            parsed_results = []
            all_from_redis = True
            
            for key in keys:
                data = redis_results.get(key)
                if data:
                    try:
                        parsed_results.append(json.loads(data))
                    except json.JSONDecodeError:
                        parsed_results.append(None)
                        all_from_redis = False
                else:
                    parsed_results.append(None)
                    all_from_redis = False
            
            # Tüm veriler Redis'ten geldiyse direkt dön
            if all_from_redis:
                return parsed_results
            
        except Exception as e:
            logger.error(f"Redis multi-get error: {e}")
            # Fallback to RAM cache
    
    # 2. RAM multi-get
    ram_results = ram_cache.get_multi(keys, ttl)
    
    # Convert to list in same order as keys
    results = []
    for key in keys:
        results.append(ram_results.get(key))
    
    return results


def set_cache(key: str, data: Any, ttl: Optional[int] = None) -> bool:
    """
    Cache'e veri yaz (Redis + RAM fallback)
    
    Args:
        key: Cache key
        data: Data to cache
        ttl: Time to live in seconds
        
    Returns:
        Success status
    """
    # TTL default değeri
    if ttl is None:
        try:
            from config import Config
            ttl = Config.CACHE_TTL
        except ImportError:
            ttl = 300
    
    success = False
    
    # JSON serialize helper
    def json_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, 'isoformat'):  # Diğer date/time objeleri
            return obj.isoformat()
        return str(obj)
    
    # JSON serialize
    try:
        json_data = json.dumps(data, default=json_serializer, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ JSON serialize hatası: {e}")
        # JSON serialize başarısız olsa bile RAM'e yazmayı dene
        json_data = None
    
    # 1. Redis'e yaz (sadece JSON başarılıysa)
    if redis_client.is_enabled() and json_data:
        if redis_client.set(key, json_data, ttl):
            success = True
    
    # 2. RAM'e yaz (her zaman)
    if ram_cache.set(key, data):
        success = True
    
    return success


def set_multiple_cache(items: Dict[str, Any], ttl: Optional[int] = None) -> Dict[str, bool]:
    """
    Set multiple cache items at once
    
    Args:
        items: Dict of {key: data}
        ttl: Time to live in seconds
        
    Returns:
        Dict of {key: success_status}
    """
    if ttl is None:
        try:
            from config import Config
            ttl = Config.CACHE_TTL
        except ImportError:
            ttl = 300
    
    # JSON serialize helper
    def json_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return str(obj)
    
    # Prepare Redis items
    redis_items = {}
    ram_items = {}
    
    for key, data in items.items():
        # RAM için
        ram_items[key] = data
        
        # Redis için JSON serialize et
        try:
            json_data = json.dumps(data, default=json_serializer, ensure_ascii=False)
            redis_items[key] = (json_data, ttl)
        except Exception as e:
            logger.error(f"❌ JSON serialize hatası ({key}): {e}")
            # Bu key için Redis'e yazma
    
    results = {}
    
    # 1. Redis multi-set
    if redis_client.is_enabled() and redis_items:
        redis_results = redis_client.set_multi(redis_items)
        results.update(redis_results)
    else:
        # Redis yoksa veya başarısızsa
        for key in redis_items:
            results[key] = False
    
    # 2. RAM multi-set
    ram_results = ram_cache.set_multi(ram_items)
    
    # Combine results (RAM başarılıysa success say)
    for key in items:
        if results.get(key, False) or ram_results.get(key, False):
            results[key] = True
        else:
            results[key] = False
    
    return results


def clear_cache(pattern: str = "kurabak:*") -> Dict[str, int]:
    """
    Tüm cache'i temizle (Redis + RAM)
    
    Args:
        pattern: Redis key pattern to clear
        
    Returns:
        Dict with number of keys cleared from each cache
    """
    result = {
        'redis_cleared': 0,
        'ram_cleared': 0
    }
    
    # Redis temizle
    if redis_client.is_enabled():
        result['redis_cleared'] = redis_client.flush_cache(pattern)
    
    # RAM temizle
    result['ram_cleared'] = ram_cache.clear()
    
    logger.info(f"🗑️ Cache cleared: Redis={result['redis_cleared']}, RAM={result['ram_cleared']}")
    return result


def get_cache_stats() -> dict:
    """
    Detaylı cache istatistikleri
    
    Returns:
        Comprehensive cache statistics
    """
    ram_stats = ram_cache.get_stats()
    redis_info = redis_client.get_info()
    
    # Hit rates
    total_redis = redis_client.metrics['redis_hits'] + redis_client.metrics['redis_misses']
    total_ram = redis_client.metrics['ram_hits'] + redis_client.metrics['ram_misses']
    
    redis_hit_rate = (
        (redis_client.metrics['redis_hits'] / total_redis * 100)
        if total_redis > 0 else 0
    )
    
    ram_hit_rate = (
        (redis_client.metrics['ram_hits'] / total_ram * 100)
        if total_ram > 0 else 0
    )
    
    # Overall hit rate (weighted)
    total_hits = redis_client.metrics['redis_hits'] + redis_client.metrics['ram_hits']
    total_misses = redis_client.metrics['redis_misses'] + redis_client.metrics['ram_misses']
    total_access = total_hits + total_misses
    overall_hit_rate = (total_hits / total_access * 100) if total_access > 0 else 0
    
    return {
        'overview': {
            'redis_enabled': REDIS_ENABLED,
            'overall_hit_rate': f"{overall_hit_rate:.2f}%",
            'total_access': total_access,
            'total_hits': total_hits,
            'total_misses': total_misses,
            'timestamp': datetime.now().isoformat()
        },
        'redis': {
            'enabled': REDIS_ENABLED,
            'status': redis_info.get('status', 'unknown'),
            'hits': redis_client.metrics['redis_hits'],
            'misses': redis_client.metrics['redis_misses'],
            'errors': redis_client.metrics['redis_errors'],
            'hit_rate': f"{redis_hit_rate:.2f}%",
            'connection_attempts': redis_client.metrics['connection_attempts'],
            'pipeline_operations': redis_client.metrics['pipeline_operations'],
            'bulk_operations': redis_client.metrics['bulk_operations'],
            'last_connection_attempt': redis_client.metrics['last_connection_attempt'],
            'last_error': redis_client.metrics['last_error'],
            'server_info': redis_info
        },
        'ram': {
            'hit_rate': f"{ram_hit_rate:.2f}%",
            **ram_stats
        }
    }


def health_check() -> Dict[str, Any]:
    """
    Cache system health check
    
    Returns:
        Health status for monitoring
    """
    redis_healthy = redis_client.is_enabled()
    ram_stats = ram_cache.get_stats()
    
    # Redis latency test
    redis_latency = None
    if redis_healthy and redis_client.get_client():
        try:
            start = time.time()
            redis_client.get_client().ping()
            redis_latency = (time.time() - start) * 1000  # ms
        except:
            redis_healthy = False
    
    return {
        'status': 'healthy' if redis_healthy or ram_stats['current_keys'] > 0 else 'degraded',
        'redis': {
            'enabled': redis_healthy,
            'latency_ms': round(redis_latency, 2) if redis_latency else None
        },
        'ram': {
            'keys': ram_stats['current_keys'],
            'size_mb': round(ram_stats['total_size_bytes'] / (1024 * 1024), 2)
        },
        'timestamp': datetime.now().isoformat()
    }

# ======================================
# STARTUP CHECK & INITIALIZATION
# ======================================

# Başlangıçta cache sistemini test et
def initialize_cache_system() -> bool:
    """
    Cache sistemini başlat ve test et
    
    Returns:
        True if cache system is operational
    """
    logger.info("🔄 Cache sistemi başlatılıyor...")
    
    # Redis connection test
    if REDIS_ENABLED:
        logger.info("✅ Redis cache aktif")
        
        # Test connection with a ping
        try:
            client = redis_client.get_client()
            if client:
                latency_start = time.time()
                client.ping()
                latency = (time.time() - latency_start) * 1000
                logger.info(f"📊 Redis latency: {latency:.2f}ms")
        except Exception as e:
            logger.warning(f"⚠️ Redis ping test başarısız: {e}")
    else:
        logger.warning("⚠️ Redis bağlantısı yok, RAM fallback kullanılıyor")
    
    # RAM cache test
    try:
        test_key = "cache:init:test"
        test_data = {"test": True, "timestamp": datetime.now().isoformat()}
        
        ram_cache.set(test_key, test_data)
        retrieved = ram_cache.get(test_key, ttl=10)
        
        if retrieved and retrieved.get("test"):
            logger.info("✅ RAM cache çalışıyor")
            ram_cache.clear()  # Test verisini temizle
        else:
            logger.error("❌ RAM cache test başarısız")
            return False
    
    except Exception as e:
        logger.error(f"❌ RAM cache test hatası: {e}")
        return False
    
    logger.info("🚀 Cache sistemi başlatma tamamlandı")
    return True

# Uygulama başladığında cache'i initialize et
if __name__ != "__main__":
    # Sadece module import edildiğinde çalıştır
    import atexit
    
    # Cache sistemini başlat
    cache_init_success = initialize_cache_system()
    
    if not cache_init_success:
        logger.error("❌ Cache sistemi başlatılamadı!")
    
    # Uygulama kapanırken temizle
    def cleanup_cache():
        logger.info("🧹 Cache cleanup başlatılıyor...")
        clear_cache()
        logger.info("✅ Cache cleanup tamamlandı")
    
    atexit.register(cleanup_cache)
