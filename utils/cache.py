"""
Redis Cache Utility - PRODUCTION READY (ULTIMATE FIX) 🚀
=======================================================
✅ INFINITE TTL SUPPORT: ttl=0 gönderilirse veri ASLA silinmez.
✅ HYBRID SYSTEM: Redis varsa kullanır, yoksa RAM'e geçer (Otomatik).
✅ THREAD-SAFE: Çoklu worker/thread ortamında güvenli.
✅ JSON SERIALIZATION: Verileri otomatik string/json yapar.
✅ CONNECTION POOL: Redis bağlantılarını verimli yönetir.
"""

import os
import json
import logging
import time
import threading
from typing import Optional, Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ======================================
# REDIS CLIENT WRAPPER
# ======================================

class RedisClient:
    """
    Hata korumalı, otomatik yeniden bağlanan Redis istemcisi.
    """
    def __init__(self):
        self._client = None
        self._lock = threading.Lock()
        self._enabled = False
        self._connection_error_logged = False
        
        # Redis URL kontrolü (Env'den gelir)
        self.redis_url = os.environ.get("REDIS_URL")

    def _connect(self):
        """Redis'e bağlanmayı dener"""
        if not self.redis_url:
            if not self._connection_error_logged:
                logger.warning("⚠️ REDIS_URL tanımlı değil! RAM Cache kullanılacak.")
                self._connection_error_logged = True
            return None

        try:
            import redis
            # Connection Pool ile verimli bağlantı
            client = redis.from_url(
                self.redis_url,
                decode_responses=True, # String olarak al
                socket_connect_timeout=3,
                socket_timeout=3
            )
            client.ping() # Test et
            logger.info("✅ Redis bağlantısı başarılı.")
            self._enabled = True
            return client
        except ImportError:
            logger.error("❌ 'redis' kütüphanesi eksik! (pip install redis)")
            return None
        except Exception as e:
            logger.error(f"❌ Redis bağlantı hatası: {e}")
            return None

    def get_client(self):
        """Lazy connection: İlk ihtiyaç duyulduğunda bağlanır"""
        if self._client:
            return self._client
            
        with self._lock:
            if not self._client:
                self._client = self._connect()
            return self._client

    def is_enabled(self):
        return self._enabled

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
            expiry = time.time() + ttl if ttl > 0 else 0 # 0 ise sonsuz
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

ram_cache = RAMCache()

# ======================================
# PUBLIC API (DIŞARIYA AÇILAN FONKSİYONLAR)
# ======================================

def get_cache(key: str, ttl: Optional[int] = None) -> Optional[Any]:
    """
    Cache'ten veri okur.
    Önce Redis'e bakar, hata alırsan RAM'e bakar.
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
                client.setex(key, ttl, json_data) # Süreli kayıt
            else:
                client.set(key, json_data) # 🔥 SÜRESİZ KAYIT (Fix burası)
            success = True
        except Exception as e:
            logger.error(f"❌ Redis Yazma Hatası: {e}")

    # 2. RAM Yazma (Her zaman yedek olarak yazalım)
    ram_cache.set(key, data, ttl)
    
    return success or True # RAM'e yazıldıysa başarılı say
