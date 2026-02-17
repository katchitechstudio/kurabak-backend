import logging
import json
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from config import Config
from utils.cache import get_cache, get_redis_client

logger = logging.getLogger("KuraBak.AlarmService")

def get_current_price(currency_code: str, profile: str = "jeweler") -> Optional[float]:
    try:
        original_code = currency_code
        if currency_code.startswith("FOREX_"):
            currency_code = currency_code.replace("FOREX_", "")
        elif currency_code.startswith("SILVER_"):
            currency_code = currency_code.replace("SILVER_", "")
        elif currency_code.startswith("GOLD_"):
            currency_code = currency_code.replace("GOLD_", "")
        
        if profile == "raw":
            currencies_key = Config.CACHE_KEYS['currencies_all']
            golds_key = Config.CACHE_KEYS['golds_all']
            silvers_key = Config.CACHE_KEYS['silvers_all']
        else:
            currencies_key = Config.CACHE_KEYS['currencies_jeweler']
            golds_key = Config.CACHE_KEYS['golds_jeweler']
            silvers_key = Config.CACHE_KEYS['silvers_jeweler']
        
        currencies_data = get_cache(currencies_key)
        
        if currencies_data:
            for item in currencies_data.get('data', []):
                if item.get('code') == currency_code:
                    return item.get('selling', 0)
        
        golds_data = get_cache(golds_key)
        
        if golds_data:
            for item in golds_data.get('data', []):
                if item.get('code') == currency_code:
                    return item.get('selling', 0)
        
        silvers_data = get_cache(silvers_key)
        
        if silvers_data:
            for item in silvers_data.get('data', []):
                if item.get('code') == currency_code:
                    return item.get('selling', 0)
        
        logger.debug(f"🔍 [ALARM] Fiyat aranıyor: {original_code} → {currency_code} ({profile})")
        return None
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Fiyat alma hatası ({currency_code}, {profile}): {e}")
        return None

def extract_fcm_token_from_key(alarm_key: str) -> Optional[str]:
    try:
        parts = alarm_key.split(':')
        if len(parts) >= 2:
            return parts[1]
        return None
    except:
        return None

def get_fcm_token_from_hash(token_hash: str) -> Optional[str]:
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return None
        
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
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return
        
        mapping_key = f"fcm_token_map:{token_hash}"
        
        redis_client.setex(mapping_key, 90 * 24 * 60 * 60, fcm_token)
        
    except Exception as e:
        logger.warning(f"⚠️ [ALARM] Token mapping kayıt hatası: {e}")

def validate_fcm_token(fcm_token: str) -> bool:
    try:
        if not fcm_token or not isinstance(fcm_token, str):
            return False
        
        if len(fcm_token) < 100:
            logger.warning(f"⚠️ [ALARM] Token çok kısa: {len(fcm_token)} karakter")
            return False
        
        if ' ' in fcm_token:
            logger.warning(f"⚠️ [ALARM] Token boşluk içeriyor!")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Token validasyon hatası: {e}")
        return False

def check_alarm_trigger(alarm_data: dict, current_price: float) -> bool:
    try:
        alarm_mode = alarm_data.get('alarm_mode', 'PRICE').upper()
        
        if alarm_mode == 'PERCENT':
            start_price = alarm_data.get('start_price', 0)
            percent_value = alarm_data.get('percent_value', 0)
            percent_direction = alarm_data.get('percent_direction', '').upper()
            
            if start_price <= 0 or percent_value <= 0:
                return False
            
            change_percent = ((current_price - start_price) / start_price) * 100
            
            if percent_direction == 'UP':
                return change_percent >= percent_value
            elif percent_direction == 'DOWN':
                return change_percent <= -percent_value
            
            return False
        else:
            target_price = alarm_data.get('target_price', 0)
            alarm_type = alarm_data.get('alarm_type', '').upper()
            
            if alarm_type == 'HIGH':
                return current_price >= target_price
            elif alarm_type == 'LOW':
                return current_price <= target_price
            
            return False
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Trigger kontrolü hatası: {e}")
        return False

def send_alarm_notification_legacy(fcm_token: str, alarm_data: dict, current_price: float) -> bool:
    try:
        from utils.notification_service import send_alarm_notification
        
        currency_code = alarm_data.get('currency_code', '')
        currency_name = alarm_data.get('currency_name', 'Varlık')
        target_price = alarm_data.get('target_price', 0)
        start_price = alarm_data.get('start_price', current_price)
        alarm_type = alarm_data.get('alarm_type', 'HIGH')
        
        success = send_alarm_notification(
            fcm_token=fcm_token,
            currency_code=currency_code,
            currency_name=currency_name,
            target_price=target_price,
            current_price=current_price,
            start_price=start_price,
            alarm_type=alarm_type
        )
        
        if success:
            logger.info(f"✅ [ALARM] Bildirim gönderildi: {currency_name} → ₺{current_price:,.2f}")
            return True
        else:
            logger.error(f"❌ [ALARM] Bildirim gönderilemedi: {currency_name}")
            return False
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Bildirim gönderme hatası: {e}")
        return False

def get_all_alarm_keys_safe(redis_client) -> List[str]:
    try:
        alarm_keys = []
        cursor = 0
        
        while True:
            cursor, keys = redis_client.scan(
                cursor=cursor,
                match="alarm:*",
                count=100
            )
            
            for key in keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                
                if key_str.startswith("alarm:fcm_token_map:"):
                    continue
                if key_str == "alarm:price:last_check":
                    continue
                
                parts = key_str.split(':')
                if len(parts) >= 4:
                    alarm_keys.append(key_str)
            
            if cursor == 0:
                break
        
        return alarm_keys
        
    except Exception as e:
        logger.error(f"❌ [ALARM] SCAN hatası: {e}")
        return []

def check_all_alarms() -> Dict:
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
        
        alarm_keys = get_all_alarm_keys_safe(redis_client)
        
        total_alarms = len(alarm_keys)
        
        if total_alarms == 0:
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
        
        for key in alarm_keys:
            try:
                alarm_data = redis_client.get(key)
                
                if not alarm_data:
                    failed_count += 1
                    continue
                
                if isinstance(alarm_data, bytes):
                    alarm_data = alarm_data.decode('utf-8')
                
                alarm_obj = json.loads(alarm_data)
                
                if not alarm_obj.get('is_active', True):
                    continue
                
                checked_count += 1
                
                currency_code = alarm_obj.get('currency_code')
                if not currency_code:
                    failed_count += 1
                    continue
                
                alarm_profile = alarm_obj.get('profile', 'jeweler')
                
                current_price = get_current_price(currency_code, profile=alarm_profile)
                
                if current_price is None or current_price <= 0:
                    failed_count += 1
                    continue
                
                should_trigger = check_alarm_trigger(alarm_obj, current_price)
                
                if should_trigger:
                    logger.info(f"🎯 [ALARM] Tetiklendi: {currency_code} ({alarm_profile}) → {current_price}")
                    
                    token_hash = extract_fcm_token_from_key(key)
                    
                    if not token_hash:
                        failed_count += 1
                        continue
                    
                    fcm_token = get_fcm_token_from_hash(token_hash)
                    
                    if not fcm_token:
                        redis_client.delete(key)
                        logger.info(f"🗑️ [ALARM] Geçersiz alarm silindi: {key}")
                        failed_count += 1
                        continue
                    
                    notification_sent = send_alarm_notification_legacy(
                        fcm_token,
                        alarm_obj,
                        current_price
                    )
                    
                    redis_client.delete(key)
                    
                    if notification_sent:
                        triggered_count += 1
                    else:
                        failed_count += 1
                
            except json.JSONDecodeError:
                failed_count += 1
                continue
                
            except Exception as alarm_err:
                logger.error(f"❌ [ALARM] Kontrol hatası ({key}): {alarm_err}")
                failed_count += 1
                continue
        
        duration_ms = (time.time() - start_time) * 1000
        
        result = {
            'total_alarms': total_alarms,
            'checked': checked_count,
            'triggered': triggered_count,
            'failed': failed_count,
            'duration_ms': round(duration_ms, 2)
        }
        
        if triggered_count > 0:
            logger.info(f"🔔 [ALARM] {triggered_count} alarm tetiklendi!")
        elif failed_count > 5:
            logger.warning(f"⚠️ [ALARM] {failed_count} hata!")
        
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

def get_alarm_stats() -> Dict:
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return {
                'total_alarms': 0,
                'unique_users': 0,
                'alarm_types': {'HIGH': 0, 'LOW': 0}
            }
        
        alarm_keys = get_all_alarm_keys_safe(redis_client)
        
        total_alarms = len(alarm_keys)
        
        unique_users = set()
        high_count = 0
        low_count = 0
        
        for key in alarm_keys:
            try:
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
    logger.info("🚀 [ALARM] Manuel kontrol tetiklendi")
    return check_all_alarms()
