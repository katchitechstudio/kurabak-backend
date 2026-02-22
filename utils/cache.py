"""
Redis Cache Utility - PRODUCTION READY V5.6 🚀
=========================================================
✅ CONNECTION POOL FIX: Global client kullanımı (V4.8)
✅ RAM CACHE CLEANUP: Otomatik çöp toplama (V4.8)
✅ DISK BACKUP OPTİMİZE: Sadece kritik anlarda kaydet (V4.8)
✅ INFINITE TTL SUPPORT: ttl=0 gönderilirse veri ASLA silinmez
✅ TRIPLE FALLBACK: Redis → RAM → Disk (JSON dosyası)
✅ THREAD-SAFE: Çoklu worker/thread ortamında güvenli
✅ JSON SERIALIZATION: Verileri otomatik string/json yapar
✅ AUTO-RECOVERY: Redis çökse bile disk'ten veriyi yükler
✅ get_redis_client() EXPORT: FCM notification desteği
✅ CLEANUP SYSTEM: 7 günden eski backup'ları otomatik sil
✅ TIMEOUT FIX: Render Redis için yeterli bağlantı süresi
✅ EAGER CONNECTION: Startup'ta hemen bağlan
✅ ATOMIC INCR: Race Condition önleme için atomik increment
✅ 🔥 RAM CLEANUP INTERVAL: 10 dakika (RAM OPTİMİZASYON - V4.8.1)
✅ 🔥 V5.5 SNAPSHOT KEYS: raw_snapshot + jeweler_snapshot (Disk backup desteği)
✅ 🔥 V5.6 SCHEDULER LOCK: renew_scheduler_lock buraya taşındı (circular import fix)
   app.py → maintenance_service.py → app.py döngüsü kırıldı.

V5.6 Değişiklikler:
- 🔥 SCHEDULER_LOCK_KEY, SCHEDULER_LOCK_TTL, renew_scheduler_lock() eklendi
- app.py ve maintenance_service.py artık buradan import eder
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
# DISK BACKUP SİSTEMİ
# ======================================

class DiskBackup:
    """
    Redis çökerse veya restart atarsa, kritik verileri
    disk'ten yükleyen kurtarma sistemi.
    """
    def __init__(self):
        self.backup_dir = Path("data/cache_backup")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        
        logger.info(f"📁 Disk Backup klasörü: {self.backup_dir.absolute()}")
    
    def save(self, key: str, data: Any) -> bool:
        """Kritik veriyi disk'e kaydet (JSON formatında)"""
        try:
            with self._lock:
                safe_key = key.replace(":", "_").replace("/", "_")
                file_path = self.backup_dir / f"{safe_key}.json"
                
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
        """Disk'ten veriyi yükle"""
        try:
            with self._lock:
                safe_key = key.replace(":", "_").replace("/", "_")
                file_path = self.backup_dir / f"{safe_key}.json"
                
                if not file_path.exists():
                    return None
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    backup = json.load(f)
                    
                    age = time.time() - backup.get('timestamp', 0)
                    if age > 86400:
                        logger.warning(f"⚠️ [{key}] Disk backup'ı çok eski ({age/3600:.1f} saat)")
                        return None
                    
                    return backup.get('data')
        except Exception as e:
            logger.error(f"❌ Disk okuma hatası [{key}]: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Disk'ten backup'ı sil"""
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
        """Disk'teki tüm backup key'lerini listele"""
        try:
            with self._lock:
                files = self.backup_dir.glob("*.json")
                keys = []
                for f in files:
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
                        with open(file_path, 'r', encoding='utf-8') as f:
                            backup = json.load(f)
                            timestamp = backup.get('timestamp', 0)
                        
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
        """📊 Backup istatistiklerini getir"""
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

disk_backup = DiskBackup()

# ======================================
# 🔥 V4.8: REDIS CLIENT (CONNECTION LEAK FİX!)
# ======================================

class RedisClient:
    """
    🔥 V4.8 FIX: Global client kullanımı
    
    ÖNCEKİ SORUN:
    - Her get_cache() çağrısında yeni connection alınıyordu
    - Connection'lar geri verilmiyordu
    - Pool doluyordu ve RAM'de birikiyor
    
    YENİ ÇÖZÜM:
    - Tek bir global Redis client
    - Connection pool otomatik yönetiliyor
    - Memory leak yok!
    """
    def __init__(self):
        self._client = None
        self._pool = None
        self._lock = threading.Lock()
        self._enabled = False
        self._connection_error_logged = False
        
        self.redis_url = os.environ.get("REDIS_URL")
        
        if self.redis_url:
            logger.info(f"🔍 [INIT] Redis URL bulundu, bağlantı kuruluyor...")
            self._client = self._connect()
        else:
            logger.warning("⚠️ [INIT] REDIS_URL yok, RAM + Disk kullanılacak")

    def _connect(self):
        """Redis'e Connection Pool ile bağlanır"""
        if not self.redis_url:
            if not self._connection_error_logged:
                logger.warning("⚠️ REDIS_URL tanımlı değil! RAM + Disk Cache kullanılacak.")
                self._connection_error_logged = True
            return None

        try:
            import redis
            
            logger.info(f"🔍 [CONNECT] redis modülü import edildi (v{redis.__version__})")
            
            # CONNECTION POOL
            self._pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=20,
                decode_responses=True,
                socket_connect_timeout=10,
                socket_timeout=10,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={
                    6: 1,
                    5: 10,
                    4: 3
                }
            )
            
            logger.info("🔍 [CONNECT] Connection pool oluşturuldu")
            
            # 🔥 V4.8: GLOBAL CLIENT - SADECE BİR KERE OLUŞTUR!
            client = redis.Redis(connection_pool=self._pool)
            
            logger.info("🔍 [CONNECT] Redis client oluşturuldu, ping atılıyor...")
            
            client.ping()
            
            logger.info("✅ Redis bağlantısı başarılı! (Global client kullanımda)")
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
        """
        🔥 V4.8: Global client döndür (Yeni connection AÇMA!)
        """
        return self._client

    def is_enabled(self):
        return self._enabled

redis_wrapper = RedisClient()

# ======================================
# 🔥 V4.8.1: RAM CACHE (RAM OPTİMİZASYON!)
# ======================================

class RAMCache:
    """
    🔥 V4.8.1 OPTIMIZATION: RAM temizlik aralığı artırıldı
    
    ÖNCEKİ SORUN:
    - Her 5 dakikada cleanup → Gereksiz CPU/RAM kullanımı
    
    YENİ ÇÖZÜM:
    - Her 10 dakikada cleanup → %50 daha az kaynak tüketimi
    - Memory leak yine yok, ama daha verimli!
    """
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()
        
        # 🔥 V4.8.1: OTOMATIK TEMİZLİK THREAD'İ (10 DK)
        self._cleanup_thread = threading.Thread(
            target=self._auto_cleanup,
            daemon=True,
            name="RAMCacheCleanup"
        )
        self._cleanup_thread.start()
        logger.info("🧹 RAM Cache otomatik temizlik thread'i başlatıldı (10dk interval)")

    def _auto_cleanup(self):
        """
        🧹 Arka planda çalışan temizlik thread'i
        
        🔥 V4.8.1: Her 10 dakikada bir expired key'leri temizler (eski: 5dk)
        """
        while True:
            try:
                time.sleep(600)  # 🔥 10 dakika bekle (eski: 300)
                
                with self._lock:
                    current_time = time.time()
                    keys_to_delete = []
                    
                    # Expired key'leri bul
                    for key, (value, expiry) in self._cache.items():
                        if expiry > 0 and current_time > expiry:
                            keys_to_delete.append(key)
                    
                    # Temizle
                    for key in keys_to_delete:
                        del self._cache[key]
                    
                    if keys_to_delete:
                        logger.info(f"🧹 RAM Cache temizlendi: {len(keys_to_delete)} expired key silindi")
                
            except Exception as e:
                logger.error(f"❌ RAM Cache cleanup hatası: {e}")
                time.sleep(60)  # Hata durumunda 1 dakika bekle

    def set(self, key: str, value: Any, ttl: int = 0):
        with self._lock:
            expiry = time.time() + ttl if ttl > 0 else 0
            self._cache[key] = (value, expiry)

    def get(self, key: str):
        with self._lock:
            if key not in self._cache:
                return None
            
            value, expiry = self._cache[key]
            
            if expiry > 0 and time.time() > expiry:
                del self._cache[key]
                return None
                
            return value
    
    def exists(self, key: str) -> bool:
        with self._lock:
            if key not in self._cache:
                return False
            
            value, expiry = self._cache[key]
            
            if expiry > 0 and time.time() > expiry:
                del self._cache[key]
                return False
            
            return True
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def incr(self, key: str, ttl: int = 0) -> int:
        """Atomik increment (RAM için thread-safe)"""
        with self._lock:
            current_value = 0
            
            if key in self._cache:
                value, expiry = self._cache[key]
                
                if expiry == 0 or time.time() <= expiry:
                    current_value = int(value) if isinstance(value, (int, str)) else 0
                else:
                    del self._cache[key]
            
            new_value = current_value + 1
            
            expiry = time.time() + ttl if ttl > 0 else 0
            self._cache[key] = (new_value, expiry)
            
            return new_value
    
    def keys(self, pattern: str = "*"):
        with self._lock:
            if pattern == "*":
                return list(self._cache.keys())
            
            import fnmatch
            return [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]

ram_cache = RAMCache()

# ======================================
# 🔥 V5.5: KRİTİK VERİ LİSTESİ (SNAPSHOT KEYS GÜNCELLENDI!)
# ======================================

CRITICAL_KEYS = [
    'kurabak:currencies:all',
    'kurabak:golds:all',
    'kurabak:silvers:all',
    'kurabak:summary',
    'kurabak:raw_snapshot',      # 🔥 V5.5: Ham fiyat snapshot'ı (disk backup!)
    'kurabak:jeweler_snapshot',  # 🔥 V5.5: Kuyumcu fiyat snapshot'ı (disk backup!)
    'kurabak:backup:all'
]

# ======================================
# PUBLIC API
# ======================================

def get_cache(key: str) -> Optional[Any]:
    """
    🔥 V4.8 FIX: Global client kullanımı
    
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
            logger.warning(f"⚠️ Redis Okuma Hatası: {e}")
    
    # 2. RAM Denemesi
    ram_data = ram_cache.get(key)
    if ram_data:
        return ram_data
    
    # 3. Disk Denemesi
    if key in CRITICAL_KEYS:
        logger.warning(f"🔥 [{key}] Redis ve RAM'de yok, DISK'ten yükleniyor...")
        disk_data = disk_backup.load(key)
        if disk_data:
            logger.info(f"✅ [{key}] Disk'ten başarıyla kurtarıldı!")
            ram_cache.set(key, disk_data, ttl=0)
            return disk_data
    
    return None


def set_cache(key: str, data: Any, ttl: int = 300, force_disk_backup: bool = False) -> bool:
    """
    🔥 V4.8 FIX: Disk backup optimize edildi
    
    Cache'e veri yazar + SADECE force_disk_backup=True ise disk'e yazar
    
    Args:
        key: Cache key
        data: Veri
        ttl: TTL (saniye, 0=süresiz)
        force_disk_backup: True ise kritik key'leri disk'e de yaz
    """
    success = False
    
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
                client.setex(key, ttl, json_data)
            else:
                client.set(key, json_data)
            success = True
        except Exception as e:
            logger.error(f"❌ Redis Yazma Hatası: {e}")

    # 2. RAM Yazma
    ram_cache.set(key, data, ttl)
    
    # 3. 🔥 V4.8: DISK BACKUP - Sadece force_disk_backup=True ise!
    if force_disk_backup and key in CRITICAL_KEYS:
        disk_backup.save(key, data)
        logger.debug(f"💾 [{key}] Disk'e yedeklendi")
    
    return success or True


def incr_cache(key: str, ttl: int = 0) -> int:
    """
    Atomik increment (Redis INCR veya RAM thread-safe)
    """
    client = redis_wrapper.get_client()
    
    if client:
        try:
            new_value = client.incr(key)
            
            if ttl > 0 and new_value == 1:
                client.expire(key, ttl)
            
            return new_value
            
        except Exception as e:
            logger.warning(f"⚠️ Redis INCR hatası: {e}")
    
    return ram_cache.incr(key, ttl)


def cache_exists(key: str) -> bool:
    """Key var mı kontrol et (Redis → RAM → Disk)"""
    client = redis_wrapper.get_client()
    
    if client:
        try:
            return bool(client.exists(key))
        except Exception as e:
            logger.warning(f"⚠️ Redis EXISTS hatası: {e}")
    
    if ram_cache.exists(key):
        return True
    
    if key in CRITICAL_KEYS:
        return disk_backup.load(key) is not None
    
    return False


def delete_cache(key: str) -> bool:
    """Key'i sil (Redis + RAM + Disk)"""
    success = False
    client = redis_wrapper.get_client()
    
    if client:
        try:
            client.delete(key)
            success = True
        except Exception as e:
            logger.warning(f"⚠️ Redis DELETE hatası: {e}")
    
    ram_cache.delete(key)
    
    if key in CRITICAL_KEYS:
        disk_backup.delete(key)
    
    return success or True


def get_cache_keys(pattern: str = "*"):
    """Pattern'e uyan tüm key'leri döndür"""
    client = redis_wrapper.get_client()
    
    if client:
        try:
            return [k.decode() if isinstance(k, bytes) else k 
                    for k in client.keys(pattern)]
        except Exception as e:
            logger.warning(f"⚠️ Redis KEYS hatası: {e}")
    
    ram_keys = ram_cache.keys(pattern)
    disk_keys = disk_backup.list_keys()
    
    all_keys = set(ram_keys + disk_keys)
    
    if pattern != "*":
        import fnmatch
        all_keys = {k for k in all_keys if fnmatch.fnmatch(k, pattern)}
    
    return list(all_keys)


def flush_all_cache() -> bool:
    """TÜM cache'i temizle (Redis + RAM + Disk)"""
    success = False
    client = redis_wrapper.get_client()
    
    if client:
        try:
            client.flushall()
            logger.warning("🧹 Redis tamamen temizlendi!")
            success = True
        except Exception as e:
            logger.error(f"❌ Redis FLUSHALL hatası: {e}")
    
    ram_cache._cache.clear()
    logger.warning("🧹 RAM Cache temizlendi!")
    
    for key in CRITICAL_KEYS:
        disk_backup.delete(key)
    logger.warning("🧹 Disk Backup temizlendi!")
    
    return success or True


def cleanup_old_disk_backups(max_age_days: int = 7) -> dict:
    """🧹 Eski disk backup'larını temizle"""
    before_stats = disk_backup.get_backup_stats()
    deleted_count = disk_backup.cleanup_old_backups(max_age_days)
    after_stats = disk_backup.get_backup_stats()
    
    return {
        'deleted_count': deleted_count,
        'before_stats': before_stats,
        'after_stats': after_stats
    }


def get_disk_backup_stats() -> dict:
    """📊 Disk backup istatistiklerini getir"""
    return disk_backup.get_backup_stats()


def get_redis_client():
    """
    Redis client'ı döndür (FCM notification için)
    """
    return redis_wrapper.get_client()


def recover_from_disk():
    """Uygulama başlatılırken disk'ten kritik verileri yükle"""
    logger.info("🔄 Disk'ten veri kurtarma kontrolü başlatılıyor...")
    
    recovered_count = 0
    
    for key in CRITICAL_KEYS:
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

recover_from_disk()


# ======================================
# 🔥 V5.6: SCHEDULER LOCK (circular import fix)
# Buraya taşındı: app.py → maintenance_service.py → app.py döngüsü kırıldı.
# app.py ve maintenance_service.py her ikisi de buradan import eder.
# ======================================

SCHEDULER_LOCK_KEY = "kurabak:scheduler:lock"
SCHEDULER_LOCK_TTL = 120  # 2 dakika — worker her 60s'de yeniler, çökerse 120s'de kalkar


def renew_scheduler_lock():
    """
    Scheduler'ın hâlâ yaşadığını Redis'e bildirir.
    maintenance_service.py içindeki worker_job her çalışmasında (60s) bunu çağırır.
    Sunucu çökerse SCHEDULER_LOCK_TTL sonunda lock otomatik kalkar,
    yeni Render worker'ı devralır.
    """
    try:
        client = get_redis_client()
        if client:
            client.set(SCHEDULER_LOCK_KEY, os.getpid(), ex=SCHEDULER_LOCK_TTL)
    except Exception:
        pass  # Lock yenileme kritik değil, sessizce geç
