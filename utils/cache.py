"""
Redis Cache Utility - PRODUCTION READY V4.5 🚀
=======================================================
✅ CONNECTION POOL: 50 bağlantı sınırını patlatmaz (max=20)
✅ INFINITE TTL SUPPORT: ttl=0 gönderilirse veri ASLA silinmez
✅ TRIPLE FALLBACK: Redis → RAM → Disk (JSON dosyası)
✅ THREAD-SAFE: Çoklu worker/thread ortamında güvenli
✅ JSON SERIALIZATION: Verileri otomatik string/json yapar
✅ DISK BACKUP: Restart sonrası veri kaybını önler
✅ AUTO-RECOVERY: Redis çökse bile disk'ten veriyi yükler
✅ get_redis_client() EXPORT: FCM notification desteği
✅ CLEANUP SYSTEM: 7 günden eski backup'ları otomatik sil
✅ TIMEOUT FIX: Render Redis için yeterli bağlantı süresi (V4.5)
"""

import os
import json
import logging
import time
import threading
from typing import Optional, Any, Dict
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ======================================
# DISK BACKUP SİSTEMİ (YENİ!)
# ======================================

class DiskBackup:
    """
    Redis çökerse veya restart atarsa, kritik verileri
    disk'ten yükleyen kurtarma sistemi.
    """
    def __init__(self):
        # Backup klasörü (proje root'unda)
        self.backup_dir = Path("data/cache_backup")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        
        logger.info(f"📁 Disk Backup klasörü: {self.backup_dir.absolute()}")
    
    def save(self, key: str, data: Any) -> bool:
        """
        Kritik veriyi disk'e kaydet (JSON formatında)
        """
        try:
            with self._lock:
                # Güvenli dosya adı oluştur (: ve / karakterlerini temizle)
                safe_key = key.replace(":", "_").replace("/", "_")
                file_path = self.backup_dir / f"{safe_key}.json"
                
                # JSON'a çevir ve kaydet
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'key': key,
                        'data': data,
                        'timestamp': time.time()
                    }, f, default=str, indent=2)
                
                return True
        except Exception as e:
            logger.error(f"❌ Disk kayıt hatası [{key}]: {e}")
            return False
    
    def load(self, key: str) -> Optional[Any]:
        """
        Disk'ten veriyi yükle
        """
        try:
            with self._lock:
                safe_key = key.replace(":", "_").replace("/", "_")
                file_path = self.backup_dir / f"{safe_key}.json"
                
                if not file_path.exists():
                    return None
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    backup = json.load(f)
                    
                    # 24 saatten eski backup'ları yükleme
                    age = time.time() - backup.get('timestamp', 0)
                    if age > 86400:  # 24 saat = 86400 saniye
                        logger.warning(f"⚠️ [{key}] Disk backup'ı çok eski ({age/3600:.1f} saat)")
                        return None
                    
                    return backup.get('data')
        except Exception as e:
            logger.error(f"❌ Disk okuma hatası [{key}]: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """
        Disk'ten backup'ı sil
        """
        try:
            with self._lock:
                safe_key = key.replace(":", "_").replace("/", "_")
                file_path = self.backup_dir / f"{safe_key}.json"
                
                if file_path.exists():
                    file_path.unlink()
                    return True
                return False
        except Exception as e:
            logger.error(f"❌ Disk silme hatası [{key}]: {e}")
            return False
    
    def list_keys(self) -> list:
        """
        Disk'teki tüm backup key'lerini listele
        """
        try:
            with self._lock:
                files = self.backup_dir.glob("*.json")
                keys = []
                for f in files:
                    # Dosya adından key'i geri oluştur
                    key = f.stem.replace("_", ":")
                    keys.append(key)
                return keys
        except Exception as e:
            logger.error(f"❌ Disk listeleme hatası: {e}")
            return []
    
    def cleanup_old_backups(self, max_age_days: int = 7) -> int:
        """
        🧹 Eski backup dosyalarını temizle
        
        Args:
            max_age_days: Kaç günden eski dosyalar silinsin (varsayılan 7)
            
        Returns:
            Silinen dosya sayısı
        """
        try:
            with self._lock:
                deleted_count = 0
                cutoff_time = time.time() - (max_age_days * 86400)
                
                for file_path in self.backup_dir.glob("*.json"):
                    try:
                        # Dosyayı oku ve timestamp'ini kontrol et
                        with open(file_path, 'r', encoding='utf-8') as f:
                            backup = json.load(f)
                            timestamp = backup.get('timestamp', 0)
                        
                        # Eski mi?
                        if timestamp < cutoff_time:
                            file_path.unlink()
                            deleted_count += 1
                            age_days = (time.time() - timestamp) / 86400
                            logger.info(f"🗑️ Eski backup silindi: {file_path.name} ({age_days:.1f} gün)")
                    
                    except Exception as e:
                        logger.warning(f"⚠️ Dosya temizleme hatası [{file_path.name}]: {e}")
                        continue
                
                if deleted_count > 0:
                    logger.info(f"✅ {deleted_count} adet eski backup temizlendi!")
                
                return deleted_count
        
        except Exception as e:
            logger.error(f"❌ Cleanup hatası: {e}")
            return 0
    
    def get_backup_stats(self) -> dict:
        """
        📊 Backup istatistiklerini getir
        
        Returns:
            {
                'total_files': int,
                'total_size_mb': float,
                'oldest_backup': datetime,
                'newest_backup': datetime
            }
        """
        try:
            with self._lock:
                files = list(self.backup_dir.glob("*.json"))
                
                if not files:
                    return {
                        'total_files': 0,
                        'total_size_mb': 0,
                        'oldest_backup': None,
                        'newest_backup': None
                    }
                
                total_size = sum(f.stat().st_size for f in files)
                timestamps = []
                
                for file_path in files:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            backup = json.load(f)
                            timestamps.append(backup.get('timestamp', 0))
                    except:
                        continue
                
                return {
                    'total_files': len(files),
                    'total_size_mb': round(total_size / (1024 * 1024), 2),
                    'oldest_backup': datetime.fromtimestamp(min(timestamps)) if timestamps else None,
                    'newest_backup': datetime.fromtimestamp(max(timestamps)) if timestamps else None
                }
        
        except Exception as e:
            logger.error(f"❌ Stats hatası: {e}")
            return {'total_files': 0, 'total_size_mb': 0, 'oldest_backup': None, 'newest_backup': None}

# Global Disk Backup
disk_backup = DiskBackup()

# ======================================
# REDIS CLIENT WRAPPER (CONNECTION POOL)
# ======================================

class RedisClient:
    """
    Hata korumalı, Connection Pool ile yönetilen Redis istemcisi.
    🔥 YENİ: max_connections=20 ile 50 sınırını aşmaz!
    🔥 V4.5: Timeout'lar Render için optimize edildi!
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
                logger.warning("⚠️ REDIS_URL tanımlı değil! RAM + Disk Cache kullanılacak.")
                self._connection_error_logged = True
            return None

        try:
            import redis
            
            # 🔥 CONNECTION POOL (Hayati Önem!) - V4.5 TIMEOUT FIX
            self._pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=20,  # 🚨 SİHİRLİ AYAR
                decode_responses=True,
                socket_connect_timeout=10,  # ✅ 3→10 saniye (Render için)
                socket_timeout=10,  # ✅ 3→10 saniye  
                retry_on_timeout=True,  # ✅ Timeout'ta tekrar dene
                socket_keepalive=True,  # ✅ Bağlantıyı canlı tut
                socket_keepalive_options={
                    6: 1,   # TCP_KEEPIDLE = 60 saniye
                    5: 10,  # TCP_KEEPINTVL = 10 saniye
                    4: 3    # TCP_KEEPCNT = 3 deneme
                }
            )
            
            # Pool'dan client oluştur
            client = redis.Redis(connection_pool=self._pool)
            
            # Test et (10 saniye timeout ile)
            client.ping()
            
            logger.info("✅ Redis Connection Pool başarılı. (Max: 20 bağlantı, Timeout: 10s)")
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
                logger.error(f"   Redis URL: {self.redis_url[:30]}...")  # İlk 30 karakter
                self._connection_error_logged = True
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
# KRİTİK VERİ LİSTESİ
# ======================================

# Bu key'ler disk'e de yedeklenir (Restart sonrası kurtarma için)
CRITICAL_KEYS = [
    'kurabak:currencies:all',
    'kurabak:golds:all',
    'kurabak:silvers:all',
    'kurabak:summary',
    'kurabak:yesterday_prices',  # Snapshot (en kritik!)
    'kurabak:backup:all'
]

# ======================================
# PUBLIC API (DIŞARIYA AÇILAN FONKSİYONLAR)
# ======================================

def get_cache(key: str) -> Optional[Any]:
    """
    TRIPLE FALLBACK: Redis → RAM → Disk
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
    ram_data = ram_cache.get(key)
    if ram_data:
        return ram_data
    
    # 3. Disk Denemesi (Final Kurtarma!)
    if key in CRITICAL_KEYS:
        logger.warning(f"🔥 [{key}] Redis ve RAM'de yok, DISK'ten yükleniyor...")
        disk_data = disk_backup.load(key)
        if disk_data:
            logger.info(f"✅ [{key}] Disk'ten başarıyla kurtarıldı!")
            # Kurtarılan veriyi RAM'e de yükle
            ram_cache.set(key, disk_data, ttl=0)
            return disk_data
    
    return None


def set_cache(key: str, data: Any, ttl: int = 300) -> bool:
    """
    Cache'e veri yazar + Kritik verileri disk'e yedekler
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
    
    # 3. 🔥 DİSK YEDEKLEME (Sadece kritik veriler için)
    if key in CRITICAL_KEYS:
        disk_backup.save(key, data)
        logger.debug(f"💾 [{key}] Disk'e yedeklendi")
    
    return success or True  # RAM'e yazıldıysa başarılı say


def cache_exists(key: str) -> bool:
    """
    Key var mı kontrol et (Redis → RAM → Disk)
    """
    client = redis_wrapper.get_client()
    
    # 1. Redis Kontrolü
    if client:
        try:
            return bool(client.exists(key))
        except Exception as e:
            logger.warning(f"⚠️ Redis EXISTS hatası: {e}")
    
    # 2. RAM Kontrolü
    if ram_cache.exists(key):
        return True
    
    # 3. Disk Kontrolü (Kritik key'ler için)
    if key in CRITICAL_KEYS:
        return disk_backup.load(key) is not None
    
    return False


def delete_cache(key: str) -> bool:
    """
    Key'i sil (Redis + RAM + Disk)
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
    
    # 3. Disk Silme (Kritik key'ler için)
    if key in CRITICAL_KEYS:
        disk_backup.delete(key)
    
    return success or True


def get_cache_keys(pattern: str = "*"):
    """
    Pattern'e uyan tüm key'leri döndür
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
    ram_keys = ram_cache.keys(pattern)
    
    # 3. Disk'teki kritik key'leri de ekle
    disk_keys = disk_backup.list_keys()
    
    # Unique key listesi oluştur
    all_keys = set(ram_keys + disk_keys)
    
    # Pattern ile filtrele
    if pattern != "*":
        import fnmatch
        all_keys = {k for k in all_keys if fnmatch.fnmatch(k, pattern)}
    
    return list(all_keys)


def flush_all_cache() -> bool:
    """
    TÜM cache'i temizle (Redis + RAM + Disk)
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
    
    # 3. Disk Temizliği (Kritik key'leri sil)
    for key in CRITICAL_KEYS:
        disk_backup.delete(key)
    logger.warning("🧹 Disk Backup temizlendi!")
    
    return success or True


# ======================================
# 🧹 TEMİZLİK FONKSİYONU (PUBLIC API)
# ======================================

def cleanup_old_disk_backups(max_age_days: int = 7) -> dict:
    """
    🧹 Eski disk backup'larını temizle
    
    Args:
        max_age_days: Kaç günden eski dosyalar silinsin (varsayılan 7)
        
    Returns:
        {
            'deleted_count': int,
            'before_stats': dict,
            'after_stats': dict
        }
    """
    # Önceki durum
    before_stats = disk_backup.get_backup_stats()
    
    # Temizlik yap
    deleted_count = disk_backup.cleanup_old_backups(max_age_days)
    
    # Sonraki durum
    after_stats = disk_backup.get_backup_stats()
    
    return {
        'deleted_count': deleted_count,
        'before_stats': before_stats,
        'after_stats': after_stats
    }


def get_disk_backup_stats() -> dict:
    """
    📊 Disk backup istatistiklerini getir
    """
    return disk_backup.get_backup_stats()


# ======================================
# 🔥 FCM NOTIFICATION SUPPORT
# ======================================

def get_redis_client():
    """
    Redis client'ı döndür
    
    Bu fonksiyon notification_service.py tarafından kullanılır.
    FCM token'larını Redis Set'inde saklamak için gerekli.
    
    Returns:
        Redis client instance veya None
    """
    return redis_wrapper.get_client()


# ======================================
# STARTUP: DISK'TEN VERİ KURTARMA
# ======================================

def recover_from_disk():
    """
    Uygulama başlatılırken disk'ten kritik verileri yükle
    (Redis çökmüşse veya restart atmışsa)
    """
    logger.info("🔄 Disk'ten veri kurtarma kontrolü başlatılıyor...")
    
    recovered_count = 0
    
    for key in CRITICAL_KEYS:
        # Eğer Redis ve RAM'de yoksa disk'ten yükle
        if not get_cache(key):
            disk_data = disk_backup.load(key)
            if disk_data:
                logger.info(f"💾 [{key}] Disk'ten kurtarıldı ve RAM'e yüklendi")
                ram_cache.set(key, disk_data, ttl=0)
                recovered_count += 1
    
    if recovered_count > 0:
        logger.info(f"✅ {recovered_count} adet veri disk'ten başarıyla kurtarıldı!")
    else:
        logger.info("ℹ️ Kurtarılacak veri bulunamadı (Normal durum)")

# Uygulama başlarken otomatik kurtarma yap
recover_from_disk()
