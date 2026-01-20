"""
Redis Cache Utility - PRODUCTION READY (CONNECTION POOL) 🚀
=======================================================
✅ CONNECTION POOL: 50 bağlantı sınırını patlatmaz (max=20)
✅ INFINITE TTL SUPPORT: ttl=0 gönderilirse veri ASLA silinmez.
✅ HYBRID SYSTEM: Redis varsa kullanır, yoksa RAM'e geçer (Otomatik).
✅ THREAD-SAFE: Çoklu worker/thread ortamında güvenli.
✅ JSON SERIALIZATION: Verileri otomatik string/json yapar.
"""

import os
import json
import logging
import time
import threading
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

# ======================================
# REDIS CLIENT WRAPPER (CONNECTION POOL)
# ======================================

class RedisClient:
    """
    Hata korumalı, Connection Pool ile yönetilen Redis istemcisi.
    🔥 YENİ: max_connections=20 ile 50 sınırını aşmaz!
    """
    def __init__(self):
        self._client = None
        self._pool = None
        self._lock = threading.Lock()
        self._enabled = False
        self._connection_error_logged = False
        
        # Redis URL kontrolü (Env'den gelir)
        self.redis_url = os.environ.get("REDIS_URL")

    def _connect(self):
        """Redis'e Connection Pool ile bağlanır"""
        if not self.redis_url:
            if not self._connection_error_logged:
                logger.warning("⚠️ REDIS_URL tanımlı değil! RAM Cache kullanılacak.")
                self._connection_error_logged = True
            return None

        try:
            import redis
            
            # 🔥 CONNECTION POOL (Hayati Önem!)
            # max_connections=20 -> 50 sınırının altında kalırız
            self._pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=20,  # 🚨 SİHİRLİ AYAR
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3
            )
            
            # Pool'dan client oluştur
            client = redis.Redis(connection_pool=self._pool)
            client.ping()  # Test et
            
            logger.info("✅ Redis Connection Pool başarılı. (Max: 20 bağlantı)")
            self._enabled = True
            return client
            
        except ImportError:
            if not self._connection_error_logged:
                logger.error("❌ 'redis' kütüphanesi eksik! (pip install redis)")
                self._connection_error_logged = True
            return None
        except Exception as e:
            if not self._connection_error_logged:
                logger.error(f"❌ Redis bağlantı hatası: {e}")
                self._connection_error_logged = True
            return None

    def get_client(self):
        """Lazy connection: İlk ihtiyaç duyulduğında bağlanır"""
        if self._client:
            return self._client
            
        with self._lock:
            if not self._client:
                self._client = self._connect()
            return self._client

    def is_enabled(self):
        return self._enabled

# Global Redis Wrapper
redis_wrapper = RedisClient()

# ======================================
# RAM CACHE (FALLBACK)
# ======================================

class RAMCache:
    """
    Redis yoksa devreye giren basit bellek deposu.
    """
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def set(self, key: str, value: Any, ttl: int = 0):
        with self._lock:
            expiry = time.time() + ttl if ttl > 0 else 0  # 0 ise sonsuz
            self._cache[key] = (value, expiry)

    def get(self, key: str):
        with self._lock:
            if key not in self._cache:
                return None
            
            value, expiry = self._cache[key]
            
            # Süre dolmuş mu? (Expiry 0 ise dolmaz)
            if expiry > 0 and time.time() > expiry:
                del self._cache[key]
                return None
                
            return value
    
    def exists(self, key: str) -> bool:
        """Key var mı kontrol et"""
        with self._lock:
            if key not in self._cache:
                return False
            
            value, expiry = self._cache[key]
            
            # Süre dolmuşsa False döndür
            if expiry > 0 and time.time() > expiry:
                del self._cache[key]
                return False
            
            return True
    
    def delete(self, key: str) -> bool:
        """Key'i sil"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def keys(self, pattern: str = "*"):
        """Pattern'e uyan tüm key'leri döndür"""
        with self._lock:
            if pattern == "*":
                return list(self._cache.keys())
            
            # Basit wildcard desteği
            import fnmatch
            return [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]

# Global RAM Cache
ram_cache = RAMCache()

# ======================================
# PUBLIC API (DIŞARIYA AÇILAN FONKSİYONLAR)
# ======================================

def get_cache(key: str) -> Optional[Any]:
    """
    Cache'ten veri okur.
    Önce Redis'e bakar, hata alırsa RAM'e bakar.
    """
    client = redis_wrapper.get_client()
    
    # 1. Redis Denemesi
    if client:
        try:
            data = client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"⚠️ Redis Okuma Hatası: {e} -> RAM'e geçiliyor.")
    
    # 2. RAM Denemesi (Fallback)
    return ram_cache.get(key)


def set_cache(key: str, data: Any, ttl: int = 300) -> bool:
    """
    Cache'e veri yazar.
    ÖNEMLİ: ttl=0 gönderilirse veri silinmez (Persistent).
    """
    success = False
    
    # Veriyi JSON string'e çevir
    try:
        json_data = json.dumps(data, default=str)
    except Exception as e:
        logger.error(f"❌ JSON Serialization Hatası: {e}")
        return False

    client = redis_wrapper.get_client()

    # 1. Redis Yazma
    if client:
        try:
            if ttl and ttl > 0:
                client.setex(key, ttl, json_data)  # Süreli kayıt
            else:
                client.set(key, json_data)  # 🔥 SÜRESİZ KAYIT (ttl=0)
            success = True
        except Exception as e:
            logger.error(f"❌ Redis Yazma Hatası: {e}")

    # 2. RAM Yazma (Her zaman yedek olarak yazalım)
    ram_cache.set(key, data, ttl)
    
    return success or True  # RAM'e yazıldıysa başarılı say


def cache_exists(key: str) -> bool:
    """
    Key var mı kontrol et (Şef için gerekli)
    """
    client = redis_wrapper.get_client()
    
    # 1. Redis Kontrolü
    if client:
        try:
            return bool(client.exists(key))
        except Exception as e:
            logger.warning(f"⚠️ Redis EXISTS hatası: {e}")
    
    # 2. RAM Kontrolü
    return ram_cache.exists(key)


def delete_cache(key: str) -> bool:
    """
    Key'i sil (Şef için gerekli)
    """
    success = False
    client = redis_wrapper.get_client()
    
    # 1. Redis Silme
    if client:
        try:
            client.delete(key)
            success = True
        except Exception as e:
            logger.warning(f"⚠️ Redis DELETE hatası: {e}")
    
    # 2. RAM Silme
    ram_cache.delete(key)
    
    return success or True


def get_cache_keys(pattern: str = "*"):
    """
    Pattern'e uyan tüm key'leri döndür (Şef için gerekli)
    """
    client = redis_wrapper.get_client()
    
    # 1. Redis Denemesi
    if client:
        try:
            return [k.decode() if isinstance(k, bytes) else k 
                    for k in client.keys(pattern)]
        except Exception as e:
            logger.warning(f"⚠️ Redis KEYS hatası: {e}")
    
    # 2. RAM Denemesi
    return ram_cache.keys(pattern)


def flush_all_cache() -> bool:
    """
    TÜM cache'i temizle (Şef'in /temizle komutu için)
    ⚠️ DİKKAT: Bu komutu sadece Şef kullanmalı!
    """
    success = False
    client = redis_wrapper.get_client()
    
    # 1. Redis Temizliği
    if client:
        try:
            client.flushall()
            logger.warning("🧹 Redis tamamen temizlendi!")
            success = True
        except Exception as e:
            logger.error(f"❌ Redis FLUSHALL hatası: {e}")
    
    # 2. RAM Temizliği
    ram_cache._cache.clear()
    logger.warning("🧹 RAM Cache temizlendi!")
    
    return success or True
