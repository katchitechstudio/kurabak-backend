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
✅ Connection pooling
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
            'last_error': None
        }
    
    def _create_client(self) -> Optional[Any]:
        """Redis client oluştur"""
        redis_url = os.environ.get("REDIS_URL")
        
        if not redis_url:
            logger.warning("⚠️ REDIS_URL bulunamadı, RAM cache kullanılacak")
            return None
        
        try:
            import redis
            
            # Connection pool oluştur (Sade ve Güvenli Ayarlar)
            client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,  # Integer
                socket_timeout=5,          # Integer
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
    Features: TTL-based expiration, automatic cleanup
    """
    
    def __init__(self, max_size_mb: int = 50):
        self._cache: Dict[str, Tuple[float, Any]] = {}  # {key: (timestamp, data)}
        self._lock = threading.RLock()
        self._last_cleanup = time.time()
        self._cleanup_interval = 60  # 1 dakikada bir cleanup
        
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
                    self._stats['total_hits'] += 1
                    redis_client.metrics['ram_hits'] += 1
                    return data
                else:
                    # Expired - sil
                    del self._cache[key]
                    self._stats['total_evicted'] += 1
                    redis_client.metrics['ram_misses'] += 1
                    self._stats['total_misses'] += 1
            else:
                redis_client.metrics['ram_misses'] += 1
                self._stats['total_misses'] += 1
            
            return None
    
    def set(self, key: str, data: Any) -> bool:
        """RAM'e veri yaz"""
        with self._lock:
            # Eğer cache çok şiştiyse temizle (Basit koruma)
            if len(self._cache) > 2000:
                self._cache.clear()
            
            self._cache[key] = (time.time(), data)
            self._stats['total_stored'] += 1
            self._cleanup_if_needed()
            return True
    
    def _cleanup_if_needed(self):
        """Expired key'leri temizle (periyodik)"""
        now = time.time()
        
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        # Cleanup zamanı
        expired_keys = []
        for key, (timestamp, _) in list(self._cache.items()):
            if now - timestamp > 600: # 10dk'dan eski her şeyi sil
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
        
        self._last_cleanup = now

# Global RAM cache
ram_cache = RAMCache(max_size_mb=50)

# ======================================
# PUBLIC API
# ======================================

def get_cache(key: str, ttl: Optional[int] = None) -> Optional[Any]:
    """Cache'den veri al (Redis → RAM fallback)"""
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

def set_cache(key: str, data: Any, ttl: Optional[int] = None) -> bool:
    """Cache'e veri yaz (Redis + RAM fallback)"""
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
        return str(obj)
    
    # JSON serialize
    try:
        json_data = json.dumps(data, default=json_serializer, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ JSON serialize hatası: {e}")
        json_data = None
    
    # 1. Redis'e yaz
    if redis_client.is_enabled() and json_data:
        if redis_client.set(key, json_data, ttl):
            success = True
    
    # 2. RAM'e yaz (her zaman)
    if ram_cache.set(key, data):
        success = True
    
    return success
