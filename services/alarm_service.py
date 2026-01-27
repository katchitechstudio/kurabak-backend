"""
Alarm Service - PRODUCTION READY V1.1 🚀
==========================================================
✅ PERIODIC CHECK: Her 5-15 dakikada alarmları kontrol eder
✅ FCM NOTIFICATION: Hedef tuttuğunda bildirim gönderir
✅ AUTO CLEANUP: Tetiklenen alarmları otomatik siler
✅ PRICE MATCHING: Currencies cache'inden fiyat karşılaştırması
✅ BATCH PROCESSING: Tüm alarmları verimli şekilde işler
✅ ERROR HANDLING: Hata durumunda sistem durmasın
✅ LOGGING: Detaylı log sistemi
✅ KEY FILTERING: Geçersiz key'leri otomatik filtreler
"""

import logging
import json
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from config import Config
from utils.cache import get_cache, get_redis_client
from utils.notification_service import send_notification

logger = logging.getLogger("KuraBak.AlarmService")

# ======================================
# HELPER FUNCTIONS
# ======================================

def get_current_price(currency_code: str) -> Optional[float]:
    """
    Currencies cache'inden güncel fiyatı al
    
    Args:
        currency_code: Döviz kodu (USD, EUR, GRA vb.)
        
    Returns:
        float: Güncel fiyat (selling)
        None: Fiyat bulunamazsa
    """
    try:
        # Önce currencies'e bak
        currencies_data = get_cache(Config.CACHE_KEYS['currencies_all'])
        
        if currencies_data:
            for item in currencies_data.get('data', []):
                if item.get('code') == currency_code:
                    return item.get('selling', 0)
        
        # Bulamazsa gold'a bak
        golds_data = get_cache(Config.CACHE_KEYS['golds_all'])
        
        if golds_data:
            for item in golds_data.get('data', []):
                if item.get('code') == currency_code:
                    return item.get('selling', 0)
        
        # Bulamazsa silver'a bak
        silvers_data = get_cache(Config.CACHE_KEYS['silvers_all'])
        
        if silvers_data:
            for item in silvers_data.get('data', []):
                if item.get('code') == currency_code:
                    return item.get('selling', 0)
        
        return None
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Fiyat alma hatası ({currency_code}): {e}")
        return None


def extract_fcm_token_from_key(alarm_key: str) -> Optional[str]:
    """
    Redis key'den FCM token hash'ini çıkar
    
    Format: alarm:TOKEN_HASH:CURRENCY:TYPE
    
    Args:
        alarm_key: Redis alarm key
        
    Returns:
        str: Token hash
        None: Parse edilemezse
    """
    try:
        parts = alarm_key.split(':')
        if len(parts) >= 2:
            return parts[1]  # Token hash
        return None
    except:
        return None


def get_fcm_token_from_hash(token_hash: str) -> Optional[str]:
    """
    Token hash'inden gerçek FCM token'ı bul
    
    NOT: Bu fonksiyon token hash'ini kullanarak Redis'teki
    FCM token set'inden gerçek token'ı bulmaya çalışır.
    
    Ancak biz token'ı hash'lediğimiz için geriye dönüşüm yok.
    Bu yüzden Redis'e ayrı bir mapping kaydediyoruz.
    
    Args:
        token_hash: SHA256 token hash'i
        
    Returns:
        str: Gerçek FCM token
        None: Bulunamazsa
    """
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return None
        
        # Mapping key: fcm_token_map:HASH → TOKEN
        mapping_key = f"fcm_token_map:{token_hash}"
        fcm_token = redis_client.get(mapping_key)
        
        if fcm_token:
            if isinstance(fcm_token, bytes):
                fcm_token = fcm_token.decode('utf-8')
            return fcm_token
        
        return None
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Token mapping hatası: {e}")
        return None


def save_fcm_token_mapping(fcm_token: str, token_hash: str):
    """
    FCM token hash mapping'i kaydet
    
    Bu sayede alarm tetiklendiğinde hash'ten gerçek token'ı bulabiliriz.
    
    Args:
        fcm_token: Gerçek FCM token
        token_hash: SHA256 hash
    """
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return
        
        mapping_key = f"fcm_token_map:{token_hash}"
        
        # 90 gün TTL (alarm TTL ile aynı)
        redis_client.setex(mapping_key, 90 * 24 * 60 * 60, fcm_token)
        
    except Exception as e:
        logger.warning(f"⚠️ [ALARM] Token mapping kayıt hatası: {e}")


def check_alarm_trigger(alarm_data: dict, current_price: float) -> bool:
    """
    Alarmın tetiklenmesi gerekip gerekmediğini kontrol et
    
    Args:
        alarm_data: Alarm objesi (Redis'ten)
        current_price: Güncel fiyat
        
    Returns:
        bool: Tetiklenmeli mi?
    """
    try:
        target_price = alarm_data.get('target_price', 0)
        alarm_type = alarm_data.get('alarm_type', '').upper()
        
        if alarm_type == 'HIGH':
            # Yükseliş alarmı: Mevcut fiyat >= Hedef fiyat
            return current_price >= target_price
        
        elif alarm_type == 'LOW':
            # Düşüş alarmı: Mevcut fiyat <= Hedef fiyat
            return current_price <= target_price
        
        return False
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Trigger kontrolü hatası: {e}")
        return False


def send_alarm_notification(fcm_token: str, alarm_data: dict, current_price: float) -> bool:
    """
    Alarm bildirimi gönder
    
    Args:
        fcm_token: Firebase Cloud Messaging token
        alarm_data: Alarm objesi
        current_price: Güncel fiyat
        
    Returns:
        bool: Başarılı mı?
    """
    try:
        currency_name = alarm_data.get('currency_name', 'Varlık')
        currency_code = alarm_data.get('currency_code', '')
        target_price = alarm_data.get('target_price', 0)
        alarm_type = alarm_data.get('alarm_type', '').upper()
        
        # Emoji seç
        emoji = "📈" if alarm_type == 'HIGH' else "📉"
        
        # Bildirim metni
        if alarm_type == 'HIGH':
            title = f"{emoji} Fiyat Yükseldi!"
            body = f"{currency_name} hedef fiyatı aştı: ₺{target_price:,.2f}"
        else:
            title = f"{emoji} Fiyat Düştü!"
            body = f"{currency_name} hedef fiyatın altına düştü: ₺{target_price:,.2f}"
        
        # Data payload
        data = {
            "type": "alarm_triggered",
            "currency_code": currency_code,
            "currency_name": currency_name,
            "target_price": str(target_price),
            "current_price": str(current_price),
            "alarm_type": alarm_type,
            "timestamp": str(int(time.time()))
        }
        
        # FCM gönder (tek token)
        result = send_notification(
            tokens=[fcm_token],
            title=title,
            body=body,
            data=data,
            priority="high",
            sound="default"
        )
        
        if result.get('success'):
            logger.info(
                f"✅ [ALARM] Bildirim gönderildi: {currency_name} "
                f"→ Hedef: ₺{target_price:,.2f}, Mevcut: ₺{current_price:,.2f}"
            )
            return True
        else:
            logger.error(f"❌ [ALARM] Bildirim hatası: {result.get('error')}")
            return False
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Bildirim gönderme hatası: {e}")
        return False


# ======================================
# ANA ALARM KONTROLCÜ
# ======================================

def check_all_alarms() -> Dict:
    """
    Tüm alarmları kontrol et ve gerekirse bildirim gönder
    
    Bu fonksiyon scheduler tarafından periyodik olarak çağrılır.
    
    Returns:
        dict: {
            'total_alarms': int,
            'checked': int,
            'triggered': int,
            'failed': int,
            'duration_ms': float
        }
    """
    start_time = time.time()
    
    try:
        logger.info("🔔 [ALARM] Periyodik kontrol başlatıldı...")
        
        redis_client = get_redis_client()
        if not redis_client:
            logger.error("❌ [ALARM] Redis bağlantısı yok!")
            return {
                'total_alarms': 0,
                'checked': 0,
                'triggered': 0,
                'failed': 0,
                'duration_ms': 0,
                'error': 'Redis connection failed'
            }
        
        # Tüm alarmları al
        all_alarm_keys = redis_client.keys("alarm:*")
        
        # Geçersiz key'leri filtrele
        alarm_keys = []
        for key in all_alarm_keys:
            # Bytes'tan string'e çevir
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            
            # Bu key'leri atla
            if key_str.startswith("fcm_token_map:"):
                continue
            if key_str == "alarm:price:last_check":
                continue
            
            # Geçerli alarm key formatı: alarm:HASH:CODE:TYPE (4 parça)
            parts = key_str.split(':')
            if len(parts) == 4:
                alarm_keys.append(key)
        
        total_alarms = len(alarm_keys)
        
        if total_alarms == 0:
            logger.info("ℹ️ [ALARM] Kontrol edilecek alarm yok")
            return {
                'total_alarms': 0,
                'checked': 0,
                'triggered': 0,
                'failed': 0,
                'duration_ms': 0
            }
        
        logger.info(f"📊 [ALARM] {total_alarms} alarm kontrol ediliyor...")
        
        checked_count = 0
        triggered_count = 0
        failed_count = 0
        
        # Her bir alarm için kontrol
        for key in alarm_keys:
            try:
                # Bytes'tan string'e çevir
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                # Alarm verisini al
                alarm_data = redis_client.get(key)
                
                if not alarm_data:
                    logger.warning(f"⚠️ [ALARM] Veri bulunamadı: {key}")
                    failed_count += 1
                    continue
                
                # JSON parse et
                if isinstance(alarm_data, bytes):
                    alarm_data = alarm_data.decode('utf-8')
                
                alarm_obj = json.loads(alarm_data)
                
                # Aktif mi kontrol et
                if not alarm_obj.get('is_active', True):
                    logger.debug(f"⏸️ [ALARM] Pasif alarm atlandı: {key}")
                    continue
                
                checked_count += 1
                
                # Currency code
                currency_code = alarm_obj.get('currency_code')
                if not currency_code:
                    logger.warning(f"⚠️ [ALARM] Currency code yok: {key}")
                    failed_count += 1
                    continue
                
                # Güncel fiyatı al
                current_price = get_current_price(currency_code)
                
                if current_price is None or current_price <= 0:
                    logger.warning(f"⚠️ [ALARM] Fiyat bulunamadı: {currency_code}")
                    failed_count += 1
                    continue
                
                # Alarm tetiklenmeli mi?
                should_trigger = check_alarm_trigger(alarm_obj, current_price)
                
                if should_trigger:
                    logger.info(f"🎯 [ALARM] Tetiklendi: {currency_code} → {current_price}")
                    
                    # Token hash'ini al
                    token_hash = extract_fcm_token_from_key(key)
                    
                    if not token_hash:
                        logger.error(f"❌ [ALARM] Token hash parse edilemedi: {key}")
                        failed_count += 1
                        continue
                    
                    # Gerçek FCM token'ı bul
                    fcm_token = get_fcm_token_from_hash(token_hash)
                    
                    if not fcm_token:
                        logger.error(f"❌ [ALARM] FCM token bulunamadı: {token_hash}")
                        failed_count += 1
                        
                        # Token bulunamadıysa alarm'ı sil (geçersiz)
                        redis_client.delete(key)
                        logger.info(f"🗑️ [ALARM] Geçersiz alarm silindi: {key}")
                        continue
                    
                    # Bildirim gönder
                    notification_sent = send_alarm_notification(
                        fcm_token,
                        alarm_obj,
                        current_price
                    )
                    
                    if notification_sent:
                        # Başarılı → Alarm'ı sil (tek seferlik)
                        redis_client.delete(key)
                        triggered_count += 1
                        logger.info(f"✅ [ALARM] Bildirim gönderildi ve alarm silindi: {currency_code}")
                    else:
                        # Bildirim gönderilemedi ama tetiklendi
                        # Alarm'ı yine de sil (sürekli denemesin)
                        redis_client.delete(key)
                        failed_count += 1
                        logger.warning(f"⚠️ [ALARM] Bildirim gönderilemedi ama alarm silindi: {currency_code}")
                
            except json.JSONDecodeError as json_err:
                logger.error(f"❌ [ALARM] JSON parse hatası ({key}): {json_err}")
                failed_count += 1
                continue
                
            except Exception as alarm_err:
                logger.error(f"❌ [ALARM] Alarm kontrolü hatası ({key}): {alarm_err}")
                failed_count += 1
                continue
        
        # Süre hesapla
        duration_ms = (time.time() - start_time) * 1000
        
        # Sonuç
        result = {
            'total_alarms': total_alarms,
            'checked': checked_count,
            'triggered': triggered_count,
            'failed': failed_count,
            'duration_ms': round(duration_ms, 2)
        }
        
        logger.info(
            f"✅ [ALARM] Kontrol tamamlandı: "
            f"{checked_count} kontrol edildi, "
            f"{triggered_count} tetiklendi, "
            f"{failed_count} hata ({duration_ms:.2f}ms)"
        )
        
        return result
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ [ALARM] Genel kontrol hatası: {e}")
        
        return {
            'total_alarms': 0,
            'checked': 0,
            'triggered': 0,
            'failed': 0,
            'duration_ms': round(duration_ms, 2),
            'error': str(e)
        }


# ======================================
# YARDIMCI FONKSİYONLAR (Public API)
# ======================================

def get_alarm_stats() -> Dict:
    """
    Alarm sistemi istatistiklerini döner
    
    Returns:
        dict: {
            'total_alarms': int,
            'unique_users': int,
            'alarm_types': {'HIGH': int, 'LOW': int}
        }
    """
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return {
                'total_alarms': 0,
                'unique_users': 0,
                'alarm_types': {'HIGH': 0, 'LOW': 0}
            }
        
        # Tüm alarmları al
        all_alarm_keys = redis_client.keys("alarm:*")
        
        # Geçersiz key'leri filtrele
        alarm_keys = []
        for key in all_alarm_keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            
            if key_str.startswith("fcm_token_map:"):
                continue
            if key_str == "alarm:price:last_check":
                continue
            
            parts = key_str.split(':')
            if len(parts) == 4:
                alarm_keys.append(key)
        
        total_alarms = len(alarm_keys)
        
        # Benzersiz kullanıcılar ve alarm tipleri
        unique_users = set()
        high_count = 0
        low_count = 0
        
        for key in alarm_keys:
            try:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                # alarm:HASH:CODE:TYPE formatından parse et
                parts = key.split(':')
                if len(parts) >= 4:
                    token_hash = parts[1]
                    alarm_type = parts[3]
                    
                    unique_users.add(token_hash)
                    
                    if alarm_type == 'HIGH':
                        high_count += 1
                    elif alarm_type == 'LOW':
                        low_count += 1
                        
            except:
                continue
        
        return {
            'total_alarms': total_alarms,
            'unique_users': len(unique_users),
            'alarm_types': {
                'HIGH': high_count,
                'LOW': low_count
            }
        }
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Stats hatası: {e}")
        return {
            'total_alarms': 0,
            'unique_users': 0,
            'alarm_types': {'HIGH': 0, 'LOW': 0}
        }


def trigger_immediate_check() -> Dict:
    """
    Anında alarm kontrolü tetikle (Manuel test için)
    
    Returns:
        dict: check_all_alarms() sonucu
    """
    logger.info("🚀 [ALARM] Manuel kontrol tetiklendi")
    return check_all_alarms()
