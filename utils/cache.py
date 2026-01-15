"""
Redis Cache Utility - Production Ready (High Performance)
=======================================================

Features:
✅ Redis with automatic reconnection
✅ RAM fallback (zero downtime)
✅ Thread-safe operations
✅ TTL-based memory cleanup
✅ Metrics and monitoring
✅ Config integration
✅ Connection pooling
✅ BULK OPERATIONS (MGET/Pipeline) 🚀
"""

import os
import json
import logging
import time
import threading
from datetime import datetime
from typing import Optional, Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ======================================
# REDIS CLIENT
# ======================================

class RedisClient:
    """
    Thread-safe Redis client wrapper
    Features: Auto-reconnection, health checks, fallback, bulk ops
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
            'bulk_ops': 0
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
                retry_on_error=[redis.exceptions.ConnectionError]
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
        """Redis client'ı al (lazy initialization + auto-reconnect)"""
        if self._client and self._enabled:
            now = time.time()
            if now - self._last_check < self._check_interval:
                return self._client
            
            try:
                self._client.ping()
                self._last_check = now
                return self._client
            except Exception as e:
                logger.error(f"❌ Redis health check başarısız: {e}")
                self._enabled = False
                self._client = None
        
        with self._lock:
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
        if not client: return None
        try:
            data = client.get(key)
            if data: self.metrics['redis_hits'] += 1
            else: self.metrics['redis_misses'] += 1
            return data
        except Exception as e:
            logger.error(f"❌ Redis GET hatası ({key}): {e}")
            self.metrics['redis_errors'] += 1
            self._enabled = False
            return None
    
    def set(self, key: str, value: str, ttl: int) -> bool:
        """Redis'e veri yaz"""
        client = self.get_client()
        if not client: return False
        try:
            client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.error(f"❌ Redis SET hatası ({key}): {e}")
            self.metrics['redis_errors'] += 1
            self._enabled = False
            return False
            
    def delete(self, *keys: str) -> int:
        """Redis'ten veri sil"""
        client = self.get_client()
        if not client: return 0
        try:
            return client.delete(*keys)
        except Exception as e:
            logger.error(f"❌ Redis DELETE hatası: {e}")
            self.metrics['redis_errors'] += 1
            return 0

    # 🔥 YENİ EKLENEN BULK OPERATIONS 🔥
    
    def get_multi(self, keys: List[str]) -> Dict[str, Optional[str]]:
        """Birden fazla key'i tek seferde al (MGET)"""
        client = self.get_client()
        if not client or not keys:
            return {k: None for k in keys}
        
        try:
            values = client.mget(keys)
            results = {}
            for i, key in enumerate(keys):
                val = values[i]
                results[key] = val
                if val: self.metrics['redis_hits'] += 1
                else: self.metrics['redis_misses'] += 1
            
            self.metrics['bulk_ops'] += 1
            return results
        except Exception as e:
            logger.error(f"❌ Redis MGET hatası: {e}")
            self.metrics['redis_errors'] += 1
            return {k: None for k in keys}

    def set_multi(self, items: Dict[str, str], ttl: int) -> bool:
        """Birden fazla key'i tek seferde yaz (Pipeline)"""
        client = self.get_client()
        if not client or not items:
            return False
        
        try:
            pipeline = client.pipeline()
            for key, value in items.items():
                pipeline.setex(key, ttl, value)
            pipeline.execute()
            self.metrics['bulk_ops'] += 1
            return True
        except Exception as e:
            logger.error(f"❌ Redis Pipeline SET hatası: {e}")
            self.metrics['redis_errors'] += 1
            return False

# ======================================
# GLOBAL INSTANCE & INIT
# ======================================

redis_client = RedisClient()
redis_client.get_client()
REDIS_ENABLED = redis_client.is_enabled()

# ======================================
# RAM CACHE (FALLBACK)
# ======================================

class RAMCache:
    """Thread-safe RAM cache with TTL"""
    
    def __init__(self, max_size_mb: int = 50):
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.RLock()
        self._last_cleanup = time.time()
        self._cleanup_interval = 60
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._stats = {'total_stored': 0, 'total_evicted': 0, 'total_hits': 0, 'total_misses': 0}
    
    def get(self, key: str, ttl: int) -> Optional[Any]:
        with self._lock:
            self._cleanup_if_needed()
            if key in self._cache:
                timestamp, data = self._cache[key]
                if time.time() - timestamp < ttl:
                    self._stats['total_hits'] += 1
                    redis_client.metrics['ram_hits'] += 1
                    return data
                else:
                    del self._cache[key]
                    self._stats['total_evicted'] += 1
            
            redis_client.metrics['ram_misses'] += 1
            self._stats['total_misses'] += 1
            return None
    
    def set(self, key: str, data: Any) -> bool:
        with self._lock:
            if len(self._cache) > 2000: self._cache.clear()
            self._cache[key] = (time.time(), data)
            self._stats['total_stored'] += 1
            self._cleanup_if_needed()
            return True
    
    def _cleanup_if_needed(self):
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval: return
        expired = [k for k, (ts, _) in self._cache.items() if now - ts > 600]
        for k in expired: del self._cache[k]
        self._last_cleanup = now

ram_cache = RAMCache(max_size_mb=50)

# ======================================
# PUBLIC API
# ======================================

def get_cache(key: str, ttl: Optional[int] = None) -> Optional[Any]:
    """Single Cache Get"""
    if ttl is None:
        try: from config import Config; ttl = Config.CACHE_TTL
        except: ttl = 300
    
    if redis_client.is_enabled():
        try:
            data = redis_client.get(key)
            if data: return json.loads(data)
        except Exception as e:
            logger.error(f"❌ Cache get error: {e}")
    
    return ram_cache.get(key, ttl)

def set_cache(key: str, data: Any, ttl: Optional[int] = None) -> bool:
    """Single Cache Set"""
    if ttl is None:
        try: from config import Config; ttl = Config.CACHE_TTL
        except: ttl = 300
    
    success = False
    json_data = None
    try:
        json_data = json.dumps(data, default=str, ensure_ascii=False)
    except: pass
    
    if redis_client.is_enabled() and json_data:
        if redis_client.set(key, json_data, ttl): success = True
    
    if ram_cache.set(key, data): success = True
    return success

# 🔥 BULK API WRAPPERS (App.py bunları kullanabilir)
def get_multiple_cache(keys: List[str], ttl: Optional[int] = None) -> Dict[str, Any]:
    """Bulk Cache Get"""
    if ttl is None:
        try: from config import Config; ttl = Config.CACHE_TTL
        except: ttl = 300
        
    results = {}
    
    # 1. Try Redis MGET
    if redis_client.is_enabled():
        try:
            redis_data = redis_client.get_multi(keys)
            for k, v in redis_data.items():
                if v:
                    try: results[k] = json.loads(v)
                    except: pass
        except Exception as e:
            logger.error(f"Bulk get error: {e}")
            
    # 2. Fill missing from RAM
    for k in keys:
        if k not in results:
            val = ram_cache.get(k, ttl)
            if val: results[k] = val
            
    return results

def set_multiple_cache(items: Dict[str, Any], ttl: Optional[int] = None) -> bool:
    """Bulk Cache Set"""
    if ttl is None:
        try: from config import Config; ttl = Config.CACHE_TTL
        except: ttl = 300
        
    redis_items = {}
    ram_success = True
    
    # Prepare data
    for k, v in items.items():
        try:
            redis_items[k] = json.dumps(v, default=str, ensure_ascii=False)
        except: pass
        if not ram_cache.set(k, v): ram_success = False
        
    # Redis Pipeline Set
    if redis_client.is_enabled() and redis_items:
        redis_client.set_multi(redis_items, ttl)
        
    return ram_success
