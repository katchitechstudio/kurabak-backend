"""
Maintenance Service - PRODUCTION READY V3.0 🚧
===============================================
✅ BAKIM MODU: Tek basit bakım senaryosu (banner ile bilgilendirme)
✅ SADECE V5 API: V4/V3 tamamen kaldırıldı
✅ BANNER SİSTEMİ: Uygulama tarafına özel mesaj gönderme
✅ THREAD-SAFE: Güvenli veri erişimi
✅ SMART RECOVERY: Sistem çökerse otomatik kurtarma
"""

import logging
import time
from typing import Optional, Dict, Any

from utils.cache import get_cache, set_cache, delete_cache
from config import Config

logger = logging.getLogger(__name__)

# ======================================
# BAKIM MODU YÖNETİMİ
# ======================================

def check_maintenance_status() -> Dict[str, Any]:
    """
    Bakım modunu kontrol eder.
    
    Returns:
        Dict: {
            'is_active': bool,
            'banner_message': str or None
        }
    """
    maintenance_data = get_cache(Config.CACHE_KEYS['maintenance'])
    
    if not maintenance_data:
        return {
            'is_active': False,
            'banner_message': None
        }
    
    return {
        'is_active': True,
        'banner_message': maintenance_data.get('message', Config.MAINTENANCE_DEFAULT_MESSAGE)
    }


def activate_maintenance(message: Optional[str] = None) -> bool:
    """
    Bakım modunu aktif eder.
    
    Args:
        message: Özel bakım mesajı (opsiyonel)
    
    Returns:
        bool: Başarılı mı?
    """
    try:
        banner_msg = message or Config.MAINTENANCE_DEFAULT_MESSAGE
        
        maintenance_data = {
            'message': banner_msg,
            'activated_at': time.time()
        }
        
        # Süresiz kaydet (ttl=0)
        set_cache(Config.CACHE_KEYS['maintenance'], maintenance_data, ttl=0)
        
        logger.info(f"🚧 Bakım modu aktif edildi: {banner_msg}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Bakım modu aktif etme hatası: {e}")
        return False


def deactivate_maintenance() -> bool:
    """
    Bakım modunu kapatır.
    
    Returns:
        bool: Başarılı mı?
    """
    try:
        delete_cache(Config.CACHE_KEYS['maintenance'])
        logger.info("✅ Bakım modu kapatıldı")
        return True
        
    except Exception as e:
        logger.error(f"❌ Bakım modu kapatma hatası: {e}")
        return False


# ======================================
# BANNER YÖNETİMİ
# ======================================

def set_banner(message: str, ttl: int = 0) -> bool:
    """
    Banner mesajı ayarlar.
    
    Args:
        message: Banner mesajı
        ttl: Süreli mi? (0 = süresiz, >0 = saniye)
    
    Returns:
        bool: Başarılı mı?
    """
    try:
        set_cache(Config.CACHE_KEYS['banner'], message, ttl=ttl)
        logger.info(f"📢 Banner ayarlandı: {message} (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.error(f"❌ Banner ayarlama hatası: {e}")
        return False


def clear_banner() -> bool:
    """
    Banner mesajını kaldırır.
    
    Returns:
        bool: Başarılı mı?
    """
    try:
        delete_cache(Config.CACHE_KEYS['banner'])
        logger.info("🔇 Banner kaldırıldı")
        return True
    except Exception as e:
        logger.error(f"❌ Banner kaldırma hatası: {e}")
        return False


def get_current_banner() -> Optional[str]:
    """
    Mevcut banner mesajını getirir.
    
    Priority:
    1. Bakım modu aktifse -> Bakım mesajı
    2. Manuel banner varsa -> Manuel banner
    3. Hiçbiri yoksa -> None
    
    Returns:
        str or None: Banner mesajı
    """
    # 1. Bakım modu kontrolü (öncelik #1)
    maintenance = check_maintenance_status()
    if maintenance['is_active']:
        return maintenance['banner_message']
    
    # 2. Manuel banner kontrolü
    banner = get_cache(Config.CACHE_KEYS['banner'])
    if banner:
        return banner
    
    # 3. Banner yok
    return None


# ======================================
# VERİ GÜVENLİĞİ (SADECE V5)
# ======================================

def fetch_all_data_safe() -> bool:
    """
    Acil durumda tüm verileri yeniden çeker (Sadece V5).
    
    Returns:
        bool: Başarılı mı?
    """
    try:
        logger.info("🔄 Acil veri çekimi başlatılıyor (V5 API)...")
        
        # financial_service'den veri çek
        from services.financial_service import update_financial_data
        
        success = update_financial_data()
        
        if success:
            logger.info("✅ Acil veri çekimi başarılı")
        else:
            logger.error("❌ Acil veri çekimi başarısız")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Acil veri çekimi hatası: {e}")
        return False


# ======================================
# SCHEDULER STATUS (ŞEF İÇİN)
# ======================================

def get_scheduler_status() -> Dict[str, Any]:
    """
    Zamanlayıcı durumunu döner (Şef için).
    
    Returns:
        Dict: Scheduler bilgileri
    """
    try:
        last_worker_run = get_cache(Config.CACHE_KEYS['last_worker_run'])
        
        status = {
            'last_worker_run': last_worker_run,
            'worker_interval': Config.UPDATE_INTERVAL,
            'alarm_interval': Config.ALARM_CHECK_INTERVAL,
            'maintenance_active': check_maintenance_status()['is_active']
        }
        
        return status
        
    except Exception as e:
        logger.error(f"❌ Scheduler status hatası: {e}")
        return {}
