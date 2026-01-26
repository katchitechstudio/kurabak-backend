"""
Alarm Routes - PRODUCTION READY V1.0 🚀
==========================================================
✅ REDIS BASED: Hafif ve hızlı alarm storage
✅ FCM TOKEN BASED: Kullanıcı başına izole alarmlar
✅ AUTO SYNC: Android restart sonrası otomatik senkronizasyon
✅ TTL SUPPORT: 90 gün sonra otomatik temizlik
✅ DUPLICATE CHECK: Aynı döviz ve tip için tek alarm
✅ RATE LIMITING: Spam koruması
✅ VALIDATION: Fiyat ve format kontrolü
"""

from flask import Blueprint, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
import time
from datetime import datetime
import json

from config import Config
from utils.cache import get_cache, set_cache, get_redis_client

logger = logging.getLogger(__name__)

alarm_bp = Blueprint('alarm', __name__, url_prefix='/api/alarm')

# Rate Limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)

# ======================================
# CONSTANTS
# ======================================

ALARM_TTL = 90 * 24 * 60 * 60  # 90 gün (saniye cinsinden)
MAX_ALARMS_PER_USER = 50  # Kullanıcı başına maksimum alarm sayısı

# ======================================
# HELPER FUNCTIONS
# ======================================

def create_alarm_key(fcm_token: str, currency_code: str, alarm_type: str) -> str:
    """
    Redis alarm anahtarı oluştur
    
    Format: alarms:{fcm_token}:{currency_code}:{alarm_type}
    
    Args:
        fcm_token: Firebase Cloud Messaging token
        currency_code: Döviz kodu (USD, EUR, GRA vb.)
        alarm_type: HIGH veya LOW
        
    Returns:
        str: Redis key
    """
    # Token'ı hash'le (güvenlik + kısa anahtar)
    import hashlib
    token_hash = hashlib.sha256(fcm_token.encode()).hexdigest()[:16]
    
    return f"alarm:{token_hash}:{currency_code}:{alarm_type}"


def get_user_alarm_pattern(fcm_token: str) -> str:
    """
    Kullanıcının tüm alarmları için pattern
    
    Args:
        fcm_token: Firebase Cloud Messaging token
        
    Returns:
        str: Redis pattern (alarm:TOKEN_HASH:*)
    """
    import hashlib
    token_hash = hashlib.sha256(fcm_token.encode()).hexdigest()[:16]
    
    return f"alarm:{token_hash}:*"


def validate_alarm_data(data: dict) -> tuple:
    """
    Alarm verilerini doğrula
    
    Args:
        data: Request body
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    # Gerekli alanlar
    required_fields = ['fcm_token', 'currency_code', 'currency_name', 'target_price', 'alarm_type']
    
    for field in required_fields:
        if field not in data:
            return False, f"{field} eksik"
    
    # FCM Token validasyonu
    fcm_token = data['fcm_token'].strip()
    if len(fcm_token) < 100:
        return False, "Geçersiz FCM token"
    
    # Currency Code validasyonu
    currency_code = data['currency_code'].strip().upper()
    if not currency_code or len(currency_code) > 10:
        return False, "Geçersiz currency_code"
    
    # Target Price validasyonu
    try:
        target_price = float(data['target_price'])
        if target_price <= 0:
            return False, "Hedef fiyat 0'dan büyük olmalı"
    except (ValueError, TypeError):
        return False, "Geçersiz target_price formatı"
    
    # Start Price validasyonu (opsiyonel)
    if 'start_price' in data:
        try:
            start_price = float(data['start_price'])
            if start_price <= 0:
                return False, "Başlangıç fiyatı 0'dan büyük olmalı"
        except (ValueError, TypeError):
            return False, "Geçersiz start_price formatı"
    
    # Alarm Type validasyonu
    alarm_type = data['alarm_type'].strip().upper()
    if alarm_type not in ['HIGH', 'LOW']:
        return False, "alarm_type sadece HIGH veya LOW olabilir"
    
    return True, None


def parse_alarm_data(data: dict) -> dict:
    """
    Alarm verisini parse et ve Redis formatına dönüştür
    
    Args:
        data: Request body
        
    Returns:
        dict: Redis'e kaydedilecek alarm objesi
    """
    return {
        'currency_code': data['currency_code'].strip().upper(),
        'currency_name': data['currency_name'].strip(),
        'target_price': float(data['target_price']),
        'start_price': float(data.get('start_price', 0)),
        'alarm_type': data['alarm_type'].strip().upper(),
        'created_at': int(time.time()),
        'is_active': True
    }


# ======================================
# ALARM CRUD ENDPOINTS
# ======================================

@alarm_bp.route('/create', methods=['POST'])
@limiter.limit("20 per minute")  # Dakikada 20 alarm kurma
def create_alarm():
    """
    Yeni alarm oluştur
    
    Request Body:
    {
        "fcm_token": "FIREBASE_TOKEN",
        "currency_code": "USD",
        "currency_name": "Amerikan Doları",
        "target_price": 45.50,
        "start_price": 43.20,  // Opsiyonel
        "alarm_type": "HIGH"   // HIGH veya LOW
    }
    
    Response:
    {
        "success": true,
        "message": "Alarm başarıyla oluşturuldu",
        "data": {
            "alarm_id": "alarm:HASH:USD:HIGH",
            "currency_code": "USD",
            "target_price": 45.50,
            "alarm_type": "HIGH"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "Request body boş olamaz"
            }), 400
        
        # Validasyon
        is_valid, error_msg = validate_alarm_data(data)
        if not is_valid:
            return jsonify({
                "success": False,
                "message": error_msg
            }), 400
        
        fcm_token = data['fcm_token'].strip()
        currency_code = data['currency_code'].strip().upper()
        alarm_type = data['alarm_type'].strip().upper()
        
        # Redis client
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        # Kullanıcının toplam alarm sayısını kontrol et
        user_pattern = get_user_alarm_pattern(fcm_token)
        user_alarms = redis_client.keys(user_pattern)
        
        if len(user_alarms) >= MAX_ALARMS_PER_USER:
            return jsonify({
                "success": False,
                "message": f"Maksimum {MAX_ALARMS_PER_USER} alarm kurabilirsiniz"
            }), 400
        
        # Alarm anahtarı oluştur
        alarm_key = create_alarm_key(fcm_token, currency_code, alarm_type)
        
        # Duplicate kontrolü
        existing_alarm = redis_client.get(alarm_key)
        if existing_alarm:
            return jsonify({
                "success": False,
                "message": f"{currency_code} için {alarm_type} alarmı zaten var"
            }), 409  # Conflict
        
        # Alarm verisini hazırla
        alarm_obj = parse_alarm_data(data)
        
        # Redis'e kaydet (JSON string olarak)
        redis_client.setex(
            alarm_key,
            ALARM_TTL,
            json.dumps(alarm_obj)
        )
        
        logger.info(
            f"✅ [ALARM] Oluşturuldu: {currency_code} ({alarm_type}) "
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
    """
    Kullanıcının tüm alarmlarını listele
    
    Request Body:
    {
        "fcm_token": "FIREBASE_TOKEN"
    }
    
    Response:
    {
        "success": true,
        "data": [
            {
                "currency_code": "USD",
                "currency_name": "Amerikan Doları",
                "target_price": 45.50,
                "start_price": 43.20,
                "alarm_type": "HIGH",
                "created_at": 1234567890,
                "is_active": true
            }
        ],
        "meta": {
            "total": 5
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'fcm_token' not in data:
            return jsonify({
                "success": False,
                "message": "fcm_token gerekli"
            }), 400
        
        fcm_token = data['fcm_token'].strip()
        
        # Redis client
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        # Kullanıcının tüm alarmlarını çek
        user_pattern = get_user_alarm_pattern(fcm_token)
        alarm_keys = redis_client.keys(user_pattern)
        
        alarms = []
        
        for key in alarm_keys:
            try:
                # Bytes'tan string'e çevir
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                # Alarm verisini al
                alarm_data = redis_client.get(key)
                
                if alarm_data:
                    # JSON parse et
                    if isinstance(alarm_data, bytes):
                        alarm_data = alarm_data.decode('utf-8')
                    
                    alarm_obj = json.loads(alarm_data)
                    alarms.append(alarm_obj)
                    
            except Exception as parse_err:
                logger.warning(f"⚠️ [ALARM] Parse hatası ({key}): {parse_err}")
                continue
        
        # Created_at'a göre sırala (yeniden eskiye)
        alarms.sort(key=lambda x: x.get('created_at', 0), reverse=True)
        
        logger.info(f"📋 [ALARM] Liste çekildi: {len(alarms)} alarm")
        
        return jsonify({
            "success": True,
            "data": alarms,
            "meta": {
                "total": len(alarms),
                "max_alarms": MAX_ALARMS_PER_USER
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
    """
    Alarm sil
    
    Request Body:
    {
        "fcm_token": "FIREBASE_TOKEN",
        "currency_code": "USD",
        "alarm_type": "HIGH"
    }
    
    Response:
    {
        "success": true,
        "message": "Alarm silindi"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "Request body boş"
            }), 400
        
        # Gerekli alanlar
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
        
        # Redis client
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        # Alarm anahtarı
        alarm_key = create_alarm_key(fcm_token, currency_code, alarm_type)
        
        # Alarm var mı kontrol et
        if not redis_client.exists(alarm_key):
            return jsonify({
                "success": False,
                "message": "Alarm bulunamadı"
            }), 404
        
        # Sil
        redis_client.delete(alarm_key)
        
        logger.info(f"🗑️ [ALARM] Silindi: {currency_code} ({alarm_type})")
        
        return jsonify({
            "success": True,
            "message": "Alarm başarıyla silindi",
            "data": {
                "currency_code": currency_code,
                "alarm_type": alarm_type
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
    """
    Android'den tüm alarmları sync et (Restart sonrası)
    Mevcut alarmları temizleyip yeniden oluşturur
    
    Request Body:
    {
        "fcm_token": "FIREBASE_TOKEN",
        "alarms": [
            {
                "currency_code": "USD",
                "currency_name": "Amerikan Doları",
                "target_price": 45.50,
                "start_price": 43.20,
                "alarm_type": "HIGH"
            }
        ]
    }
    
    Response:
    {
        "success": true,
        "message": "Alarmlar senkronize edildi",
        "data": {
            "synced": 5,
            "failed": 0
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'fcm_token' not in data or 'alarms' not in data:
            return jsonify({
                "success": False,
                "message": "fcm_token ve alarms gerekli"
            }), 400
        
        fcm_token = data['fcm_token'].strip()
        alarms = data['alarms']
        
        if not isinstance(alarms, list):
            return jsonify({
                "success": False,
                "message": "alarms bir liste olmalı"
            }), 400
        
        # Maksimum alarm kontrolü
        if len(alarms) > MAX_ALARMS_PER_USER:
            return jsonify({
                "success": False,
                "message": f"Maksimum {MAX_ALARMS_PER_USER} alarm"
            }), 400
        
        # Redis client
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        # 1. Mevcut alarmları temizle
        user_pattern = get_user_alarm_pattern(fcm_token)
        old_alarms = redis_client.keys(user_pattern)
        
        if old_alarms:
            for key in old_alarms:
                redis_client.delete(key)
            logger.info(f"🧹 [ALARM] {len(old_alarms)} eski alarm temizlendi")
        
        # 2. Yeni alarmları kaydet
        synced_count = 0
        failed_count = 0
        
        for alarm in alarms:
            try:
                # Her bir alarm için gerekli alanları ekle
                alarm['fcm_token'] = fcm_token
                
                # Validasyon
                is_valid, error_msg = validate_alarm_data(alarm)
                if not is_valid:
                    logger.warning(f"⚠️ [SYNC] Geçersiz alarm: {error_msg}")
                    failed_count += 1
                    continue
                
                # Parse et
                alarm_obj = parse_alarm_data(alarm)
                
                currency_code = alarm_obj['currency_code']
                alarm_type = alarm_obj['alarm_type']
                
                # Alarm anahtarı
                alarm_key = create_alarm_key(fcm_token, currency_code, alarm_type)
                
                # Redis'e kaydet
                redis_client.setex(
                    alarm_key,
                    ALARM_TTL,
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
    """
    Kullanıcının tüm alarmlarını sil
    
    Request Body:
    {
        "fcm_token": "FIREBASE_TOKEN"
    }
    
    Response:
    {
        "success": true,
        "message": "Tüm alarmlar silindi",
        "data": {
            "deleted": 5
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'fcm_token' not in data:
            return jsonify({
                "success": False,
                "message": "fcm_token gerekli"
            }), 400
        
        fcm_token = data['fcm_token'].strip()
        
        # Redis client
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        # Kullanıcının tüm alarmlarını bul
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


# ======================================
# SYSTEM ENDPOINTS (Admin/Debug)
# ======================================

@alarm_bp.route('/stats', methods=['GET'])
@limiter.limit("10 per minute")
def alarm_stats():
    """
    Alarm sistemi istatistikleri (Admin için)
    
    Response:
    {
        "success": true,
        "data": {
            "total_alarms": 150,
            "unique_users": 50,
            "alarm_types": {
                "HIGH": 80,
                "LOW": 70
            }
        }
    }
    """
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return jsonify({
                "success": False,
                "message": "Redis bağlantısı yok"
            }), 500
        
        # Tüm alarmları say
        all_alarms = redis_client.keys("alarm:*")
        total_alarms = len(all_alarms)
        
        # Benzersiz kullanıcı sayısı (token hash'lerine göre)
        unique_users = set()
        high_count = 0
        low_count = 0
        
        for key in all_alarms:
            try:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                # alarm:HASH:CODE:TYPE formatından parse et
                parts = key.split(':')
                if len(parts) >= 4:
                    user_hash = parts[1]
                    alarm_type = parts[3]
                    
                    unique_users.add(user_hash)
                    
                    if alarm_type == 'HIGH':
                        high_count += 1
                    elif alarm_type == 'LOW':
                        low_count += 1
                        
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
                "max_per_user": MAX_ALARMS_PER_USER,
                "ttl_days": ALARM_TTL // (24 * 60 * 60)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ [ALARM] Stats hatası: {e}")
        return jsonify({
            "success": False,
            "message": f"Sunucu hatası: {str(e)}"
        }), 500
