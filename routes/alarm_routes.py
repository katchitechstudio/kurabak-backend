from flask import Blueprint, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
import time
import json
import hashlib

from config import Config
from utils.cache import get_cache, set_cache, get_redis_client
from services.alarm_service import save_fcm_token_mapping, get_all_alarm_keys_safe

logger = logging.getLogger(__name__)

alarm_bp = Blueprint('alarm', __name__, url_prefix='/api/alarm')

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"],
    storage_uri=Config.REDIS_URL or "memory://",
    strategy="fixed-window"
)


# ─── Yardımcı fonksiyonlar ────────────────────────────────────────────────────

def _token_hash(fcm_token: str) -> str:
    return hashlib.sha256(fcm_token.encode()).hexdigest()[:16]

def create_alarm_key(fcm_token: str, currency_code: str, alarm_type: str, profile: str) -> str:
    return f"alarm:{_token_hash(fcm_token)}:{currency_code}:{alarm_type}:{profile}"

def get_user_alarm_pattern(fcm_token: str) -> str:
    return f"alarm:{_token_hash(fcm_token)}:*"

def scan_keys(redis_client, pattern: str) -> list:
    """redis.keys() yerine SCAN kullan — production'da güvenli."""
    keys = []
    cursor = 0
    while True:
        cursor, batch = redis_client.scan(cursor, match=pattern, count=100)
        keys.extend(batch)
        if cursor == 0:
            break
    return keys


def validate_alarm_data(data: dict) -> tuple:
    required_fields = ['fcm_token', 'currency_code', 'currency_name', 'target_price', 'alarm_type']
    for field in required_fields:
        if field not in data:
            return False, f"{field} eksik"

    if len(data['fcm_token'].strip()) < 100:
        return False, "Geçersiz FCM token"

    currency_code = data['currency_code'].strip().upper()
    if not currency_code or len(currency_code) > 10:
        return False, "Geçersiz currency_code"

    try:
        if float(data['target_price']) <= 0:
            return False, "Hedef fiyat 0'dan büyük olmalı"
    except (ValueError, TypeError):
        return False, "Geçersiz target_price formatı"

    if data['alarm_type'].strip().upper() not in ['HIGH', 'LOW']:
        return False, "alarm_type sadece HIGH veya LOW olabilir"

    alarm_mode = data.get('alarm_mode', 'PRICE').strip().upper()
    if alarm_mode not in ['PRICE', 'PERCENT']:
        return False, "alarm_mode sadece PRICE veya PERCENT olabilir"

    profile = data.get('profile', 'jeweler').strip().lower()
    if profile not in ['raw', 'jeweler']:
        return False, "profile sadece raw veya jeweler olabilir"

    # ─── start_price kontrolü ────────────────────────────────────────────────
    # PERCENT modunda start_price ZORUNLU — olmadan alarm hiç tetiklenemez.
    # PRICE modunda isteğe bağlı, gönderilmişse geçerli olmalı.
    if alarm_mode == 'PERCENT':
        if 'start_price' not in data:
            return False, "PERCENT modunda start_price zorunludur"
        try:
            if float(data['start_price']) <= 0:
                return False, "Başlangıç fiyatı 0'dan büyük olmalı"
        except (ValueError, TypeError):
            return False, "Geçersiz start_price formatı"
    else:
        # PRICE modu — start_price opsiyonel ama gönderildiyse geçerli olmalı
        if 'start_price' in data:
            try:
                if float(data['start_price']) <= 0:
                    return False, "Başlangıç fiyatı 0'dan büyük olmalı"
            except (ValueError, TypeError):
                return False, "Geçersiz start_price formatı"

    # ─── PERCENT modu ek alanlar ─────────────────────────────────────────────
    if alarm_mode == 'PERCENT':
        if 'percent_value' not in data:
            return False, "percent_value gerekli"
        try:
            pv = float(data['percent_value'])
            if pv <= 0 or pv > 100:
                return False, "percent_value 0-100 arasında olmalı"
        except (ValueError, TypeError):
            return False, "Geçersiz percent_value formatı"

        if data.get('percent_direction', '').strip().upper() not in ['UP', 'DOWN']:
            return False, "percent_direction sadece UP veya DOWN olabilir"

    return True, None


def parse_alarm_data(data: dict) -> dict:
    alarm_mode = data.get('alarm_mode', 'PRICE').strip().upper()
    obj = {
        'currency_code':     data['currency_code'].strip().upper(),
        'currency_name':     data['currency_name'].strip(),
        'target_price':      float(data['target_price']),
        'start_price':       float(data.get('start_price', 0)),
        'alarm_type':        data['alarm_type'].strip().upper(),
        'alarm_mode':        alarm_mode,
        'profile':           data.get('profile', 'jeweler').strip().lower(),
        'created_at':        int(time.time()),
        'is_active':         True,
        'percent_value':     float(data['percent_value'])             if alarm_mode == 'PERCENT' else None,
        'percent_direction': data['percent_direction'].strip().upper() if alarm_mode == 'PERCENT' else None,
    }
    return obj


def _no_redis():
    return jsonify({"success": False, "message": "Redis bağlantısı yok"}), 500


# ─── Endpointler ──────────────────────────────────────────────────────────────

@alarm_bp.route('/create', methods=['POST'])
@limiter.limit("20 per minute")
def create_alarm():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "Request body boş olamaz"}), 400

        is_valid, error_msg = validate_alarm_data(data)
        if not is_valid:
            return jsonify({"success": False, "message": error_msg}), 400

        fcm_token     = data['fcm_token'].strip()
        currency_code = data['currency_code'].strip().upper()
        alarm_type    = data['alarm_type'].strip().upper()
        profile       = data.get('profile', 'jeweler').strip().lower()

        redis_client = get_redis_client()
        if not redis_client:
            return _no_redis()

        user_alarms = scan_keys(redis_client, get_user_alarm_pattern(fcm_token))
        if len(user_alarms) >= Config.MAX_ALARMS_PER_USER:
            return jsonify({
                "success": False,
                "message": f"Maksimum {Config.MAX_ALARMS_PER_USER} alarm kurabilirsiniz"
            }), 400

        alarm_key = create_alarm_key(fcm_token, currency_code, alarm_type, profile)
        save_fcm_token_mapping(fcm_token, _token_hash(fcm_token))

        if redis_client.exists(alarm_key):
            alarm_type_tr = "yükseliş" if alarm_type == "HIGH" else "düşüş"
            profile_tr    = "ham" if profile == "raw" else "kuyumcu"
            return jsonify({
                "success": False,
                "message": f"Bu varlık için {profile_tr} fiyatında zaten bir {alarm_type_tr} alarmınız var"
            }), 409

        alarm_obj = parse_alarm_data(data)
        redis_client.setex(alarm_key, Config.ALARM_TTL, json.dumps(alarm_obj))

        logger.info(
            f"✅ [ALARM] Oluşturuldu: {currency_code} ({alarm_type}, "
            f"{alarm_obj['alarm_mode']}, {profile}) → Hedef: {alarm_obj['target_price']}"
        )

        return jsonify({
            "success": True,
            "message": "Alarm başarıyla oluşturuldu",
            "data": {
                "alarm_id":          alarm_key,
                "currency_code":     currency_code,
                "currency_name":     alarm_obj['currency_name'],
                "target_price":      alarm_obj['target_price'],
                "start_price":       alarm_obj['start_price'],
                "alarm_type":        alarm_type,
                "alarm_mode":        alarm_obj['alarm_mode'],
                "profile":           alarm_obj['profile'],
                "percent_value":     alarm_obj.get('percent_value'),
                "percent_direction": alarm_obj.get('percent_direction'),
                "created_at":        alarm_obj['created_at']
            }
        }), 201

    except Exception as e:
        logger.error(f"❌ [ALARM] Oluşturma hatası: {e}")
        return jsonify({"success": False, "message": f"Sunucu hatası: {str(e)}"}), 500


@alarm_bp.route('/list', methods=['POST'])
@limiter.limit("30 per minute")
def list_alarms():
    try:
        data = request.get_json()
        if not data or 'fcm_token' not in data:
            return jsonify({"success": False, "message": "fcm_token gerekli"}), 400

        redis_client = get_redis_client()
        if not redis_client:
            return _no_redis()

        alarm_keys = scan_keys(redis_client, get_user_alarm_pattern(data['fcm_token'].strip()))
        alarms = []

        for key in alarm_keys:
            try:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                raw = redis_client.get(key)
                if raw:
                    if isinstance(raw, bytes):
                        raw = raw.decode('utf-8')
                    alarms.append(json.loads(raw))
            except Exception as e:
                logger.warning(f"⚠️ [ALARM] Parse hatası ({key}): {e}")

        alarms.sort(key=lambda x: x.get('created_at', 0), reverse=True)
        logger.info(f"📋 [ALARM] Liste çekildi: {len(alarms)} alarm")

        return jsonify({
            "success": True,
            "data": alarms,
            "meta": {"total": len(alarms), "max_alarms": Config.MAX_ALARMS_PER_USER}
        }), 200

    except Exception as e:
        logger.error(f"❌ [ALARM] Liste hatası: {e}")
        return jsonify({"success": False, "message": f"Sunucu hatası: {str(e)}"}), 500


@alarm_bp.route('/delete', methods=['POST'])
@limiter.limit("30 per minute")
def delete_alarm():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "Request body boş"}), 400

        for field in ['fcm_token', 'currency_code', 'alarm_type']:
            if field not in data:
                return jsonify({"success": False, "message": f"{field} gerekli"}), 400

        fcm_token     = data['fcm_token'].strip()
        currency_code = data['currency_code'].strip().upper()
        alarm_type    = data['alarm_type'].strip().upper()
        profile       = data.get('profile', 'jeweler').strip().lower()

        redis_client = get_redis_client()
        if not redis_client:
            return _no_redis()

        alarm_key = create_alarm_key(fcm_token, currency_code, alarm_type, profile)
        if not redis_client.exists(alarm_key):
            return jsonify({"success": False, "message": "Alarm bulunamadı"}), 404

        redis_client.delete(alarm_key)
        logger.info(f"🗑️ [ALARM] Silindi: {currency_code} ({alarm_type}, {profile})")

        return jsonify({
            "success": True,
            "message": "Alarm başarıyla silindi",
            "data": {"currency_code": currency_code, "alarm_type": alarm_type, "profile": profile}
        }), 200

    except Exception as e:
        logger.error(f"❌ [ALARM] Silme hatası: {e}")
        return jsonify({"success": False, "message": f"Sunucu hatası: {str(e)}"}), 500


@alarm_bp.route('/sync', methods=['POST'])
@limiter.limit("10 per minute")
def sync_alarms():
    try:
        data = request.get_json()
        if not data or 'fcm_token' not in data or 'alarms' not in data:
            return jsonify({"success": False, "message": "fcm_token ve alarms gerekli"}), 400

        fcm_token = data['fcm_token'].strip()
        alarms    = data['alarms']

        if not isinstance(alarms, list):
            return jsonify({"success": False, "message": "alarms bir liste olmalı"}), 400
        if len(alarms) > Config.MAX_ALARMS_PER_USER:
            return jsonify({"success": False, "message": f"Maksimum {Config.MAX_ALARMS_PER_USER} alarm"}), 400

        redis_client = get_redis_client()
        if not redis_client:
            return _no_redis()

        save_fcm_token_mapping(fcm_token, _token_hash(fcm_token))

        old_keys = scan_keys(redis_client, get_user_alarm_pattern(fcm_token))
        if old_keys:
            redis_client.delete(*old_keys)
            logger.info(f"🧹 [ALARM] {len(old_keys)} eski alarm temizlendi")

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
                alarm_key = create_alarm_key(
                    fcm_token,
                    alarm_obj['currency_code'],
                    alarm_obj['alarm_type'],
                    alarm_obj['profile']
                )
                redis_client.setex(alarm_key, Config.ALARM_TTL, json.dumps(alarm_obj))
                synced_count += 1

            except Exception as e:
                logger.error(f"❌ [SYNC] Alarm kayıt hatası: {e}")
                failed_count += 1

        logger.info(f"✅ [ALARM] Sync: {synced_count} başarılı, {failed_count} başarısız")

        return jsonify({
            "success": True,
            "message": "Alarmlar senkronize edildi",
            "data": {"synced": synced_count, "failed": failed_count, "total": len(alarms)}
        }), 200

    except Exception as e:
        logger.error(f"❌ [ALARM] Sync hatası: {e}")
        return jsonify({"success": False, "message": f"Sunucu hatası: {str(e)}"}), 500


@alarm_bp.route('/delete-all', methods=['POST'])
@limiter.limit("10 per minute")
def delete_all_alarms():
    try:
        data = request.get_json()
        if not data or 'fcm_token' not in data:
            return jsonify({"success": False, "message": "fcm_token gerekli"}), 400

        redis_client = get_redis_client()
        if not redis_client:
            return _no_redis()

        keys = scan_keys(redis_client, get_user_alarm_pattern(data['fcm_token'].strip()))
        deleted_count = 0

        if keys:
            deleted_count = redis_client.delete(*keys)

        logger.info(f"🗑️ [ALARM] Toplu silme: {deleted_count} alarm")

        return jsonify({
            "success": True,
            "message": "Tüm alarmlar silindi",
            "data": {"deleted": deleted_count}
        }), 200

    except Exception as e:
        logger.error(f"❌ [ALARM] Toplu silme hatası: {e}")
        return jsonify({"success": False, "message": f"Sunucu hatası: {str(e)}"}), 500


@alarm_bp.route('/stats', methods=['GET'])
@limiter.limit("10 per minute")
def alarm_stats():
    """
    🔥 DÜZELTİLDİ: Ham scan_keys yerine get_all_alarm_keys_safe kullanılıyor.
    fcm_token_map ve price:last_check keyleri istatistiğe dahil edilmiyor.
    """
    try:
        redis_client = get_redis_client()
        if not redis_client:
            return _no_redis()

        all_keys = get_all_alarm_keys_safe(redis_client)

        unique_users  = set()
        high_count    = 0
        low_count     = 0
        raw_count     = 0
        jeweler_count = 0

        for key in all_keys:
            try:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                parts = key.split(':')
                if len(parts) >= 4:
                    unique_users.add(parts[1])
                    if parts[3] == 'HIGH':
                        high_count += 1
                    elif parts[3] == 'LOW':
                        low_count += 1
                if len(parts) >= 5:
                    if parts[4] == 'raw':
                        raw_count += 1
                    elif parts[4] == 'jeweler':
                        jeweler_count += 1
            except Exception:
                continue

        return jsonify({
            "success": True,
            "data": {
                "total_alarms": len(all_keys),
                "unique_users": len(unique_users),
                "alarm_types":  {"HIGH": high_count, "LOW": low_count},
                "profiles":     {"raw": raw_count, "jeweler": jeweler_count},
                "max_per_user": Config.MAX_ALARMS_PER_USER,
                "ttl_days":     Config.ALARM_TTL // (24 * 60 * 60)
            }
        }), 200

    except Exception as e:
        logger.error(f"❌ [ALARM] Stats hatası: {e}")
        return jsonify({"success": False, "message": f"Sunucu hatası: {str(e)}"}), 500
