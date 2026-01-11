"""
General Routes - Production-Ready Flask API (Final)
===================================================
✅ Auto-Recovery: Cache boşsa anında veri çeker (503 Yok!)
✅ Yeni Endpoint: /api/currency/summary (Winner/Loser)
✅ Memory leak fix & Rate limiting
"""

from flask import Blueprint, jsonify, request
from functools import wraps
import logging
import time
from collections import defaultdict
from datetime import datetime
import threading

from utils.cache import get_cache
# Service'den veri çekme fonksiyonunu import ediyoruz
from services.financial_service import sync_financial_data
from config import Config

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

# ======================================
# AYARLAR
# ======================================

POPULAR_CURRENCY_CODES = [
    'USD', 'EUR', 'GBP', 'JPY', 'CHF', 
    'CNY', 'CAD', 'AUD', 'DKK', 'SEK', 
    'NOK', 'SAR', 'QAR', 'KWD', 'AED'
]

POPULAR_GOLD_NAMES = [
    'Gram Altın', 'Çeyrek Altın', 'Yarım Altın', 
    'Tam Altın', 'Cumhuriyet Altını'
]

RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW = 60
CLEANUP_INTERVAL = 300

request_counts = defaultdict(list)
request_counts_lock = threading.Lock()
last_cleanup = time.time()

metrics = {
    'cache_hits': 0,
    'cache_misses': 0,
    'forced_syncs': 0, # Yeni metrik: Zorla veri çekme sayısı
    'total_requests': 0,
    'errors': 0,
    'rate_limits': 0
}
metrics_lock = threading.Lock()

# ======================================
# YARDIMCI FONKSİYONLAR
# ======================================

def cleanup_old_ips():
    global last_cleanup
    now = time.time()
    if now - last_cleanup < CLEANUP_INTERVAL:
        return
    with request_counts_lock:
        expired_ips = []
        for ip, timestamps in request_counts.items():
            if not timestamps or (now - max(timestamps) > CLEANUP_INTERVAL):
                expired_ips.append(ip)
        for ip in expired_ips:
            del request_counts[ip]
        if expired_ips:
            logger.info(f"🧹 {len(expired_ips)} eski IP kaydı temizlendi")
    last_cleanup = now

def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        now = time.time()
        cleanup_old_ips()
        with request_counts_lock:
            clean_history = [t for t in request_counts[client_ip] if now - t < RATE_LIMIT_WINDOW]
            if len(clean_history) >= RATE_LIMIT_REQUESTS:
                with metrics_lock:
                    metrics['rate_limits'] += 1
                logger.warning(f"⚠️ Rate limit aşıldı: {client_ip}")
                return jsonify({'success': False, 'error': 'Too many requests'}), 429
            clean_history.append(now)
            request_counts[client_ip] = clean_history
        return f(*args, **kwargs)
    return decorated_function

# 🔥 KRİTİK DÜZELTME: CACHE BOŞSA SENKRONİZE ET
def get_data_or_sync(cache_key, filter_function=None):
    """
    1. Cache'e bak.
    2. Varsa döndür (HIT).
    3. Yoksa (MISS) -> sync_financial_data() çalıştır.
    4. Tekrar Cache'e bak ve döndür.
    """
    start_time = time.time()
    
    # 1. İlk Deneme
    cached_data = get_cache(cache_key, 3600) # TTL manuel 1 saat verdik service tarafında
    
    if cached_data:
        with metrics_lock:
            metrics['cache_hits'] += 1
        return process_data(cached_data, filter_function)

    # 2. Veri Yok! (Cache Miss) -> Hemen kurtar
    logger.warning(f"⚠️ Cache MISS: {cache_key} -> Veri tazelemeye zorlanıyor...")
    
    with metrics_lock:
        metrics['cache_misses'] += 1
        metrics['forced_syncs'] += 1
    
    # Arka planda değil, bekleyerek yapıyoruz ki kullanıcı boş dönmesin
    success = sync_financial_data()
    
    if success:
        # 3. İkinci Deneme
        cached_data = get_cache(cache_key, 3600)
        if cached_data:
            logger.info(f"✅ Kurtarma başarılı: {cache_key}")
            return process_data(cached_data, filter_function)
    
    return None

def process_data(cached_data, filter_function):
    """Veriyi filtreler ve formatlar"""
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

def create_response(data, status_code=200, message=None):
    with metrics_lock:
        metrics['total_requests'] += 1
    
    if data:
        response = data
        if message:
            response['message'] = message
        return jsonify(response), status_code
    
    return jsonify({
        'success': False,
        'message': 'Sistem verileri güncelliyor, lütfen tekrar deneyin.',
        'error': 'Service temporarily unavailable'
    }), 503

# ======================================
# API ENDPOINTS
# ======================================

# 🔥 YENİ: GÜNÜN ÖZETİ (WINNER/LOSER)
@api_bp.route('/currency/summary', methods=['GET'])
@rate_limit
def get_daily_summary():
    """
    📈 Günün Özeti (En çok artan / En çok düşen)
    """
    try:
        # Sadece data key'ini döndürmek yeterli
        def extract_summary(data):
            # Cache yapısında veri 'data' altında değil direkt kökte olabilir
            # financial_service'de kaydederken { ... "data": {...} } yaptık.
            return data 

        result = get_data_or_sync('kurabak:summary')
        
        # summary verisi özel formatta olduğu için direkt data'yı alıyoruz
        if result and 'data' in result:
            return jsonify({
                'success': True,
                'data': result['data'],
                'update_date': result.get('update_date')
            }), 200
            
        return create_response(None, message="Özet veri bulunamadı")

    except Exception as e:
        logger.error(f"❌ Özet veri hatası: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@api_bp.route('/currency/all', methods=['GET'])
@rate_limit
def get_all_currencies():
    try:
        result = get_data_or_sync('kurabak:currencies:all')
        return create_response(result, 200 if result else 503)
    except Exception as e:
        logger.error(f"❌ Hata: {e}", exc_info=True)
        return jsonify({'success': False}), 500

@api_bp.route('/currency/popular', methods=['GET'])
@rate_limit
def get_popular_currencies():
    try:
        def filter_popular(currencies):
            return [c for c in currencies if c.get('code') in POPULAR_CURRENCY_CODES]
        
        result = get_data_or_sync('kurabak:currencies:all', filter_popular)
        return create_response(result, 200 if result else 503)
    except Exception as e:
        logger.error(f"❌ Hata: {e}", exc_info=True)
        return jsonify({'success': False}), 500

@api_bp.route('/currency/gold/all', methods=['GET'])
@rate_limit
def get_all_golds():
    try:
        result = get_data_or_sync('kurabak:golds:all')
        return create_response(result, 200 if result else 503)
    except Exception as e:
        logger.error(f"❌ Hata: {e}", exc_info=True)
        return jsonify({'success': False}), 500

@api_bp.route('/currency/gold/popular', methods=['GET'])
@rate_limit
def get_popular_golds():
    try:
        def filter_popular(golds):
            return [g for g in golds if g.get('name') in POPULAR_GOLD_NAMES]
        
        result = get_data_or_sync('kurabak:golds:all', filter_popular)
        return create_response(result, 200 if result else 503)
    except Exception as e:
        logger.error(f"❌ Hata: {e}", exc_info=True)
        return jsonify({'success': False}), 500

@api_bp.route('/currency/silver/all', methods=['GET'])
@rate_limit
def get_all_silvers():
    try:
        result = get_data_or_sync('kurabak:silvers:all')
        return create_response(result, 200 if result else 503)
    except Exception as e:
        logger.error(f"❌ Hata: {e}", exc_info=True)
        return jsonify({'success': False}), 500

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Sağlık kontrolü"""
    try:
        currencies = get_cache('kurabak:currencies:all', 3600)
        is_healthy = currencies is not None
        
        return jsonify({
            'status': 'healthy' if is_healthy else 'degraded',
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics
        }), 200 if is_healthy else 503
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@api_bp.route('/metrics', methods=['GET'])
def get_metrics():
    """Metrikler"""
    with metrics_lock:
        current = metrics.copy()
    return jsonify({
        'metrics': current,
        'active_ips': len(request_counts),
        'timestamp': datetime.now().isoformat()
    }), 200

# Error Handlers
@api_bp.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Not found'}), 404

@api_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

@api_bp.errorhandler(429)
def rate_limit_error(error):
    return jsonify({'success': False, 'error': 'Too many requests'}), 429
