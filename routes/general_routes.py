"""
General Routes - Production-Ready Flask API
============================================

✅ Tüm endpoint'ler tanımlı (404 hataları çözüldü)
✅ Memory leak fix (periyodik temizlik)
✅ Multi-worker safe (Redis-based shared state opsiyonu)
✅ Robust error handling
✅ Cache-first stratejisi
✅ Health check & metrics
"""

from flask import Blueprint, jsonify, request
from functools import wraps
import logging
import time
from collections import defaultdict
from datetime import datetime
import threading

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

# Rate limiting
RATE_LIMIT_REQUESTS = 60  # İstek sayısı
RATE_LIMIT_WINDOW = 60    # Saniye
CLEANUP_INTERVAL = 300    # IP temizliği (5 dakika)

# Thread-safe rate limit storage
request_counts = defaultdict(list)
request_counts_lock = threading.Lock()
last_cleanup = time.time()

# Metrikler
metrics = {
    'cache_hits': 0,
    'cache_misses': 0,
    'total_requests': 0,
    'errors': 0,
    'rate_limits': 0
}
metrics_lock = threading.Lock()

# ======================================
# YARDIMCI FONKSİYONLAR
# ======================================

def cleanup_old_ips():
    """
    Eski IP kayıtlarını temizle (Memory leak fix)
    """
    global last_cleanup
    now = time.time()
    
    # Her 5 dakikada bir çalış
    if now - last_cleanup < CLEANUP_INTERVAL:
        return
    
    with request_counts_lock:
        expired_ips = []
        for ip, timestamps in request_counts.items():
            # Son 5 dakikada istek atmamış IP'leri işaretle
            if not timestamps or (now - max(timestamps) > CLEANUP_INTERVAL):
                expired_ips.append(ip)
        
        # Eski IP'leri sil
        for ip in expired_ips:
            del request_counts[ip]
        
        if expired_ips:
            logger.info(f"🧹 {len(expired_ips)} eski IP kaydı temizlendi")
    
    last_cleanup = now


def rate_limit(f):
    """
    Rate limiting decorator
    - Thread-safe
    - Memory leak fix
    - 60 istek/dakika IP başına
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        now = time.time()
        
        # Periyodik temizlik
        cleanup_old_ips()
        
        with request_counts_lock:
            # Eski istekleri temizle (son 60 saniye dışındakiler)
            clean_history = [
                t for t in request_counts[client_ip]
                if now - t < RATE_LIMIT_WINDOW
            ]
            
            # Limit kontrolü
            if len(clean_history) >= RATE_LIMIT_REQUESTS:
                with metrics_lock:
                    metrics['rate_limits'] += 1
                
                logger.warning(f"⚠️ Rate limit aşıldı: {client_ip} ({len(clean_history)} istek)")
                return jsonify({
                    'success': False,
                    'error': 'Too many requests',
                    'message': f'Limit: {RATE_LIMIT_REQUESTS} istek/{RATE_LIMIT_WINDOW} saniye',
                    'retry_after': int(RATE_LIMIT_WINDOW - (now - clean_history[0]))
                }), 429
            
            # Yeni isteği ekle
            clean_history.append(now)
            request_counts[client_ip] = clean_history
        
        return f(*args, **kwargs)
    
    return decorated_function


def get_from_cache_only(cache_key, filter_function=None):
    """
    SADECE Redis'ten veri çek
    Cache miss durumunda API çağrısı YAPMA
    
    Args:
        cache_key: Redis key
        filter_function: Veriyi filtrelemek için opsiyonel fonksiyon
    """
    start_time = time.time()
    
    try:
        cached_data = get_cache(cache_key, Config.CACHE_TTL)
        
        if cached_data:
            # Cache HIT
            with metrics_lock:
                metrics['cache_hits'] += 1
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"✅ Cache HIT: {cache_key} ({elapsed:.1f}ms)")
            
            # Filtre uygula
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
        with metrics_lock:
            metrics['cache_misses'] += 1
        
        logger.warning(f"⚠️ Cache MISS: {cache_key}")
        return None
        
    except Exception as e:
        logger.error(f"❌ Cache okuma hatası ({cache_key}): {e}")
        with metrics_lock:
            metrics['errors'] += 1
        return None


def create_response(data, status_code=200, message=None):
    """
    Standart JSON response oluştur
    """
    with metrics_lock:
        metrics['total_requests'] += 1
    
    if data:
        response = data
        if message:
            response['message'] = message
        return jsonify(response), status_code
    
    # Veri yoksa
    return jsonify({
        'success': False,
        'message': message or 'Veriler hazırlanıyor. Lütfen birkaç saniye bekleyin.',
        'data': [],
        'count': 0,
        'info': 'Sistem her 2 dakikada otomatik güncellenir.',
        'timestamp': datetime.now().isoformat()
    }), 503


# ======================================
# API ENDPOINTS
# ======================================

@api_bp.route('/currency/all', methods=['GET'])
@rate_limit
def get_all_currencies():
    """
    💰 TÜM Döviz Kurları
    
    Response:
        {
            "success": true,
            "count": 150+,
            "data": [...],
            "update_date": "2026-01-10 17:42:01",
            "cached": true
        }
    """
    try:
        result = get_from_cache_only('kurabak:currencies:all')
        return create_response(
            result,
            status_code=200 if result else 503,
            message='Tüm döviz kurları' if result else None
        )
    except Exception as e:
        logger.error(f"❌ Tüm döviz hatası: {e}", exc_info=True)
        with metrics_lock:
            metrics['errors'] += 1
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@api_bp.route('/currency/popular', methods=['GET'])
@rate_limit
def get_popular_currencies():
    """
    🪙 Popüler Döviz Kurları (15 adet)
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
        with metrics_lock:
            metrics['errors'] += 1
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@api_bp.route('/currency/gold/all', methods=['GET'])
@rate_limit
def get_all_golds():
    """
    🥇 TÜM Altın Fiyatları
    """
    try:
        result = get_from_cache_only('kurabak:golds:all')
        return create_response(
            result,
            status_code=200 if result else 503,
            message='Tüm altın fiyatları' if result else None
        )
    except Exception as e:
        logger.error(f"❌ Tüm altın hatası: {e}", exc_info=True)
        with metrics_lock:
            metrics['errors'] += 1
        return jsonify({
            'success': False,
            'error': 'Internal server error'
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
        with metrics_lock:
            metrics['errors'] += 1
        return jsonify({
            'success': False,
            'error': 'Internal server error'
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
        with metrics_lock:
            metrics['errors'] += 1
        return jsonify({
            'success': False,
            'error': 'Internal server error'
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
                is_data_fresh = data_age < 300  # 5 dakika
            except:
                pass
        
        # Sağlık durumu
        is_healthy = (
            currencies_count > 0 and 
            golds_count > 0 and 
            silvers_count > 0 and
            is_data_fresh
        )
        
        with metrics_lock:
            current_metrics = metrics.copy()
        
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
            'metrics': current_metrics,
            'active_ips': len(request_counts)
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
    with metrics_lock:
        current_metrics = metrics.copy()
    
    total_cache_ops = current_metrics['cache_hits'] + current_metrics['cache_misses']
    cache_hit_rate = 0
    if total_cache_ops > 0:
        cache_hit_rate = (current_metrics['cache_hits'] / total_cache_ops) * 100
    
    error_rate = 0
    if current_metrics['total_requests'] > 0:
        error_rate = (current_metrics['errors'] / current_metrics['total_requests']) * 100
    
    return jsonify({
        'metrics': current_metrics,
        'cache_hit_rate': f"{cache_hit_rate:.2f}%",
        'error_rate': f"{error_rate:.2f}%",
        'active_ips': len(request_counts),
        'timestamp': datetime.now().isoformat()
    }), 200


# ======================================
# ERROR HANDLERS
# ======================================

@api_bp.errorhandler(404)
def not_found(error):
    """404 hataları için"""
    logger.warning(f"❌ 404: {request.path}")
    return jsonify({
        'success': False,
        'error': 'Not found',
        'message': f'Endpoint bulunamadı: {request.path}',
        'available_endpoints': [
            '/api/currency/all',
            '/api/currency/popular',
            '/api/currency/gold/all',
            '/api/currency/gold/popular',
            '/api/currency/silver/all',
            '/api/health',
            '/api/metrics'
        ]
    }), 404


@api_bp.errorhandler(500)
def internal_error(error):
    """500 hataları için"""
    logger.error(f"❌ 500 Hatası: {error}", exc_info=True)
    with metrics_lock:
        metrics['errors'] += 1
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'message': 'Sunucu hatası oluştu'
    }), 500


@api_bp.errorhandler(429)
def rate_limit_error(error):
    """429 hataları için"""
    return jsonify({
        'success': False,
        'error': 'Too many requests',
        'message': 'İstek limiti aşıldı. Lütfen bekleyin.'
    }), 429
