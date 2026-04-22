"""
General Routes - API Endpoints V5.6
==================================================
✅ FCM Token Registration & Unregistration
✅ Feedback System
✅ Currency/Gold/Silver Data Endpoints
✅ Regional Currency Grouping
✅ Banner Management (Event System)
✅ Metrics & Monitoring
✅ 💰 PRICE PROFILE SUPPORT (Raw / Jeweler)
✅ 🚦 MARKET STATUS ENDPOINT
✅ 📬 TELEGRAM FEEDBACK
✅ 🔥 S15 FIX: Redis-backed tek Limiter instance
✅ 📱 V5.6: Device ID bazlı online tracking
   - online_user TTL: 600s (10 dakika aktif kullanıcı)
   - daily_user TTL: 43200s (12 saatlik unique cihaz)
   - IP fallback yerine device_id öncelikli
"""
from flask import Blueprint, jsonify, request, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
import time
import pytz
from datetime import datetime, timedelta

from config import Config
from utils.cache import get_cache, set_cache, incr_cache
from utils.notification_service import (
    register_fcm_token,
    unregister_fcm_token,
    get_token_count
)
from utils.event_manager import get_todays_banner
from services.financial_service import get_cache_key_for_profile

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

# ======================================
# 🔥 S15 FIX: Redis-backed paylaşımlı Limiter
# ======================================

def get_real_ip():
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        ips = [ip.strip() for ip in forwarded_for.split(',')]
        return ips[0]
    return request.remote_addr or '0.0.0.0'


def _get_limiter_storage() -> str:
    redis_url = Config.REDIS_URL
    if redis_url:
        return redis_url
    logger.warning(
        "⚠️ [RATE LIMIT] Redis yok! Rate limiter her Gunicorn worker'ında "
        "bağımsız çalışıyor. DDoS koruması zayıf!"
    )
    return "memory://"


limiter = Limiter(
    key_func=get_real_ip,
    default_limits=["200 per hour"],
    storage_uri=_get_limiter_storage(),
    strategy="fixed-window"
)

# ======================================


def track_online_user():
    """
    Device ID bazlı online tracking.
    - online_user:  TTL 600s  → son 10 dakikada aktif cihazlar
    - daily_user:   TTL 43200s → son 12 saatte unique cihazlar
    Öncelik: X-Device-Id header → X-Client-Id header → IP (son çare)
    """
    try:
        device_id = request.headers.get('X-Device-Id', '').strip()
        client_id = request.headers.get('X-Client-Id', '').strip()

        # Öncelik sırası: device_id > client_id > IP
        if device_id and device_id != 'unknown':
            unique_key = device_id
        elif client_id and client_id != 'unknown':
            unique_key = client_id
        else:
            unique_key = get_real_ip()

        # Aktif kullanıcı (son 10 dakika)
        set_cache(f"online_user:{unique_key}", "1", ttl=600)

        # 12 saatlik unique cihaz
        set_cache(f"daily_user:{unique_key}", "1", ttl=43200)

        # İstek sayacı (günlük)
        incr_cache(f"api_request:{unique_key}", ttl=86400)

    except Exception as e:
        logger.debug(f"Online tracking hatası (önemsiz): {e}")


def create_response(data, status_code=200, message=None, meta=None):
    response = {
        'success': status_code < 400,
        'data': data,
        'meta': meta or {},
        'timestamp': datetime.now().isoformat()
    }
    if message:
        response['message'] = message
    return jsonify(response), status_code


def get_data_guaranteed(cache_key):
    data = get_cache(cache_key)
    if data:
        return data

    stale_key  = f"{cache_key}:stale"
    stale_data = get_cache(stale_key)

    if stale_data:
        logger.warning(f"⚠️ {cache_key} için güncel veri yok, BAYAT veri sunuluyor.")
        return stale_data

    logger.error(
        f"🔴 KRİTİK: {cache_key} verisi yok! "
        f"Scheduler kontrol edilmeli. 503 dönülüyor."
    )
    return None


def check_user_agent():
    user_agent        = request.headers.get('User-Agent', 'Unknown')
    suspicious_agents = ['curl', 'wget', 'python-requests', 'scrapy']
    if any(bot in user_agent.lower() for bot in suspicious_agents):
        logger.warning(f"⚠️ Şüpheli User-Agent: {user_agent} | IP: {request.remote_addr}")
    return True


def get_smart_banner():
    manual_banner = get_cache("system_banner")
    if manual_banner:
        logger.debug("📢 [BANNER] Manual banner bulundu (Priority: 100)")
        return manual_banner
    try:
        event_banner = get_todays_banner()
        if event_banner:
            logger.debug(f"🤖 [BANNER] Event banner bulundu: {event_banner[:50]}...")
            return event_banner
    except Exception as e:
        logger.warning(f"⚠️ [BANNER] Event Manager hatası (önemsiz): {e}")
    return None


# ======================================
# ENDPOINTS
# ======================================

@api_bp.route('/currency/all', methods=['GET'])
@limiter.limit("60 per minute")
def get_all_currencies():
    check_user_agent()
    track_online_user()

    try:
        profile = request.args.get('profile', Config.DEFAULT_PRICE_PROFILE).lower()
        if profile not in ["raw", "jeweler"]:
            logger.warning(f"⚠️ Geçersiz profil: {profile}, jeweler kullanılıyor")
            profile = "jeweler"

        cache_key = get_cache_key_for_profile('currencies_all', profile)
        result    = get_data_guaranteed(cache_key)

        if not result:
            return create_response(
                [],
                503,
                "Veriler hazırlanıyor, lütfen 1-2 dakika sonra tekrar deneyin."
            )

        data_list  = result.get('data', [])
        update_date = result.get('update_date')
        status      = result.get('status', 'OPEN')
        market_msg  = result.get('market_msg')
        banner_msg  = get_smart_banner()

        if not banner_msg:
            if status in ['MAINTENANCE', 'MAINTENANCE_FULL']:
                banner_msg = market_msg or "🚧 Sistem şu an bakımda. Lütfen daha sonra tekrar deneyin."
            elif status == 'CLOSED':
                banner_msg = market_msg or "🌙 Piyasalar kapalı, iyi hafta sonları!"

        return create_response(
            data_list,
            200,
            f"Döviz kurları getirildi ({profile})",
            {
                'count':       len(data_list),
                'profile':     profile,
                'last_update': update_date,
                'source':      result.get('source'),
                'status':      status,
                'market_msg':  market_msg,
                'banner':      banner_msg,
            }
        )
    except Exception as e:
        logger.error(f"Currency All Error: {e}")
        return create_response([], 500, "Sunucu hatası")


@api_bp.route('/currency/gold/all', methods=['GET'])
@limiter.limit("60 per minute")
def get_all_golds():
    check_user_agent()
    track_online_user()

    try:
        profile = request.args.get('profile', Config.DEFAULT_PRICE_PROFILE).lower()
        if profile not in ["raw", "jeweler"]:
            profile = "jeweler"

        cache_key = get_cache_key_for_profile('golds_all', profile)
        result    = get_data_guaranteed(cache_key)

        if not result:
            return create_response(
                [],
                503,
                "Veriler hazırlanıyor, lütfen 1-2 dakika sonra tekrar deneyin."
            )

        data_list = result.get('data', [])
        return create_response(
            data_list,
            200,
            f"Altın fiyatları getirildi ({profile})",
            {
                'count':       len(data_list),
                'profile':     profile,
                'last_update': result.get('update_date'),
                'status':      result.get('status', 'OPEN'),
            }
        )
    except Exception as e:
        logger.error(f"Gold All Error: {e}")
        return create_response([], 500, "Sunucu hatası")


@api_bp.route('/currency/silver/all', methods=['GET'])
@limiter.limit("60 per minute")
def get_all_silvers():
    check_user_agent()
    track_online_user()

    try:
        profile = request.args.get('profile', Config.DEFAULT_PRICE_PROFILE).lower()
        if profile not in ["raw", "jeweler"]:
            profile = "jeweler"

        cache_key = get_cache_key_for_profile('silvers_all', profile)
        result    = get_data_guaranteed(cache_key)

        if not result:
            return create_response(
                [],
                503,
                "Veriler hazırlanıyor, lütfen 1-2 dakika sonra tekrar deneyin."
            )

        data_list = result.get('data', [])
        return create_response(
            data_list,
            200,
            f"Gümüş fiyatları getirildi ({profile})",
            {
                'count':       len(data_list),
                'profile':     profile,
                'last_update': result.get('update_date'),
                'status':      result.get('status', 'OPEN'),
            }
        )
    except Exception as e:
        logger.error(f"Silver All Error: {e}")
        return create_response([], 500, "Sunucu hatası")


@api_bp.route('/currency/regional', methods=['GET'])
@limiter.limit("30 per minute")
def get_regional_currencies():
    check_user_agent()
    track_online_user()

    try:
        cache_key = get_cache_key_for_profile('currencies_all', 'jeweler')
        result    = get_data_guaranteed(cache_key)

        if not result:
            return create_response(
                {},
                503,
                "Veriler hazırlanıyor, lütfen 1-2 dakika sonra tekrar deneyin."
            )

        all_currencies = result.get('data', [])
        regional_data  = {}
        regions        = Config.REGIONAL_CURRENCIES
        curr_map       = {item['code']: item for item in all_currencies}

        for region_name, codes in regions.items():
            regional_data[region_name] = []
            for code in codes:
                if code in curr_map:
                    regional_data[region_name].append(curr_map[code])

        return create_response(
            regional_data,
            200,
            "Bölgesel veriler getirildi",
            {'regions': list(regions.keys())}
        )
    except Exception as e:
        logger.error(f"Regional Error: {e}")
        return create_response({}, 500, "Sunucu hatası")


@api_bp.route('/market/status', methods=['GET'])
@limiter.limit("120 per minute")
def get_market_status():
    check_user_agent()
    track_online_user()

    try:
        tz  = pytz.timezone(Config.DEFAULT_TIMEZONE)
        now = datetime.now(tz)

        meta = {
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timezone":     Config.DEFAULT_TIMEZONE,
        }

        # 1. Bakım modu
        maintenance_data = get_cache("system_maintenance")
        if maintenance_data and isinstance(maintenance_data, dict):
            end_time = maintenance_data.get("end_time")
            if end_time and time.time() <= end_time:
                message = maintenance_data.get("message", "Sistem Bakımda")
                mode    = maintenance_data.get("mode", "limited")
                status  = "MAINTENANCE_FULL" if mode == "full" else "MAINTENANCE"
                return create_response(
                    {"status": status, "color": "yellow", "message": message, "next_open": None},
                    200, "Market durumu (Bakım)", meta
                )

        # 2. Hafta sonu
        is_saturday      = now.weekday() == 5
        is_friday_closed = now.weekday() == 4 and now.hour >= Config.MARKET_CLOSE_FRIDAY_HOUR
        is_sunday        = now.weekday() == 6

        if is_saturday or is_friday_closed or is_sunday:
            if is_friday_closed:
                days_until_monday = (7 - now.weekday()) % 7
                next_open = (now + timedelta(days=days_until_monday)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            elif is_saturday:
                next_open = (now + timedelta(days=2)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            else:
                next_open = (now + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

            return create_response(
                {
                    "status":    "CLOSED",
                    "color":     "red",
                    "message":   "Piyasalar Kapalı",
                    "next_open": next_open.strftime("%Y-%m-%d %H:%M:%S"),
                },
                200, "Market durumu (Kapalı)", meta
            )

        # 3. Açık
        return create_response(
            {"status": "OPEN", "color": "green", "message": "Piyasalar Açık", "next_open": None},
            200, "Market durumu (Açık)", meta
        )

    except Exception as e:
        logger.error(f"❌ [MARKET STATUS] Hata: {e}")
        return create_response(
            {"status": "OPEN", "color": "green", "message": "Piyasalar Açık", "next_open": None},
            200, "Market durumu (Varsayılan)",
            {
                "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "timezone":     Config.DEFAULT_TIMEZONE,
                "error":        str(e),
            }
        )


@api_bp.route('/banner/today', methods=['GET'])
@limiter.limit("120 per minute")
def get_todays_event_banner():
    check_user_agent()
    track_online_user()

    try:
        from utils.event_manager import get_todays_events
        events = get_todays_events()

        if events:
            top_event = events[0]
            return create_response(
                {"banner": top_event['message'], "event_type": top_event['type']},
                200,
                "Bugünün banner'ı getirildi",
                {
                    'banner_type': top_event['type'],
                    'priority':    top_event['priority'],
                    'valid_until': top_event['valid_until'],
                    'has_events':  True,
                    'total_events': len(events),
                }
            )
        else:
            return create_response(
                {"banner": None, "event_type": None},
                200,
                "Bugün özel bir banner yok",
                {'banner_type': None, 'priority': 0, 'has_events': False}
            )
    except Exception as e:
        logger.error(f"Event Banner Error: {e}")
        return create_response({"banner": None}, 500, "Banner alınırken hata oluştu")


@api_bp.route('/fcm/register', methods=['POST'])
@limiter.limit("10 per minute")
def register_fcm_token_endpoint():
    try:
        data = request.get_json()
        if not data or 'token' not in data:
            return create_response(None, 400, "Token gerekli! Body: {\"token\": \"FCM_TOKEN\"}")

        token = data['token'].strip()
        if len(token) < 100:
            return create_response(None, 400, "Geçersiz token formatı")

        success = register_fcm_token(token)
        if success:
            logger.info(f"✅ [FCM] Yeni token kaydedildi: {token[:20]}...")
            return create_response({"token": token[:20] + "..."}, 200, "Token başarıyla kaydedildi")
        else:
            return create_response(None, 500, "Token kaydedilemedi")
    except Exception as e:
        logger.error(f"❌ [FCM] Token kayıt hatası: {e}")
        return create_response(None, 500, f"Sunucu hatası: {str(e)}")


@api_bp.route('/fcm/unregister', methods=['POST'])
@limiter.limit("10 per minute")
def unregister_fcm_token_endpoint():
    try:
        data = request.get_json()
        if not data or 'token' not in data:
            return create_response(None, 400, "Token gerekli! Body: {\"token\": \"FCM_TOKEN\"}")

        token   = data['token'].strip()
        success = unregister_fcm_token(token)

        if success:
            logger.info(f"🗑️ [FCM] Token silindi: {token[:20]}...")
            return create_response({"token": token[:20] + "..."}, 200, "Token başarıyla silindi")
        else:
            return create_response(None, 404, "Token bulunamadı")
    except Exception as e:
        logger.error(f"❌ [FCM] Token silme hatası: {e}")
        return create_response(None, 500, f"Sunucu hatası: {str(e)}")


@api_bp.route('/fcm/status', methods=['GET'])
@limiter.limit("30 per minute")
def fcm_status():
    try:
        token_count       = get_token_count()
        last_notification = get_cache(Config.CACHE_KEYS['fcm_last_notification'])
        if last_notification:
            last_notification = datetime.fromtimestamp(float(last_notification)).isoformat()

        return create_response(
            {
                "total_tokens":           token_count,
                "last_notification":      last_notification,
                "notification_enabled":   Config.FIREBASE_NOTIFICATION_ENABLED,
            },
            200, "FCM durumu"
        )
    except Exception as e:
        logger.error(f"❌ [FCM] Durum sorgulama hatası: {e}")
        return create_response(None, 500, f"Sunucu hatası: {str(e)}")


@api_bp.route('/feedback/send', methods=['POST'])
@limiter.limit("5 per hour")
def send_feedback():
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return create_response(None, 400, "Mesaj gerekli!")

        user_message = data['message'].strip()
        if not user_message:
            return create_response(None, 400, "Mesaj boş olamaz")
        if len(user_message) < 5:
            return create_response(None, 400, "Mesaj en az 5 karakter olmalı")
        if len(user_message) > 500:
            return create_response(None, 400, "Mesaj en fazla 500 karakter olabilir")

        user_id    = request.headers.get('X-Client-Id', 'Bilinmiyor')
        device_id  = request.headers.get('X-Device-Id', 'Bilinmiyor')
        ip_address = get_real_ip()
        user_agent = request.headers.get('User-Agent', 'Bilinmiyor')

        from utils.telegram_monitor import init_telegram_monitor
        telegram_bot = init_telegram_monitor()

        if telegram_bot:
            feedback_text = (
                f"📬 *YENİ KULLANICI GERİ BİLDİRİMİ*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💬 *Mesaj:*\n{user_message}\n\n"
                f"👤 *Kullanıcı Bilgileri:*\n"
                f"• User ID: `{user_id[:20]}`\n"
                f"• Device ID: `{device_id[:20]}`\n"
                f"• IP: `{ip_address}`\n"
                f"• Platform: `{user_agent[:50]}`\n\n"
                f"⏰ *Zaman:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            )
            telegram_bot.send_message(feedback_text, level='report')

        return create_response({"sent": True}, 200, "Geri bildiriminiz alındı, teşekkürler! 🙏")

    except Exception as e:
        logger.error(f"❌ [Feedback] Beklenmeyen hata: {e}")
        return create_response({"sent": False}, 200, "Geri bildiriminiz alındı, teşekkürler! 🙏")


@api_bp.route('/metrics', methods=['GET'])
@limiter.limit("10 per minute")
def get_metrics():
    try:
        from services.financial_service import get_service_metrics
        from services.maintenance_service import get_scheduler_status

        metrics   = get_service_metrics()
        scheduler = get_scheduler_status()

        return create_response(
            {
                'api_metrics':      metrics,
                'scheduler_status': scheduler,
                'environment':      Config.ENVIRONMENT,
            },
            200
        )
    except Exception as e:
        return create_response(None, 500, str(e))


@api_bp.errorhandler(429)
def ratelimit_handler(e):
    logger.warning(f"⚠️ Rate limit aşıldı: IP={get_real_ip()}")
    return create_response(
        [],
        429,
        "Çok fazla istek gönderiyorsunuz. Lütfen biraz bekleyin.",
        {'retry_after': '60 saniye'}
    )


# ======================================
# ONLINE TRACKING HELPERS (Telegram'dan çağrılır)
# ======================================

def get_online_stats() -> dict:
    """
    Telegram /online komutu için aktif + günlük unique kullanıcı sayısını döner.
    """
    try:
        from utils.cache import get_cache_keys

        # Son 10 dakika aktif
        online_keys  = get_cache_keys("online_user:*")
        active_count = len(online_keys)

        # Son 12 saat unique cihaz
        daily_keys   = get_cache_keys("daily_user:*")
        daily_count  = len(daily_keys)

        # IP fallback olanları ayıkla (device ID'ler genelde 16 hex karakteri)
        device_based = [k for k in daily_keys if not _looks_like_ip(k.replace("daily_user:", ""))]
        ip_based     = daily_count - len(device_based)

        return {
            "active_10min": active_count,
            "unique_12h":   daily_count,
            "device_based": len(device_based),
            "ip_based":     ip_based,
        }
    except Exception as e:
        logger.error(f"get_online_stats hatası: {e}")
        return {"active_10min": 0, "unique_12h": 0, "device_based": 0, "ip_based": 0}


def _looks_like_ip(key: str) -> bool:
    import re
    return bool(re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', key))
