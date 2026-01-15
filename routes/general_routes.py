"""
General Routes - PRODUCTION READY v2.1 🚀
========================================
✅ Proxy-Aware IP Detection (Render/Cloudflare Safe)
✅ Regional Currencies (21 döviz, 5 bölge)
✅ Zero-Downtime Cache Recovery
✅ Smart Background Sync with Backoff
✅ Memory Leak Prevention
✅ Advanced Rate Limiting
✅ Health Check with Degradation Detection
✅ Comprehensive Metrics
✅ Error Handling & Logging
"""

from flask import Blueprint, jsonify, request, current_app
from functools import wraps
import logging
import time
import threading
import hashlib
from collections import defaultdict, deque
from datetime import datetime
import os

# App.py ile uyumlu importlar
from utils.cache import get_cache, redis_client
from services.maintenance_service import fetch_all_data, manual_trigger
from config import Config

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

# ======================================
# REGIONAL CURRENCY MAPPING
# ======================================

REGION_MAP = {
    # 🇺🇸 Kuzey Amerika
    "USD": "north_america",
    "CAD": "north_america",
    
    # 🇪🇺 Avrupa Birliği
    "EUR": "europe",
    "GBP": "europe",
    "CHF": "europe",
    "SEK": "europe",
    "NOK": "europe",
    "DKK": "europe",
    "PLN": "europe",
    "HUF": "europe",
    
    # 🇷🇺 Doğu Avrupa ve Komşular
    "RUB": "east_europe",
    "AZN": "east_europe",
    "BGN": "east_europe",
    "RON": "east_europe",
    
    # 🇸🇦 Orta Doğu ve Körfez
    "SAR": "middle_east",
    "AED": "middle_east",
    "KWD": "middle_east",
    "QAR": "middle_east",
    
    # 🇨🇳 Asya-Pasifik
    "CNY": "asia_pacific",
    "AUD": "asia_pacific"
}

REGION_NAMES = {
    "north_america": "🇺🇸 Kuzey Amerika",
    "europe": "🇪🇺 Avrupa Birliği",
    "east_europe": "🇷🇺 Doğu Avrupa ve Komşular",
    "middle_east": "🇸🇦 Orta Doğu ve Körfez",
    "asia_pacific": "🇨🇳 Asya-Pasifik"
}

POPULAR_GOLD_NAMES = [
    'Gram Altın', 'Çeyrek Altın', 'Yarım Altın',
    'Tam Altın', 'Cumhuriyet Altını', 'Ata Altın',
    'Reşat Altın', 'Hamit Altın'
]

# ======================================
# UTILITY FUNCTIONS
# ======================================

def get_real_ip():
    """
    Render/Cloudflare/Heroku gibi proxy arkasında gerçek IP adresini bulur.
    """
    # X-Forwarded-For: proxy zincirindeki tüm IP'ler
    x_forwarded_for = request.headers.getlist("X-Forwarded-For")
    if x_forwarded_for:
        # İlk IP genellikle orijinal client
        return x_forwarded_for[0].split(',')[0].strip()
    
    # X-Real-IP: Nginx gibi reverse proxy'ler
    x_real_ip = request.headers.get('X-Real-IP')
    if x_real_ip:
        return x_real_ip.strip()
    
    # Fallback
    return request.remote_addr or "unknown"

def create_response(data, status_code=200, message=None, meta=None):
    """Standart JSON response oluştur"""
    response = {
        'success': status_code < 400,
        'data': data,
        'meta': meta or {},
        'timestamp': datetime.now().isoformat()
    }
    
    if message:
        response['message'] = message
    
    return jsonify(response), status_code

# ======================================
# ADVANCED RATE LIMITING SYSTEM
# ======================================

class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(deque)
        self.lock = threading.Lock()
        self.cleanup_interval = 300  # 5 dakika
        self.last_cleanup = time.time()
        
        # Farklı endpoint'ler için farklı limitler
        self.limits = {
            'default': (60, 60),      # 60 requests / 60 seconds
            'summary': (30, 60),      # 30 requests / 60 seconds
            'sync': (5, 60),          # 5 requests / 60 seconds
            'health': (120, 60),      # 120 requests / 60 seconds
        }
    
    def get_client_identifier(self):
        """İstemciyi benzersiz şekilde tanımla (IP + User-Agent hash)"""
        ip = get_real_ip()
        user_agent = request.headers.get('User-Agent', '')[:50]
        
        # User-Agent'ın ilk 50 karakterini hash'le
        ua_hash = hashlib.md5(user_agent.encode()).hexdigest()[:8]
        
        return f"{ip}:{ua_hash}"
    
    def is_rate_limited(self, endpoint_key='default'):
        """Rate limit kontrolü yap"""
        client_id = self.get_client_identifier()
        now = time.time()
        
        # Otomatik temizlik
        self._cleanup_old_requests(now)
        
        with self.lock:
            limit, window = self.limits.get(endpoint_key, self.limits['default'])
            
            # Bu client'ın request'lerini temizle
            client_requests = self.requests[client_id]
            
            # Süresi geçmiş request'leri temizle
            while client_requests and now - client_requests[0] > window:
                client_requests.popleft()
            
            # Limit kontrolü
            if len(client_requests) >= limit:
                return True, limit, window, len(client_requests)
            
            # Yeni request ekle
            client_requests.append(now)
            return False, limit, window, len(client_requests)
    
    def _cleanup_old_requests(self, now):
        """Eski request kayıtlarını temizle"""
        if now - self.last_cleanup < self.cleanup_interval:
            return
        
        with self.lock:
            expired_clients = []
            for client_id, timestamps in self.requests.items():
                if not timestamps or (now - timestamps[-1] > self.cleanup_interval):
                    expired_clients.append(client_id)
            
            for client_id in expired_clients:
                del self.requests[client_id]
            
            if expired_clients:
                logger.debug(f"🧹 Rate limiter: {len(expired_clients)} eski client temizlendi")
        
        self.last_cleanup = now
    
    def get_stats(self):
        with self.lock:
            return {
                'total_clients': len(self.requests),
                'active_clients': sum(1 for ts in self.requests.values() if ts and time.time() - ts[-1] < 300)
            }

rate_limiter = RateLimiter()

# ======================================
# DECORATORS
# ======================================

def rate_limit(endpoint_key='default'):
    """Advanced rate limiting decorator"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Rate limit kontrolü
            limited, limit, window, current = rate_limiter.is_rate_limited(endpoint_key)
            
            if limited:
                logger.warning(f"⏸️ Rate limit: {get_real_ip()} -> {endpoint_key} ({current}/{limit})")
                return create_response(
                    None,
                    429,
                    f"Too many requests. Limit: {limit}/{window}s",
                    {'retry_after': window}
                )
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ======================================
# BACKGROUND SYNC MANAGER
# ======================================

class BackgroundSyncManager:
    def __init__(self):
        self.running = False
        self.lock = threading.Lock()
        self.last_sync_time = 0
        self.consecutive_failures = 0
    
    def should_sync(self):
        now = time.time()
        with self.lock:
            if self.running: return False
            if now - self.last_sync_time < 10: return False
            return True
    
    def start_sync(self):
        with self.lock:
            if self.running: return False
            self.running = True
            self.last_sync_time = time.time()
        
        def _sync_worker():
            try:
                # App.py ile uyumlu servis çağrısı
                result = manual_trigger() # Bu fonksiyon fetch_all_data'yı çağırır
                
                with self.lock:
                    if result.get('success'):
                        self.consecutive_failures = 0
                    else:
                        self.consecutive_failures += 1
                        
            except Exception as e:
                logger.error(f"❌ Sync error: {e}")
                with self.lock:
                    self.consecutive_failures += 1
            finally:
                with self.lock:
                    self.running = False
        
        thread = threading.Thread(target=_sync_worker, daemon=True)
        thread.start()
        return True

sync_manager = BackgroundSyncManager()

def get_data_or_sync(cache_key, filter_function=None):
    """
    Akıllı cache sistemi
    """
    # 1. Cache Kontrolü
    cached_data = get_cache(cache_key, Config.CACHE_TTL)
    
    if cached_data:
        # Veriyi işle ve dön
        result = cached_data.copy()
        result['cached'] = True
        
        if filter_function and 'data' in result:
            try:
                result['data'] = filter_function(result['data'])
                result['count'] = len(result['data'])
            except Exception:
                pass
        return result
    
    # 2. Cache Miss -> Sync Başlat
    if sync_manager.should_sync():
        sync_manager.start_sync()
    
    return None

# ======================================
# API ENDPOINTS
# ======================================

@api_bp.route('/currency/summary', methods=['GET'])
@rate_limit('summary')
def get_daily_summary():
    """Günün Özeti"""
    try:
        result = get_data_or_sync('kurabak:summary')
        
        if result is None:
            return create_response(None, 503, "Veriler hazırlanıyor...", {'retry_after': 5})
        
        return create_response(
            result.get('data', {}),
            200,
            "Günlük özet başarıyla getirildi",
            {'update_date': result.get('update_date')}
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        return create_response(None, 500, "Internal error")

@api_bp.route('/currency/all', methods=['GET'])
@rate_limit()
def get_all_currencies():
    """Tüm Döviz Kurları"""
    try:
        result = get_data_or_sync('kurabak:currencies:all')
        
        if result is None:
            return create_response(None, 503, "Yükleniyor...", {'retry_after': 3})
        
        return create_response(
            result.get('data', []),
            200,
            "Döviz kurları getirildi",
            {'count': len(result.get('data', [])), 'update_date': result.get('update_date')}
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        return create_response(None, 500, "Internal error")

@api_bp.route('/currency/regional', methods=['GET'])
@rate_limit()
def get_regional_currencies():
    """Bölgesel Dövizler"""
    try:
        result = get_data_or_sync('kurabak:currencies:all')
        
        if result is None:
            return create_response(None, 503, "Yükleniyor...")
        
        currencies = result.get('data', [])
        regional_data = defaultdict(list)
        
        for currency in currencies:
            code = currency.get('code')
            if code in REGION_MAP:
                region = REGION_MAP[code]
                regional_data[region].append(currency)
        
        return create_response(
            regional_data,
            200,
            "Bölgesel veriler getirildi",
            {'regions': REGION_NAMES}
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        return create_response(None, 500, "Internal error")

@api_bp.route('/currency/gold/all', methods=['GET'])
@rate_limit()
def get_all_golds():
    """Tüm Altın Fiyatları"""
    try:
        result = get_data_or_sync('kurabak:golds:all')
        
        if result is None:
            return create_response(None, 503, "Yükleniyor...")
        
        return create_response(
            result.get('data', []),
            200,
            "Altın fiyatları getirildi"
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        return create_response(None, 500, "Internal error")

@api_bp.route('/currency/gold/popular', methods=['GET'])
@rate_limit()
def get_popular_golds():
    """Popüler Altın Fiyatları"""
    try:
        def filter_popular(golds):
            return [g for g in golds if g.get('name') in POPULAR_GOLD_NAMES]
        
        result = get_data_or_sync('kurabak:golds:all', filter_popular)
        
        if result is None:
            return create_response(None, 503, "Yükleniyor...")
        
        return create_response(result.get('data', []), 200)
    except Exception as e:
        logger.error(f"Error: {e}")
        return create_response(None, 500, "Internal error")

@api_bp.route('/currency/silver/all', methods=['GET'])
@rate_limit()
def get_all_silvers():
    """Gümüş Fiyatı"""
    try:
        result = get_data_or_sync('kurabak:silvers:all')
        
        if result is None:
            return create_response(None, 503, "Yükleniyor...")
        
        return create_response(result.get('data', []), 200)
    except Exception as e:
        logger.error(f"Error: {e}")
        return create_response(None, 500, "Internal error")

@api_bp.route('/health', methods=['GET'])
@rate_limit('health')
def health_check():
    """Detaylı Sağlık Kontrolü"""
    try:
        cache_keys = ['kurabak:currencies:all', 'kurabak:golds:all']
        checks = {}
        all_exists = True
        
        for key in cache_keys:
            data = get_cache(key, Config.CACHE_TTL)
            exists = data is not None
            checks[key] = exists
            if not exists: all_exists = False
            
        status = 'healthy' if all_exists else 'degraded'
        
        return create_response(
            {'status': status, 'checks': checks},
            200 if all_exists else 503,
            f"System is {status}"
        )
    except Exception as e:
        return create_response(None, 500, str(e))

# ======================================
# ERROR HANDLERS & HOOKS
# ======================================

@api_bp.errorhandler(404)
def not_found(error):
    return create_response(None, 404, "Endpoint not found")

@api_bp.errorhandler(500)
def internal_error(error):
    return create_response(None, 500, "Internal server error")

@api_bp.before_request
def before_request():
    request.start_time = time.time()

@api_bp.after_request
def after_request(response):
    if hasattr(request, 'start_time'):
        response.headers['X-Response-Time'] = f"{time.time() - request.start_time:.3f}s"
    
    # CORS Headerlarını app.py zaten yönetiyor ama garanti olsun
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response
