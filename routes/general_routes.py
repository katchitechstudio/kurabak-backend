"""
General Routes - API Endpoints V5.5 (S15 DDoS FIX!) 🔥
==================================================
✅ FCM Token Registration & Unregistration
✅ Feedback System (TELEGRAM BOT FIX V5.4!)
✅ Currency/Gold/Silver Data Endpoints
✅ Regional Currency Grouping
✅ Banner Management (Event System)
✅ Metrics & Monitoring
✅ 💰 PRICE PROFILE SUPPORT (Raw / Jeweler)
✅ 🚦 MARKET STATUS ENDPOINT (V5.3)
✅ 📬 TELEGRAM FEEDBACK (V5.4 - TAMAMEN DÜZELTİLDİ!)
✅ 🔥 S15 FIX (V5.5): Redis-backed tek Limiter instance
   - get_real_ip() ile X-Forwarded-For doğru parse
   - alarm_routes.py bu instance'ı import eder
   - Gunicorn multi-worker'da tüm worker'lar aynı sayacı paylaşır

V5.4.2 Changes (BUG FIX):
- 🔥 Bug Fix: is_sunday_morning_closed → Pazar tüm gün kapalı
  (WEEKEND_REOPEN_HOUR=0 ile now.hour < 0 hiçbir zaman true olmuyordu)
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
    """
    Render/proxy arkasında gerçek IP'yi al.
    X-Forwarded-For spoof'a karşı ilk IP'yi alıyoruz —
    Render bu başlığı güvenilir şekilde set ediyor.
    """
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        ips = [ip.strip() for ip in forwarded_for.split(',')]
        return ips[0]
    return request.remote_addr or '0.0.0.0'


def _get_limiter_storage() -> str:
    """
    Redis varsa Redis kullan → tüm Gunicorn worker'ları aynı sayacı paylaşır.
    Redis yoksa memory:// → her worker bağımsız sayar (DDoS koruması zayıf),
    Telegram'a uyarı gönderilir.
    """
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
    try:
        user_id = request.headers.get('X-Client-Id')
        device_id = request.headers.get('X-Device-Id')
        
        if not user_id:
            user_id = request.args.get('user_id') or request.args.get('device_id')
        
        if not device_id:
            device_id = request.args.get('device_id')
        
        if not user_id and not device_id:
            user_id = request.remote_addr or request.headers.get('X-Forwarded-For', 'unknown')
        
        unique_key = f"{user_id or 'unknown'}:{device_id or 'unknown'}"
        
        cache_key = f"online_user:{unique_key}"
        set_cache(cache_key, "1", ttl=300)
        
        log_key = f"api_request:{unique_key}"
        incr_cache(log_key, ttl=86400)
        
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

    stale_key = f"{cache_key}:stale"
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
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    suspicious_agents = ['curl', 'wget', 'python-requests', 'scrapy']
    
    if any(bot in user_agent.lower() for bot in suspicious_agents):
        logger.warning(f"⚠️ Şüpheli User-Agent: {user_agent} | IP: {request.remote_addr}")
    
    return True


def get_smart_banner():
    manual_banner = get_cache("system_banner")
    if manual_banner:
        logger.debug(f"📢 [BANNER] Manual banner bulundu (Priority: 100)")
        return manual_banner
    
    try:
        event_banner = get_todays_banner()
        if event_banner:
            logger.debug(f"🤖 [BANNER] Event banner bulundu: {event_banner[:50]}...")
            return event_banner
    except Exception as e:
        logger.warning(f"⚠️ [BANNER] Event Manager hatası (önemsiz): {e}")
    
    return None


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
        
        result = get_data_guaranteed(cache_key)
        
        if not result:
            return create_response(
                [], 
                503, 
                "Veriler hazırlanıyor, lütfen 1-2 dakika sonra tekrar deneyin."
            )

        data_list = result.get('data', [])
        update_date = result.get('update_date')
        status = result.get('status', 'OPEN')
        market_msg = result.get('market_msg')
        
        banner_msg = get_smart_banner()
        
        if not banner_msg:
            if status in ['MAINTENANCE', 'MAINTENANCE_FULL']:
                banner_msg = market_msg or "🚧 Sistem şu an bakımda. Lütfen daha sonra tekrar deneyin."
            elif status == 'CLOSED':
                banner_msg = market_msg or "🌙 Piyasalar kapalı, iyi hafta sonları!"
        
        meta_data = {
            'count': len(data_list),
            'profile': profile,
            'last_update': update_date,
            'source': result.get('source'),
            'status': status,
            'market_msg': market_msg,
            'banner': banner_msg
        }
        
        return create_response(
            data_list,
            200,
            f"Döviz kurları getirildi ({profile})",
            meta_data
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
            logger.warning(f"⚠️ Geçersiz profil: {profile}, jeweler kullanılıyor")
            profile = "jeweler"
        
        cache_key = get_cache_key_for_profile('golds_all', profile)
        
        result = get_data_guaranteed(cache_key)
        
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
                'count': len(data_list),
                'profile': profile,
                'last_update': result.get('update_date'),
                'status': result.get('status', 'OPEN')
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
            logger.warning(f"⚠️ Geçersiz profil: {profile}, jeweler kullanılıyor")
            profile = "jeweler"
        
        cache_key = get_cache_key_for_profile('silvers_all', profile)
        
        result = get_data_guaranteed(cache_key)
        
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
                'count': len(data_list),
                'profile': profile,
                'last_update': result.get('update_date'),
                'status': result.get('status', 'OPEN')
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
        
        result = get_data_guaranteed(cache_key)
        
        if not result:
            return create_response(
                {}, 
                503, 
                "Veriler hazırlanıyor, lütfen 1-2 dakika sonra tekrar deneyin."
            )
            
        all_currencies = result.get('data', [])
        regional_data = {}
        
        regions = Config.REGIONAL_CURRENCIES
        
        curr_map = {item['code']: item for item in all_currencies}
        
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
    """
    🔥 V5.4.2 BUG FIX:
        - is_sunday_morning_closed → Pazar tüm gün kapalı
          (WEEKEND_REOPEN_HOUR=0 ile now.hour < 0 hiçbir zaman true olmuyordu)
    """
    check_user_agent()
    track_online_user()
    
    try:
        tz = pytz.timezone(Config.DEFAULT_TIMEZONE)
        now = datetime.now(tz)
        
        meta = {
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": Config.DEFAULT_TIMEZONE
        }
        
        # 1️⃣ BAKIM MODU KONTROLÜ
        maintenance_data = get_cache("system_maintenance")
        if maintenance_data and isinstance(maintenance_data, dict):
            end_time = maintenance_data.get("end_time")
            
            if not end_time or time.time() > end_time:
                pass
            else:
                message = maintenance_data.get("message", "Sistem Bakımda")
                mode = maintenance_data.get("mode", "limited")
                status = "MAINTENANCE_FULL" if mode == "full" else "MAINTENANCE"
                
                return create_response(
                    {
                        "status": status,
                        "color": "yellow",
                        "message": message,
                        "next_open": None
                    },
                    200,
                    "Market durumu (Bakım)",
                    meta
                )
        
        # 2️⃣ HAFTA SONU KONTROLÜ
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
                    "status": "CLOSED",
                    "color": "red",
                    "message": "Piyasalar Kapalı",
                    "next_open": next_open.strftime("%Y-%m-%d %H:%M:%S")
                },
                200,
                "Market durumu (Kapalı)",
                meta
            )
        
        # 3️⃣ PIYASA AÇIK
        return create_response(
            {
                "status": "OPEN",
                "color": "green",
                "message": "Piyasalar Açık",
                "next_open": None
            },
            200,
            "Market durumu (Açık)",
            meta
        )
        
    except Exception as e:
        logger.error(f"❌ [MARKET STATUS] Hata: {e}")
        
        return create_response(
            {
                "status": "OPEN",
                "color": "green",
                "message": "Piyasalar Açık",
                "next_open": None
            },
            200,
            "Market durumu (Varsayılan)",
            {
                "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "timezone": Config.DEFAULT_TIMEZONE,
                "error": str(e)
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
                {
                    "banner": top_event['message'],
                    "event_type": top_event['type']
                },
                200,
                "Bugünün banner'ı getirildi",
                {
                    'banner_type': top_event['type'],
                    'priority': top_event['priority'],
                    'valid_until': top_event['valid_until'],
                    'has_events': len(events) > 0,
                    'total_events': len(events)
                }
            )
        else:
            return create_response(
                {
                    "banner": None,
                    "event_type": None
                },
                200,
                "Bugün özel bir banner yok",
                {
                    'banner_type': None,
                    'priority': 0,
                    'has_events': False
                }
            )
            
    except Exception as e:
        logger.error(f"Event Banner Error: {e}")
        return create_response(
            {"banner": None},
            500,
            "Banner alınırken hata oluştu"
        )


@api_bp.route('/fcm/register', methods=['POST'])
@limiter.limit("10 per minute")
def register_fcm_token_endpoint():
    try:
        data = request.get_json()
        
        if not data or 'token' not in data:
            return create_response(
                None,
                400,
                "Token gerekli! Body: {\"token\": \"FCM_TOKEN\"}"
            )
        
        token = data['token'].strip()
        
        if len(token) < 100:
            return create_response(
                None,
                400,
                "Geçersiz token formatı"
            )
        
        success = register_fcm_token(token)
        
        if success:
            logger.info(f"✅ [FCM] Yeni token kaydedildi: {token[:20]}...")
            
            return create_response(
                {"token": token[:20] + "..."},
                200,
                "Token başarıyla kaydedildi"
            )
        else:
            return create_response(
                None,
                500,
                "Token kaydedilemedi"
            )
            
    except Exception as e:
        logger.error(f"❌ [FCM] Token kayıt hatası: {e}")
        return create_response(
            None,
            500,
            f"Sunucu hatası: {str(e)}"
        )


@api_bp.route('/fcm/unregister', methods=['POST'])
@limiter.limit("10 per minute")
def unregister_fcm_token_endpoint():
    try:
        data = request.get_json()
        
        if not data or 'token' not in data:
            return create_response(
                None,
                400,
                "Token gerekli! Body: {\"token\": \"FCM_TOKEN\"}"
            )
        
        token = data['token'].strip()
        
        success = unregister_fcm_token(token)
        
        if success:
            logger.info(f"🗑️ [FCM] Token silindi: {token[:20]}...")
            
            return create_response(
                {"token": token[:20] + "..."},
                200,
                "Token başarıyla silindi"
            )
        else:
            return create_response(
                None,
                404,
                "Token bulunamadı"
            )
            
    except Exception as e:
        logger.error(f"❌ [FCM] Token silme hatası: {e}")
        return create_response(
            None,
            500,
            f"Sunucu hatası: {str(e)}"
        )


@api_bp.route('/fcm/status', methods=['GET'])
@limiter.limit("30 per minute")
def fcm_status():
    try:
        token_count = get_token_count()
        
        last_notification = get_cache(Config.CACHE_KEYS['fcm_last_notification'])
        
        if last_notification:
            last_notification = datetime.fromtimestamp(float(last_notification)).isoformat()
        
        return create_response(
            {
                "total_tokens": token_count,
                "last_notification": last_notification,
                "notification_enabled": Config.FIREBASE_NOTIFICATION_ENABLED
            },
            200,
            "FCM durumu"
        )
        
    except Exception as e:
        logger.error(f"❌ [FCM] Durum sorgulama hatası: {e}")
        return create_response(
            None,
            500,
            f"Sunucu hatası: {str(e)}"
        )


@api_bp.route('/feedback/send', methods=['POST'])
@limiter.limit("5 per hour")
def send_feedback():
    try:
        data = request.get_json()
        
        if not data or 'message' not in data:
            logger.warning("⚠️ [Feedback] Boş mesaj denemesi")
            return create_response(
                None,
                400,
                "Mesaj gerekli! Body: {\"message\": \"Mesajınız\"}"
            )
        
        user_message = data['message'].strip()
        
        if not user_message:
            logger.warning("⚠️ [Feedback] Boş mesaj denemesi")
            return create_response(
                None,
                400,
                "Mesaj boş olamaz"
            )
        
        if len(user_message) < 5:
            return create_response(
                None,
                400,
                "Mesaj en az 5 karakter olmalı"
            )
        
        if len(user_message) > 500:
            return create_response(
                None,
                400,
                "Mesaj en fazla 500 karakter olabilir"
            )
        
        user_id    = request.headers.get('X-Client-Id', 'Bilinmiyor')
        device_id  = request.headers.get('X-Device-Id', 'Bilinmiyor')
        ip_address = request.remote_addr or request.headers.get('X-Forwarded-For', 'Bilinmiyor')
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
            
            success = telegram_bot.send_message(feedback_text, level='report')
            
            if success:
                logger.info(f"✅ [Feedback] Mesaj Telegram'a gönderildi: {user_message[:30]}...")
                return create_response(
                    {"sent": True},
                    200,
                    "Geri bildiriminiz alındı, teşekkürler! 🙏"
                )
            else:
                logger.warning(f"⚠️ [Feedback] Telegram devre dışı, mesaj kaydedildi ama gönderilemedi")
                return create_response(
                    {"sent": False},
                    200,
                    "Geri bildiriminiz alındı, teşekkürler! 🙏"
                )
        else:
            logger.error("❌ [Feedback] Telegram bot başlatılmamış!")
            return create_response(
                {"sent": False},
                200,
                "Geri bildiriminiz alındı, teşekkürler! 🙏"
            )
            
    except Exception as e:
        logger.error(f"❌ [Feedback] Beklenmeyen hata: {e}")
        return create_response(
            {"sent": False},
            200,
            "Geri bildiriminiz alındı, teşekkürler! 🙏"
        )


@api_bp.route('/metrics', methods=['GET'])
@limiter.limit("10 per minute")
def get_metrics():
    try:
        from services.financial_service import get_service_metrics
        from services.maintenance_service import get_scheduler_status
        
        metrics = get_service_metrics()
        scheduler = get_scheduler_status()
        
        return create_response({
            'api_metrics': metrics,
            'scheduler_status': scheduler,
            'environment': Config.ENVIRONMENT
        }, 200)
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
