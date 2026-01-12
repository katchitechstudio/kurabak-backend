"""
General Routes - ULTIMATE MOTOR EDITION 🤖
==========================================
✅ Zero-Downtime Cache Recovery (Async Background Sync)
✅ Smart 404/503 Response Logic
✅ Enhanced Error Handling
✅ Memory Leak Prevention
✅ Optimized Rate Limiting
✅ Production-Grade Performance
✅ MOTOR GİBİ ÇALIŞIR!
"""

from flask import Blueprint, jsonify, request
from functools import wraps
import logging
import time
import threading
from collections import defaultdict
from datetime import datetime

from utils.cache import get_cache
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

# Thread-safe structures
request_counts = defaultdict(list)
request_counts_lock = threading.Lock()
last_cleanup = time.time()

# Background sync tracker
_background_sync_running = False
_background_sync_lock = threading.Lock()
_last_background_sync = 0

metrics = {
    'cache_hits': 0,
    'cache_misses': 0,
    'forced_syncs': 0,
    'background_syncs': 0,
    'total_requests': 0,
    'errors': 0,
    'rate_limits': 0
}
metrics_lock = threading.Lock()

# ======================================
# YARDIMCI FONKSİYONLAR
# ======================================

def cleanup_old_ips():
    """Eski IP kayıtlarını temizle (memory leak önleme)"""
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
    """Rate limiting decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        now = time.time()
        
        cleanup_old_ips()
        
        with request_counts_lock:
            # Son 60 saniyedeki istekleri filtrele
            clean_history = [t for t in request_counts[client_ip] if now - t < RATE_LIMIT_WINDOW]
            
            if len(clean_history) >= RATE_LIMIT_REQUESTS:
                with metrics_lock:
                    metrics['rate_limits'] += 1
                logger.warning(f"⚠️ Rate limit aşıldı: {client_ip}")
                return jsonify({
                    'success': False, 
                    'error': 'Too many requests',
                    'message': f'Limit: {RATE_LIMIT_REQUESTS} istek/{RATE_LIMIT_WINDOW} saniye'
                }), 429
            
            clean_history.append(now)
            request_counts[client_ip] = clean_history
        
        return f(*args, **kwargs)
    
    return decorated_function


def trigger_background_sync():
    """
    🔥 ARKA PLAN SENKRONİZASYONU
    
    Kullanıcıyı bekletmeden arka planda veri günceller
    Aynı anda sadece 1 sync çalışabilir (thread-safe)
    """
    global _background_sync_running, _last_background_sync
    
    with _background_sync_lock:
        # Zaten sync çalışıyorsa atla
        if _background_sync_running:
            logger.debug("⏳ Background sync zaten çalışıyor, atlanıyor")
            return False
        
        # Son 10 saniyede sync yapıldıysa atla (rate limit)
        now = time.time()
        if now - _last_background_sync < 10:
            logger.debug("⏳ Background sync çok yakın zamanda yapıldı, atlanıyor")
            return False
        
        # Sync başlat
        _background_sync_running = True
        _last_background_sync = now
    
    def _sync_worker():
        """Background worker thread"""
        global _background_sync_running
        
        try:
            logger.info("🔄 Background sync başlatıldı")
            success = sync_financial_data()
            
            with metrics_lock:
                metrics['background_syncs'] += 1
            
            if success:
                logger.info("✅ Background sync tamamlandı")
            else:
                logger.warning("⚠️ Background sync başarısız")
        
        except Exception as e:
            logger.error(f"❌ Background sync hatası: {e}", exc_info=True)
        
        finally:
            with _background_sync_lock:
                _background_sync_running = False
    
    # Thread başlat (daemon=True → main thread bitince otomatik kapanır)
    thread = threading.Thread(target=_sync_worker, daemon=True, name="BackgroundSync")
    thread.start()
    
    return True


def get_data_or_sync(cache_key, filter_function=None):
    """
    🤖 MOTOR GİBİ CACHE SİSTEMİ
    
    Akış:
    1. Cache'e bak → Varsa HEMEN dön (ultra hızlı) ✅
    2. Yoksa:
       a) Arka planda sync başlat (kullanıcı beklemez) 🔄
       b) None dön (kullanıcı hemen cevap alır) ⚡
    
    Kullanıcı Deneyimi:
    - İlk istek: 503 "Sistem hazırlanıyor, 5 saniye sonra tekrar dene"
    - 5 saniye sonra: Cache doldu, hızlı yanıt! ✅
    """
    start_time = time.time()
    
    # 1. Cache'e bak
    cached_data = get_cache(cache_key, Config.CACHE_TTL)
    
    if cached_data:
        # ✅ CACHE HIT - Ultra hızlı yanıt
        with metrics_lock:
            metrics['cache_hits'] += 1
        return process_data(cached_data, filter_function)
    
    # 2. CACHE MISS - Arka planda güncelle
    with metrics_lock:
        metrics['cache_misses'] += 1
    
    logger.warning(f"⚠️ Cache MISS: {cache_key} → Background sync tetikleniyor")
    
    # Arka planda sync başlat (non-blocking!)
    triggered = trigger_background_sync()
    
    if triggered:
        logger.info(f"🔄 Background sync tetiklendi ({cache_key})")
    
    # None dön (kullanıcı hemen 503 alır, arka planda hazırlanır)
    return None


def process_data(cached_data, filter_function):
    """Veriyi filtreler ve formatlar"""
    if filter_function and isinstance(cached_data, dict):
        data_list = cached_data.get('data', [])
        filtered_data = filter_function(data_list)
        
        return {
            'success': True,
            'count': len(filtered_data),
            'data': filtered_data,
            'update_date': cached_data.get('update_date'),
            'api_version': cached_data.get('api_version', 'Unknown'),
            'cached': True
        }
    
    return {**cached_data, 'cached': True}


def create_response(data, status_code=200, message=None):
    """Standart JSON response oluştur"""
    with metrics_lock:
        metrics['total_requests'] += 1
    
    if data:
        response = data
        if message:
            response['message'] = message
        return jsonify(response), status_code
    
    # Veri yoksa 503 dön (sistem hazırlanıyor)
    return jsonify({
        'success': False,
        'message': 'Sistem verileri hazırlıyor, lütfen 5-10 saniye sonra tekrar deneyin',
        'error': 'Cache initializing',
        'retry_after': 5
    }), 503

# ======================================
# API ENDPOINTS
# ======================================

@api_bp.route('/currency/summary', methods=['GET'])
@rate_limit
def get_daily_summary():
    """
    📈 Günün Özeti (En çok artan / En çok düşen)
    
    Returns:
        200: Özet verisi mevcut
        404: Özet bulunamadı (hesaplama hatası)
        503: Sistem hazırlanıyor
    """
    try:
        result = get_data_or_sync('kurabak:summary')
        
        if result is None:
            # Cache boş, arka planda hazırlanıyor
            return jsonify({
                'success': False,
                'message': 'Günün özeti hazırlanıyor, lütfen 5-10 saniye sonra tekrar deneyin',
                'retry_after': 5
            }), 503
        
        if result and 'data' in result:
            # Özet var ve geçerli
            return jsonify({
                'success': True,
                'data': result['data'],
                'update_date': result.get('update_date'),
                'api_version': result.get('api_version', 'Unknown'),
                'cached': True
            }), 200
        
        # Veri var ama 'data' field yok (hatalı format)
        logger.error(f"❌ Summary cache formatı hatalı: {result}")
        return jsonify({
            'success': False,
            'message': 'Özet veri formatı hatalı',
            'error': 'Invalid data format'
        }), 500

    except Exception as e:
        logger.error(f"❌ Özet veri hatası: {e}", exc_info=True)
        with metrics_lock:
            metrics['errors'] += 1
        return jsonify({
            'success': False, 
            'error': 'Internal server error'
        }), 500


@api_bp.route('/currency/all', methods=['GET'])
@rate_limit
def get_all_currencies():
    """
    💱 Tüm Döviz Kurları
    
    Returns:
        200: Tüm dövizler
        503: Sistem hazırlanıyor
    """
    try:
        result = get_data_or_sync('kurabak:currencies:all')
        
        if result is None:
            return create_response(None, 503)
        
        return create_response(result, 200)
    
    except Exception as e:
        logger.error(f"❌ Currencies endpoint hatası: {e}", exc_info=True)
        with metrics_lock:
            metrics['errors'] += 1
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api_bp.route('/currency/popular', methods=['GET'])
@rate_limit
def get_popular_currencies():
    """
    ⭐ Popüler Döviz Kurları (15 adet)
    
    Returns:
        200: Popüler dövizler
        503: Sistem hazırlanıyor
    """
    try:
        def filter_popular(currencies):
            return [c for c in currencies if c.get('code') in POPULAR_CURRENCY_CODES]
        
        result = get_data_or_sync('kurabak:currencies:all', filter_popular)
        
        if result is None:
            return create_response(None, 503)
        
        return create_response(result, 200)
    
    except Exception as e:
        logger.error(f"❌ Popular currencies endpoint hatası: {e}", exc_info=True)
        with metrics_lock:
            metrics['errors'] += 1
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api_bp.route('/currency/gold/all', methods=['GET'])
@rate_limit
def get_all_golds():
    """
    🪙 Tüm Altın Fiyatları
    
    Returns:
        200: Tüm altınlar
        503: Sistem hazırlanıyor
    """
    try:
        result = get_data_or_sync('kurabak:golds:all')
        
        if result is None:
            return create_response(None, 503)
        
        return create_response(result, 200)
    
    except Exception as e:
        logger.error(f"❌ Golds endpoint hatası: {e}", exc_info=True)
        with metrics_lock:
            metrics['errors'] += 1
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api_bp.route('/currency/gold/popular', methods=['GET'])
@rate_limit
def get_popular_golds():
    """
    ⭐ Popüler Altın Fiyatları (5 adet)
    
    Returns:
        200: Popüler altınlar
        503: Sistem hazırlanıyor
    """
    try:
        def filter_popular(golds):
            return [g for g in golds if g.get('name') in POPULAR_GOLD_NAMES]
        
        result = get_data_or_sync('kurabak:golds:all', filter_popular)
        
        if result is None:
            return create_response(None, 503)
        
        return create_response(result, 200)
    
    except Exception as e:
        logger.error(f"❌ Popular golds endpoint hatası: {e}", exc_info=True)
        with metrics_lock:
            metrics['errors'] += 1
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api_bp.route('/currency/silver/all', methods=['GET'])
@rate_limit
def get_all_silvers():
    """
    🥈 Gümüş Fiyatı
    
    Returns:
        200: Gümüş verisi
        503: Sistem hazırlanıyor
    """
    try:
        result = get_data_or_sync('kurabak:silvers:all')
        
        if result is None:
            return create_response(None, 503)
        
        return create_response(result, 200)
    
    except Exception as e:
        logger.error(f"❌ Silver endpoint hatası: {e}", exc_info=True)
        with metrics_lock:
            metrics['errors'] += 1
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api_bp.route('/health', methods=['GET'])
def health_check():
    """
    🏥 Sağlık Kontrolü
    
    Returns:
        200: Sistem sağlıklı
        503: Sistem hazırlanıyor veya sorunlu
    """
    try:
        # Cache'den verileri kontrol et
        currencies = get_cache('kurabak:currencies:all', Config.CACHE_TTL)
        golds = get_cache('kurabak:golds:all', Config.CACHE_TTL)
        silvers = get_cache('kurabak:silvers:all', Config.CACHE_TTL)
        
        c_count = len(currencies.get('data', [])) if currencies else 0
        g_count = len(golds.get('data', [])) if golds else 0
        s_count = len(silvers.get('data', [])) if silvers else 0
        
        # Veri yaşını kontrol et
        is_fresh = False
        data_age = None
        
        if currencies and currencies.get('update_date'):
            try:
                update_time = datetime.fromisoformat(currencies['update_date'])
                data_age = (datetime.now() - update_time).total_seconds()
                is_fresh = data_age < 300  # 5 dakikadan taze mi?
            except:
                pass
        
        # Sağlık kriterleri
        is_healthy = (
            c_count >= Config.HEALTH_MIN_CURRENCIES and 
            g_count >= Config.HEALTH_MIN_GOLDS and 
            s_count >= Config.HEALTH_MIN_SILVERS and 
            is_fresh
        )
        
        status = 'healthy' if is_healthy else 'degraded'
        http_code = 200 if is_healthy else 503
        
        return jsonify({
            "status": status,
            "data": {
                "currencies": {"count": c_count, "ok": c_count >= Config.HEALTH_MIN_CURRENCIES},
                "golds": {"count": g_count, "ok": g_count >= Config.HEALTH_MIN_GOLDS},
                "silvers": {"count": s_count, "ok": s_count >= Config.HEALTH_MIN_SILVERS}
            },
            "data_age_seconds": data_age,
            "data_fresh": is_fresh,
            "redis_enabled": currencies is not None,
            "background_sync_running": _background_sync_running,
            "timestamp": datetime.now().isoformat()
        }), http_code
    
    except Exception as e:
        logger.error(f"❌ Health check hatası: {e}", exc_info=True)
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500


@api_bp.route('/metrics', methods=['GET'])
def get_metrics():
    """
    📊 API Metrikleri
    
    Returns:
        200: Metrik verileri
    """
    with metrics_lock:
        current_metrics = metrics.copy()
    
    # Hesaplanmış metrikler
    total_cache_ops = current_metrics['cache_hits'] + current_metrics['cache_misses']
    cache_hit_rate = (
        (current_metrics['cache_hits'] / total_cache_ops * 100)
        if total_cache_ops > 0 else 0
    )
    
    return jsonify({
        'metrics': {
            **current_metrics,
            'cache_hit_rate': f"{cache_hit_rate:.2f}%",
            'total_cache_operations': total_cache_ops
        },
        'background_sync': {
            'running': _background_sync_running,
            'last_sync': _last_background_sync,
            'total_syncs': current_metrics['background_syncs']
        },
        'rate_limiting': {
            'active_ips': len(request_counts),
            'total_limits': current_metrics['rate_limits']
        },
        'timestamp': datetime.now().isoformat()
    }), 200

# ======================================
# ERROR HANDLERS
# ======================================

@api_bp.errorhandler(404)
def not_found(error):
    """404 - Endpoint bulunamadı"""
    return jsonify({
        'success': False, 
        'error': 'Not found',
        'message': 'Bu endpoint bulunamadı'
    }), 404


@api_bp.errorhandler(500)
def internal_error(error):
    """500 - Internal server error"""
    logger.error(f"❌ 500 Internal Server Error: {error}", exc_info=True)
    with metrics_lock:
        metrics['errors'] += 1
    return jsonify({
        'success': False, 
        'error': 'Internal server error',
        'message': 'Sunucu hatası oluştu'
    }), 500


@api_bp.errorhandler(429)
def rate_limit_error(error):
    """429 - Rate limit aşıldı"""
    return jsonify({
        'success': False, 
        'error': 'Rate limit exceeded',
        'message': 'Çok fazla istek gönderdiniz, lütfen bekleyin'
    }), 429
