from flask import Blueprint, jsonify
import logging
from utils.cache import get_cache, set_cache
from services.currency_service import fetch_currencies_to_cache
from services.gold_service import fetch_golds_to_cache
from services.silver_service import fetch_silvers_to_cache

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

CACHE_TTL = 300  # 5 dakika

# ✅ Popüler döviz kodları
POPULAR_CURRENCY_CODES = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CNY', 'CAD', 'AUD', 'DKK', 'SEK', 'NOK', 'SAR', 'QAR', 'KWD', 'AED']

# ✅ Popüler altın isimleri
POPULAR_GOLD_NAMES = ['Gram Altın', 'Çeyrek Altın', 'Yarım Altın', 'Tam Altın', 'Cumhuriyet Altını']


def get_from_cache_or_fetch(cache_key, fetch_function, filter_function=None):
    """
    Redis'ten al, yoksa API'den çek
    
    Args:
        cache_key: Redis key
        fetch_function: API'den çekme fonksiyonu
        filter_function: Filtreleme fonksiyonu (opsiyonel)
    """
    # 1️⃣ Redis'e bak
    cached_data = get_cache(cache_key, CACHE_TTL)
    
    if cached_data:
        logger.debug(f"✅ Cache HIT: {cache_key}")
        
        # Filtre varsa uygula
        if filter_function and isinstance(cached_data, dict):
            filtered = filter_function(cached_data.get('data', []))
            return {
                'success': True,
                'count': len(filtered),
                'data': filtered
            }
        
        return cached_data
    
    # 2️⃣ Cache boşsa API'den çek
    logger.warning(f"⚠️ Cache MISS: {cache_key}, API'den çekiliyor...")
    
    try:
        # API'den çek ve cache'e yaz
        success = fetch_function()
        
        if success:
            # Tekrar cache'den oku
            fresh_data = get_cache(cache_key, CACHE_TTL)
            
            if fresh_data:
                logger.info(f"✅ Fallback başarılı: {cache_key}")
                
                # Filtre varsa uygula
                if filter_function and isinstance(fresh_data, dict):
                    filtered = filter_function(fresh_data.get('data', []))
                    return {
                        'success': True,
                        'count': len(filtered),
                        'data': filtered
                    }
                
                return fresh_data
    
    except Exception as e:
        logger.error(f"❌ Fallback hatası: {e}")
    
    # 3️⃣ Hiçbir şey bulunamadı
    logger.error(f"❌ {cache_key} için veri bulunamadı")
    return None


@api_bp.route('/currency/popular', methods=['GET'])
def get_popular_currencies():
    """✅ Sadece popüler dövizler (15 adet)"""
    try:
        # Filtreleme fonksiyonu
        def filter_popular(currencies):
            return [c for c in currencies if c.get('code') in POPULAR_CURRENCY_CODES]
        
        # Cache'den al veya API'den çek
        result = get_from_cache_or_fetch(
            'kurabak:currencies:all',
            fetch_currencies_to_cache,
            filter_popular
        )
        
        # Veri yoksa 503 dön
        if not result or not result.get('data'):
            return jsonify({
                'success': False,
                'message': 'Veriler yükleniyor, lütfen birkaç saniye bekleyin',
                'count': 0,
                'data': []
            }), 503
        
        logger.info(f"✅ {result['count']} popüler döviz döndürüldü")
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"❌ Popular currencies hatası: {e}")
        return jsonify({
            'success': False,
            'message': 'Bir hata oluştu',
            'count': 0,
            'data': []
        }), 500


@api_bp.route('/currency/gold/popular', methods=['GET'])
def get_popular_golds():
    """✅ Sadece popüler altınlar (5 adet)"""
    try:
        # Filtreleme fonksiyonu
        def filter_popular(golds):
            return [g for g in golds if g.get('name') in POPULAR_GOLD_NAMES]
        
        # Cache'den al veya API'den çek
        result = get_from_cache_or_fetch(
            'kurabak:golds:all',
            fetch_golds_to_cache,
            filter_popular
        )
        
        # Veri yoksa 503 dön
        if not result or not result.get('data'):
            return jsonify({
                'success': False,
                'message': 'Veriler yükleniyor, lütfen birkaç saniye bekleyin',
                'count': 0,
                'data': []
            }), 503
        
        logger.info(f"✅ {result['count']} popüler altın döndürüldü")
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"❌ Popular golds hatası: {e}")
        return jsonify({
            'success': False,
            'message': 'Bir hata oluştu',
            'count': 0,
            'data': []
        }), 500


@api_bp.route('/currency/silver/all', methods=['GET'])
def get_all_silvers():
    """✅ Gümüş (1 adet)"""
    try:
        # Cache'den al veya API'den çek
        result = get_from_cache_or_fetch(
            'kurabak:silvers:all',
            fetch_silvers_to_cache
        )
        
        # Veri yoksa 503 dön
        if not result or not result.get('data'):
            return jsonify({
                'success': False,
                'message': 'Veriler yükleniyor, lütfen birkaç saniye bekleyin',
                'count': 0,
                'data': []
            }), 503
        
        logger.info(f"✅ {result['count']} gümüş döndürüldü")
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"❌ Silvers hatası: {e}")
        return jsonify({
            'success': False,
            'message': 'Bir hata oluştu',
            'count': 0,
            'data': []
        }), 500


# ❌ ESKİ ENDPOINT'LER (Geriye uyumluluk - opsiyonel)
@api_bp.route('/currency/all', methods=['GET'])
def get_all_currencies():
    """ESKİ - Tüm dövizler"""
    try:
        result = get_from_cache_or_fetch(
            'kurabak:currencies:all',
            fetch_currencies_to_cache
        )
        
        if not result:
            return jsonify({
                'success': False,
                'message': 'Veriler yükleniyor',
                'count': 0,
                'data': []
            }), 503
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"❌ All currencies hatası: {e}")
        return jsonify({
            'success': False,
            'message': 'Bir hata oluştu',
            'count': 0,
            'data': []
        }), 500


@api_bp.route('/currency/gold/all', methods=['GET'])
def get_all_golds():
    """ESKİ - Tüm altınlar"""
    try:
        result = get_from_cache_or_fetch(
            'kurabak:golds:all',
            fetch_golds_to_cache
        )
        
        if not result:
            return jsonify({
                'success': False,
                'message': 'Veriler yükleniyor',
                'count': 0,
                'data': []
            }), 503
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"❌ All golds hatası: {e}")
        return jsonify({
            'success': False,
            'message': 'Bir hata oluştu',
            'count': 0,
            'data': []
        }), 500
