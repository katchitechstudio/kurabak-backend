"""
General Routes - Profesyonel Flask API Endpoints
================================================

Özellikler:
✅ Rate limiting koruması
✅ Cache-first stratejisi (API çağrısı YOK!)
✅ Detaylı loglama ve metrikler
✅ Hata yönetimi
✅ Health check endpoint
✅ CORS desteği
"""

from flask import Blueprint, jsonify, request
from functools import wraps
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta

from utils.cache import get_cache
from config import Config

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

# ======================================
# AYARLAR
# ======================================

# Popüler döviz kodları
POPULAR_CURRENCY_CODES = [
    'USD', 'EUR', 'GBP', 'JPY', 'CHF', 
    'CNY', 'CAD', 'AUD', 'DKK', 'SEK', 
    'NOK', 'SAR', 'QAR', 'KWD', 'AED'
]

# Popüler altın isimleri
POPULAR_GOLD_NAMES = [
    'Gram Altın', 'Çeyrek Altın', 'Yarım Altın', 
    'Tam Altın', 'Cumhuriyet Altını'
]

# Rate limiting (IP başına)
RATE_LIMIT_REQUESTS = 60  # İstek sayısı
RATE_LIMIT_WINDOW = 60    # Saniye cinsinden
request_counts = defaultdict(list)

# Metrikler
metrics = {
    'cache_hits': 0,
    'cache_misses': 0,
    'total_requests': 0,
    'errors': 0
}

# ======================================
# YARDIMCI FONKSİYONLAR
# ======================================

def rate_limit(f):
    """
    Rate limiting decorator
    60 istek/dakika IP başına
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        now = time.time()
        
        # Eski istekleri temizle
        request_counts[client_ip] = [
            req_time for req_time in request_counts[client_ip]
            if now - req_time < RATE_LIMIT_WINDOW
        ]
        
        # Limit kontrolü
        if len(request_counts[client_ip]) >= RATE_LIMIT_REQUESTS:
            logger.warning(f"⚠️ Rate limit aşıldı: {client_ip}")
            return jsonify({
                'success': False,
                'error': 'Too many requests',
                'message': f'Limit: {RATE_LIMIT_REQUESTS} istek/{RATE_LIMIT_WINDOW} saniye'
            }), 429
        
        # İsteği kaydet
        request_counts[client_ip].append(now)
        return f(*args, **kwargs)
    
    return decorated_function


def get_from_cache_only(cache_key, filter_function=None):
    """
    SADECE Redis'ten veri çek
    Cache miss durumunda API çağrısı YAPMA (scheduler hallediyor)
    
    Args:
        cache_key: Redis key
        filter_function: Veriyi filtrelemek için opsiyonel fonksiyon
        
    Returns:
        dict: Başarılı ise veri, değilse None
    """
    start_time = time.time()
    
    try:
        # Redis'ten çek
        cached_data = get_cache(cache_key, Config.CACHE_TTL)
        
        if cached_data:
            # Cache HIT
            metrics['cache_hits'] += 1
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"✅ Cache HIT: {cache_key} ({elapsed:.2f}ms)")
            
            # Filtre uygula (popüler listeler için)
            if filter_function and isinstance(cached_data, dict):
                filtered_data = filter_function(cached_data.get('data', []))
                return {
                    'success': True,
                    'count': len(filtered_data),
                    'data': filtered_data,
                    'update_date': cached_data.get('update_date'),
                    'cached': True
                }
            
            return {**cached_data, 'cached': True}
        
        # Cache MISS
        metrics['cache_misses'] += 1
        logger.warning(f"⚠️ Cache MISS: {cache_key} - Scheduler henüz veri çekmemiş")
        return None
        
    except Exception as e:
        logger.error(f"❌ Cache okuma hatası ({cache_key}): {e}")
        metrics['errors'] += 1
        return None


def create_response(data, status_code=200, message=None):
    """
    Standart JSON response oluştur
    """
    metrics['total_requests'] += 1
    
    if data:
        response = data
        if message:
            response['message'] = message
        return jsonify(response), status_code
    
    # Veri yoksa
    return jsonify({
        'success': False,
        'message': message or 'Veriler henüz hazırlanıyor. Lütfen birkaç saniye bekleyin.',
        'data': [],
        'count': 0,
        'info': 'Sistem her 2 dakikada bir otomatik güncellenir.'
    }), 503


# ======================================
# API ENDPOINTS
# ======================================

@api_bp.route('/currency/popular', methods=['GET'])
@rate_limit
def get_popular_currencies():
    """
    🪙 Popüler Döviz Kurları (15 adet)
    
    Response:
        {
            "success": true,
            "count": 15,
            "data": [...],
            "update_date": "2026-01-08 20:00:54",
            "cached": true
        }
    """
    try:
        def filter_popular(currencies):
            return [
                c for c in currencies 
                if c.get('code') in POPULAR_CURRENCY_CODES
            ]
        
        result = get_from_cache_only('kurabak:currencies:all', filter_popular)
        return create_response(
            result, 
            status_code=200 if result else 503,
            message='Popüler döviz kurları' if result else None
        )
        
    except Exception as e:
        logger.error(f"❌ Popüler döviz hatası: {e}", exc_info=True)
        metrics['errors'] += 1
        return jsonify({
            'success': False, 
            'error': 'Internal server error',
            'message': 'Bir hata oluştu'
        }), 500


@api_bp.route('/currency/gold/popular', methods=['GET'])
@rate_limit
def get_popular_golds():
    """
    🥇 Popüler Altın Fiyatları (5 adet)
    """
    try:
        def filter_popular(golds):
            return [
                g for g in golds 
                if g.get('name') in POPULAR_GOLD_NAMES
            ]
        
        result = get_from_cache_only('kurabak:golds:all', filter_popular)
        return create_response(
            result,
            status_code=200 if result else 503,
            message='Popüler altın fiyatları' if result else None
        )
        
    except Exception as e:
        logger.error(f"❌ Popüler altın hatası: {e}", exc_info=True)
        metrics['errors'] += 1
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'Bir hata oluştu'
        }), 500


@api_bp.route('/currency/silver/all', methods=['GET'])
@rate_limit
def get_all_silvers():
    """
    🥈 Gümüş Fiyatları
    """
    try:
        result = get_from_cache_only('kurabak:silvers:all')
        return create_response(
            result,
            status_code=200 if result else 503,
            message='Gümüş fiyatları' if result else None
        )
        
    except Exception as e:
        logger.error(f"❌ Gümüş fiyatı hatası: {e}", exc_info=True)
        metrics['errors'] += 1
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'Bir hata oluştu'
        }), 500


# ======================================
# HEALTH CHECK & METRICS
# ======================================

@api_bp.route('/health', methods=['GET'])
def health_check():
    """
    🏥 Sistem sağlık kontrolü
    """
    try:
        # Cache'leri kontrol et
        currencies = get_cache('kurabak:currencies:all', Config.CACHE_TTL)
        golds = get_cache('kurabak:golds:all', Config.CACHE_TTL)
        silvers = get_cache('kurabak:silvers:all', Config.CACHE_TTL)
        
        currencies_count = len(currencies.get('data', [])) if currencies else 0
        golds_count = len(golds.get('data', [])) if golds else 0
        silvers_count = len(silvers.get('data', [])) if silvers else 0
        
        # Veri yaşını kontrol et
        is_data_fresh = False
        data_age = None
        
        if currencies and currencies.get('update_date'):
            try:
                update_time = datetime.fromisoformat(currencies['update_date'])
                data_age = (datetime.now() - update_time).total_seconds()
                # 5 dakikadan eskiyse uyarı
                is_data_fresh = data_age < 300
            except:
                pass
        
        # Sağlık durumu
        is_healthy = (
            currencies_count > 0 and 
            golds_count > 0 and 
            silvers_count > 0 and
            is_data_fresh
        )
        
        response = {
            'status': 'healthy' if is_healthy else 'degraded',
            'timestamp': datetime.now().isoformat(),
            'data': {
                'currencies': {
                    'count': currencies_count,
                    'status': 'ok' if currencies_count > 0 else 'missing'
                },
                'golds': {
                    'count': golds_count,
                    'status': 'ok' if golds_count > 0 else 'missing'
                },
                'silvers': {
                    'count': silvers_count,
                    'status': 'ok' if silvers_count > 0 else 'missing'
                }
            },
            'data_age_seconds': data_age,
            'data_fresh': is_data_fresh,
            'metrics': metrics
        }
        
        return jsonify(response), 200 if is_healthy else 503
        
    except Exception as e:
        logger.error(f"❌ Health check hatası: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@api_bp.route('/metrics', methods=['GET'])
def get_metrics():
    """
    📊 API metrikleri
    """
    cache_hit_rate = 0
    if metrics['cache_hits'] + metrics['cache_misses'] > 0:
        cache_hit_rate = (
            metrics['cache_hits'] / 
            (metrics['cache_hits'] + metrics['cache_misses'])
        ) * 100
    
    return jsonify({
        'metrics': metrics,
        'cache_hit_rate': f"{cache_hit_rate:.2f}%",
        'error_rate': f"{(metrics['errors'] / max(metrics['total_requests'], 1)) * 100:.2f}%",
        'active_rate_limits': len(request_counts)
    }), 200


# ======================================
# ERROR HANDLERS
# ======================================

@api_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Not found',
        'message': 'Endpoint bulunamadı'
    }), 404


@api_bp.errorhandler(500)
def internal_error(error):
    logger.error(f"❌ 500 Hatası: {error}")
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'message': 'Sunucu hatası oluştu'
    }), 500
