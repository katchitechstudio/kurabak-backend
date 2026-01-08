from flask import Blueprint, jsonify
import logging
from utils.cache import get_cache
from services.maintenance_service import fetch_all_data # Yeni merkezi fonksiyon

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

CACHE_TTL = 300  # 5 dakika

# ✅ Popüler döviz kodları (Config'den de çekilebilir)
POPULAR_CURRENCY_CODES = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CNY', 'CAD', 'AUD', 'DKK', 'SEK', 'NOK', 'SAR', 'QAR', 'KWD', 'AED']

# ✅ Popüler altın isimleri
POPULAR_GOLD_NAMES = ['Gram Altın', 'Çeyrek Altın', 'Yarım Altın', 'Tam Altın', 'Cumhuriyet Altını']

def get_from_cache_or_fetch(cache_key, filter_function=None):
    """
    Redis'ten al, yoksa merkezi fetch fonksiyonunu tetikle.
    """
    # 1️⃣ Redis'e bak
    cached_data = get_cache(cache_key, CACHE_TTL)
    
    if cached_data:
        # Filtre varsa uygula (Popüler listeler için)
        if filter_function and isinstance(cached_data, dict):
            filtered = filter_function(cached_data.get('data', []))
            return {
                'success': True,
                'count': len(filtered),
                'data': filtered,
                'update_date': cached_data.get('update_date')
            }
        return cached_data
    
    # 2️⃣ Cache boşsa merkezi güncellemeyi tetikle
    logger.warning(f"⚠️ Cache MISS: {cache_key}, Merkezi güncelleme tetikleniyor...")
    
    try:
        # fetch_all_data artık tüm verileri (döviz, altın, gümüş) tek seferde çeker
        success = fetch_all_data()
        
        if success:
            fresh_data = get_cache(cache_key, CACHE_TTL)
            if fresh_data:
                if filter_function and isinstance(fresh_data, dict):
                    filtered = filter_function(fresh_data.get('data', []))
                    return {
                        'success': True,
                        'count': len(filtered),
                        'data': filtered,
                        'update_date': fresh_data.get('update_date')
                    }
                return fresh_data
    
    except Exception as e:
        logger.error(f"❌ Fallback hatası: {e}")
    
    return None

@api_bp.route('/currency/popular', methods=['GET'])
def get_popular_currencies():
    """✅ Sadece popüler dövizler (15 adet)"""
    try:
        def filter_popular(currencies):
            return [c for c in currencies if c.get('code') in POPULAR_CURRENCY_CODES]
        
        result = get_from_cache_or_fetch('kurabak:currencies:all', filter_popular)
        
        if not result or not result.get('data'):
            return jsonify({'success': False, 'message': 'Veriler hazırlanıyor...', 'data': []}), 503
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/currency/gold/popular', methods=['GET'])
def get_popular_golds():
    """✅ Sadece popüler altınlar (5 adet)"""
    try:
        def filter_popular(golds):
            return [g for g in golds if g.get('name') in POPULAR_GOLD_NAMES]
        
        result = get_from_cache_or_fetch('kurabak:golds:all', filter_popular)
        
        if not result or not result.get('data'):
            return jsonify({'success': False, 'message': 'Veriler hazırlanıyor...', 'data': []}), 503
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/currency/silver/all', methods=['GET'])
def get_all_silvers():
    """✅ Gümüş Verisi"""
    try:
        result = get_from_cache_or_fetch('kurabak:silvers:all')
        
        if not result or not result.get('data'):
            return jsonify({'success': False, 'message': 'Veriler hazırlanıyor...', 'data': []}), 503
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
