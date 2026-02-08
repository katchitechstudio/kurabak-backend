from flask import Blueprint, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
import time
from datetime import datetime
import json

from config import Config
from utils.cache import get_cache, set_cache, get_redis_client
from services.alarm_service import save_fcm_token_mapping

logger = logging.getLogger(__name__)

alarm_bp = Blueprint('alarm', __name__, url_prefix='/api/alarm')

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"],
    storage_uri=Config.REDIS_URL or "memory://",
    strategy="fixed-window"
)

def create_alarm_key(fcm_token: str, currency_code: str, alarm_type: str, profile: str) -> str:
    import hashlib
    token_hash = hashlib.sha256(fcm_token.encode()).hexdigest()[:16]
    return f"alarm:{token_hash}:{currency_code}:{alarm_type}:{profile}"

def get_user_alarm_pattern(fcm_token: str) -> str:
    import hashlib
    token_hash = hashlib.sha256(fcm_token.encode()).hexdigest()[:16]
    return f"alarm:{token_hash}:*"

def validate_alarm_data(data: dict) -> tuple:
    required_fields = ['fcm_token', 'currency_code', 'currency_name', 'target_price', 'alarm_type']
    
    for field in required_fields:
        if field not in data:
            return False, f"{field} eksik"
    
    fcm_token = data['fcm_token'].strip()
    if len(fcm_token) < 100:
        return False, "Geçersiz FCM token"
    
    currency_code = data['currency_code'].strip().upper()
    if not currency_code or len(currency_code) > 10:
        return False, "Geçersiz currency_code"
    
    try:
        target_price = float(data['target_price'])
        if target_price <= 0:
            return False, "Hedef fiyat 0'dan büyük olmalı"
    except (ValueError, TypeError):
        return False, "Geçersiz target_price formatı"
    
    if 'start_price' in data:
        try:
            start_price = float(data['start_price'])
            if start_price <= 0:
                return False, "Başlangıç fiyatı 0'dan büyük olmalı"
        except (ValueError, TypeError):
            return False, "Geçersiz start_price formatı"
    
    alarm_type = data['alarm_type'].strip().upper()
    if alarm_type not in ['HIGH', 'LOW']:
        return False, "alarm_type sadece HIGH veya LOW olabilir"
    
    alarm_mode = data.get('alarm_mode', 'PRICE').strip().upper()
    if alarm_mode not in ['PRICE', 'PERCENT']:
        return False, "alarm_mode sadece PRICE veya PERCENT olabilir"
    
    profile = data.get('profile', 'jeweler').strip().lower()
    if profile not in ['raw', 'jeweler']:
        return False, "profile sadece raw veya jeweler olabilir"
    
    if alarm_mode == 'PERCENT':
        if 'percent_value' not in data:
            return False, "percent_value gerekli"
        
        try:
            percent_value = float(data['percent_value'])
            if percent_value <= 0 or percent_value > 100:
                return False, "percent_value 0-100 arasında olmalı"
        except (ValueError, TypeError):
            return False, "Geçersiz percent_value formatı"
        
        if 'percent_direction' not in data:
            return False, "percent_direction gerekli"
        
        percent_direction = data['percent_direction'].strip().upper()
        if percent_direction not in ['UP', 'DOWN']:
            return False, "percent_direction sadece UP veya DOWN olabilir"
    
    return True, None

def parse_alarm_data(data: dict) -> dict:
    alarm_obj = {
        'currency_code': data['currency_code'].strip().upper(),
        'currency_name': data['currency_name'].strip(),
        'target_price': float(data['target_price']),
        'start_price': float(data.get('start_price', 0)),
        'alarm_type': data['alarm_type'].strip().upper(),
        'alarm_mode': data.get('alarm_mode', 'PRICE').strip().upper(),
        'profile': data.get('profile', 'jeweler').strip().lower(),
        'created_at': int(time.time()),
        'is_active': True
    }
    
    if alarm_obj['alarm_mode'] == 'PERCENT':
        alarm_obj['percent_value'] = float(data['percent_value'])
        alarm_obj['percent_direction'] = data['percent_direction'].strip().upper()
    else:
        alarm_obj['percent_value'] = None
        alarm_obj['percent_direction'] = None
    
    return alarm_obj

@alarm_bp.route('/create', methods=['POST'])
@limiter.limit("20 per minute")
def create_alarm():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "Request body boş olamaz"
            }), 400
        
        is_valid, error_msg = validate_alarm_data(data)
        if not is_valid:
            return jsonify({
                "success": False,
                "message": error_msg
            }), 400
        
        fcm_token = data['fcm_token'].strip()
        currency_code = data['currency_code'].strip().upper()
        alarm_type = data['alarm_type'].strip().upper()
        profile = data.get('profile', 'jeweler').strip().lower()
        
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        user_pattern = get_user_alarm_pattern(fcm_token)
        user_alarms = redis_client.keys(user_pattern)
        
        if len(user_alarms) >= Config.MAX_ALARMS_PER_USER:
            return jsonify({
                "success": False,
                "message": f"Maksimum {Config.MAX_ALARMS_PER_USER} alarm kurabilirsiniz"
            }), 400
        
        alarm_key = create_alarm_key(fcm_token, currency_code, alarm_type, profile)
        
        import hashlib
        token_hash = hashlib.sha256(fcm_token.encode()).hexdigest()[:16]
        
        save_fcm_token_mapping(fcm_token, token_hash)
        
        existing_alarm = redis_client.get(alarm_key)
        if existing_alarm:
            alarm_type_tr = "yükseliş" if alarm_type == "HIGH" else "düşüş"
            profile_tr = "ham" if profile == "raw" else "kuyumcu"
            return jsonify({
                "success": False,
                "message": f"Bu varlık için {profile_tr} fiyatında zaten bir {alarm_type_tr} alarmınız var"
            }), 409
        
        alarm_obj = parse_alarm_data(data)
        
        redis_client.setex(
            alarm_key,
            Config.ALARM_TTL,
            json.dumps(alarm_obj)
        )
        
        logger.info(
            f"✅ [ALARM] Oluşturuldu: {currency_code} ({alarm_type}, {alarm_obj['alarm_mode']}, {profile}) "
            f"→ Hedef: {alarm_obj['target_price']}"
        )
        
        return jsonify({
            "success": True,
            "message": "Alarm başarıyla oluşturuldu",
            "data": {
                "alarm_id": alarm_key,
                "currency_code": currency_code,
                "currency_name": alarm_obj['currency_name'],
                "target_price": alarm_obj['target_price'],
                "start_price": alarm_obj['start_price'],
                "alarm_type": alarm_type,
                "alarm_mode": alarm_obj['alarm_mode'],
                "profile": alarm_obj['profile'],
                "percent_value": alarm_obj.get('percent_value'),
                "percent_direction": alarm_obj.get('percent_direction'),
                "created_at": alarm_obj['created_at']
            }
        }), 201
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Oluşturma hatası: {e}")
        return jsonify({
            "success": False,
            "message": f"Sunucu hatası: {str(e)}"
        }), 500

@alarm_bp.route('/list', methods=['POST'])
@limiter.limit("30 per minute")
def list_alarms():
    try:
        data = request.get_json()
        
        if not data or 'fcm_token' not in data:
            return jsonify({
                "success": False,
                "message": "fcm_token gerekli"
            }), 400
        
        fcm_token = data['fcm_token'].strip()
        
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        user_pattern = get_user_alarm_pattern(fcm_token)
        alarm_keys = redis_client.keys(user_pattern)
        
        alarms = []
        
        for key in alarm_keys:
            try:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                alarm_data = redis_client.get(key)
                
                if alarm_data:
                    if isinstance(alarm_data, bytes):
                        alarm_data = alarm_data.decode('utf-8')
                    
                    alarm_obj = json.loads(alarm_data)
                    alarms.append(alarm_obj)
                    
            except Exception as parse_err:
                logger.warning(f"⚠️ [ALARM] Parse hatası ({key}): {parse_err}")
                continue
        
        alarms.sort(key=lambda x: x.get('created_at', 0), reverse=True)
        
        logger.info(f"📋 [ALARM] Liste çekildi: {len(alarms)} alarm")
        
        return jsonify({
            "success": True,
            "data": alarms,
            "meta": {
                "total": len(alarms),
                "max_alarms": Config.MAX_ALARMS_PER_USER
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Liste hatası: {e}")
        return jsonify({
            "success": False,
            "message": f"Sunucu hatası: {str(e)}"
        }), 500

@alarm_bp.route('/delete', methods=['POST'])
@limiter.limit("30 per minute")
def delete_alarm():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "Request body boş"
            }), 400
        
        required = ['fcm_token', 'currency_code', 'alarm_type']
        for field in required:
            if field not in data:
                return jsonify({
                    "success": False,
                    "message": f"{field} gerekli"
                }), 400
        
        fcm_token = data['fcm_token'].strip()
        currency_code = data['currency_code'].strip().upper()
        alarm_type = data['alarm_type'].strip().upper()
        profile = data.get('profile', 'jeweler').strip().lower()
        
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        alarm_key = create_alarm_key(fcm_token, currency_code, alarm_type, profile)
        
        if not redis_client.exists(alarm_key):
            return jsonify({
                "success": False,
                "message": "Alarm bulunamadı"
            }), 404
        
        redis_client.delete(alarm_key)
        
        logger.info(f"🗑️ [ALARM] Silindi: {currency_code} ({alarm_type}, {profile})")
        
        return jsonify({
            "success": True,
            "message": "Alarm başarıyla silindi",
            "data": {
                "currency_code": currency_code,
                "alarm_type": alarm_type,
                "profile": profile
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Silme hatası: {e}")
        return jsonify({
            "success": False,
            "message": f"Sunucu hatası: {str(e)}"
        }), 500

@alarm_bp.route('/sync', methods=['POST'])
@limiter.limit("10 per minute")
def sync_alarms():
    try:
        data = request.get_json()
        
        if not data or 'fcm_token' not in data or 'alarms' not in data:
            return jsonify({
                "success": False,
                "message": "fcm_token ve alarms gerekli"
            }), 400
        
        fcm_token = data['fcm_token'].strip()
        alarms = data['alarms']
        
        import hashlib
        token_hash = hashlib.sha256(fcm_token.encode()).hexdigest()[:16]
        save_fcm_token_mapping(fcm_token, token_hash)
        
        if not isinstance(alarms, list):
            return jsonify({
                "success": False,
                "message": "alarms bir liste olmalı"
            }), 400
        
        if len(alarms) > Config.MAX_ALARMS_PER_USER:
            return jsonify({
                "success": False,
                "message": f"Maksimum {Config.MAX_ALARMS_PER_USER} alarm"
            }), 400
        
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        user_pattern = get_user_alarm_pattern(fcm_token)
        old_alarms = redis_client.keys(user_pattern)
        
        if old_alarms:
            for key in old_alarms:
                redis_client.delete(key)
            logger.info(f"🧹 [ALARM] {len(old_alarms)} eski alarm temizlendi")
        
        synced_count = 0
        failed_count = 0
        
        for alarm in alarms:
            try:
                alarm['fcm_token'] = fcm_token
                
                is_valid, error_msg = validate_alarm_data(alarm)
                if not is_valid:
                    logger.warning(f"⚠️ [SYNC] Geçersiz alarm: {error_msg}")
                    failed_count += 1
                    continue
                
                alarm_obj = parse_alarm_data(alarm)
                
                currency_code = alarm_obj['currency_code']
                alarm_type = alarm_obj['alarm_type']
                profile = alarm_obj['profile']
                
                alarm_key = create_alarm_key(fcm_token, currency_code, alarm_type, profile)
                
                redis_client.setex(
                    alarm_key,
                    Config.ALARM_TTL,
                    json.dumps(alarm_obj)
                )
                
                synced_count += 1
                
            except Exception as alarm_err:
                logger.error(f"❌ [SYNC] Alarm kayıt hatası: {alarm_err}")
                failed_count += 1
                continue
        
        logger.info(
            f"✅ [ALARM] Sync tamamlandı: "
            f"{synced_count} başarılı, {failed_count} başarısız"
        )
        
        return jsonify({
            "success": True,
            "message": "Alarmlar senkronize edildi",
            "data": {
                "synced": synced_count,
                "failed": failed_count,
                "total": len(alarms)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Sync hatası: {e}")
        return jsonify({
            "success": False,
            "message": f"Sunucu hatası: {str(e)}"
        }), 500

@alarm_bp.route('/delete-all', methods=['POST'])
@limiter.limit("10 per minute")
def delete_all_alarms():
    try:
        data = request.get_json()
        
        if not data or 'fcm_token' not in data:
            return jsonify({
                "success": False,
                "message": "fcm_token gerekli"
            }), 400
        
        fcm_token = data['fcm_token'].strip()
        
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        user_pattern = get_user_alarm_pattern(fcm_token)
        alarm_keys = redis_client.keys(user_pattern)
        
        deleted_count = 0
        
        for key in alarm_keys:
            try:
                redis_client.delete(key)
                deleted_count += 1
            except Exception as del_err:
                logger.warning(f"⚠️ [DELETE] Silme hatası: {del_err}")
                continue
        
        logger.info(f"🗑️ [ALARM] Toplu silme: {deleted_count} alarm")
        
        return jsonify({
            "success": True,
            "message": "Tüm alarmlar silindi",
            "data": {
                "deleted": deleted_count
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Toplu silme hatası: {e}")
        return jsonify({
            "success": False,
            "message": f"Sunucu hatası: {str(e)}"
        }), 500

@alarm_bp.route('/stats', methods=['GET'])
@limiter.limit("10 per minute")
def alarm_stats():
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        all_alarms = redis_client.keys("alarm:*")
        total_alarms = len(all_alarms)
        
        unique_users = set()
        high_count = 0
        low_count = 0
        raw_count = 0
        jeweler_count = 0
        
        for key in all_alarms:
            try:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                parts = key.split(':')
                if len(parts) >= 4:
                    user_hash = parts[1]
                    alarm_type = parts[3]
                    
                    unique_users.add(user_hash)
                    
                    if alarm_type == 'HIGH':
                        high_count += 1
                    elif alarm_type == 'LOW':
                        low_count += 1
                    
                    if len(parts) >= 5:
                        profile = parts[4]
                        if profile == 'raw':
                            raw_count += 1
                        elif profile == 'jeweler':
                            jeweler_count += 1
                        
            except Exception as parse_err:
                continue
        
        return jsonify({
            "success": True,
            "data": {
                "total_alarms": total_alarms,
                "unique_users": len(unique_users),
                "alarm_types": {
                    "HIGH": high_count,
                    "LOW": low_count
                },
                "profiles": {
                    "raw": raw_count,
                    "jeweler": jeweler_count
                },
                "max_per_user": Config.MAX_ALARMS_PER_USER,
                "ttl_days": Config.ALARM_TTL // (24 * 60 * 60)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Stats hatası: {e}")
        return jsonify({
            "success": False,
            "message": f"Sunucu hatası: {str(e)}"
        }), 500
