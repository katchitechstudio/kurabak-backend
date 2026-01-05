from flask import Blueprint, jsonify
import logging
from models.db import get_db_cursor
from utils.cache import get_cache, set_cache

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

CACHE_TTL = 300

# ✅ YENİ - Sadece popüler dövizler (15 adet)
@api_bp.route('/currency/popular', methods=['GET'])
def get_popular_currencies():
    try:
        cache_key = "kurabak:currencies:popular"
        cached_data = get_cache(cache_key, CACHE_TTL)
        
        if cached_data:
            logger.debug("✅ Popular currency cache HIT")
            return jsonify(cached_data), 200
        
        logger.debug("❌ Popular currency cache MISS, DB'den çekiliyor")
        
        # 🎯 Sadece popüler dövizler
        popular_codes = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CNY', 'CAD', 'AUD', 'DKK', 'SEK', 'NOK', 'SAR', 'QAR', 'KWD', 'AED']
        
        with get_db_cursor() as (conn, cur):
            # WHERE IN ile sadece popülerleri çek
            placeholders = ','.join(['%s'] * len(popular_codes))
            cur.execute(f"""
                SELECT code, name, rate, change_percent, updated_at
                FROM currencies
                WHERE code IN ({placeholders})
                ORDER BY 
                    CASE code
                        WHEN 'USD' THEN 1
                        WHEN 'EUR' THEN 2
                        WHEN 'GBP' THEN 3
                        WHEN 'JPY' THEN 4
                        WHEN 'CHF' THEN 5
                        WHEN 'CNY' THEN 6
                        WHEN 'CAD' THEN 7
                        WHEN 'AUD' THEN 8
                        WHEN 'DKK' THEN 9
                        WHEN 'SEK' THEN 10
                        WHEN 'NOK' THEN 11
                        WHEN 'SAR' THEN 12
                        WHEN 'QAR' THEN 13
                        WHEN 'KWD' THEN 14
                        WHEN 'AED' THEN 15
                    END
            """, popular_codes)
            
            rows = cur.fetchall()
            
            data = {
                "success": True,
                "count": len(rows),
                "data": [
                    {
                        "code": row[0],
                        "name": row[1],
                        "rate": float(row[2]),
                        "change_percent": float(row[3]),
                        "updated_at": row[4].isoformat() if row[4] else None
                    }
                    for row in rows
                ]
            }
        
        set_cache(cache_key, data, CACHE_TTL)
        logger.info(f"✅ {len(rows)} popüler döviz döndürüldü")
        
        return jsonify(data), 200
        
    except Exception as e:
        logger.error(f"❌ Popular currency API hatası: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ✅ YENİ - Sadece popüler altınlar (5 adet)
@api_bp.route('/currency/gold/popular', methods=['GET'])
def get_popular_golds():
    try:
        cache_key = "kurabak:golds:popular"
        cached_data = get_cache(cache_key, CACHE_TTL)
        
        if cached_data:
            logger.debug("✅ Popular gold cache HIT")
            return jsonify(cached_data), 200
        
        logger.debug("❌ Popular gold cache MISS, DB'den çekiliyor")
        
        # 🎯 Sadece popüler altınlar
        popular_golds = ['Gram Altın', 'Çeyrek Altın', 'Yarım Altın', 'Tam Altın', 'Cumhuriyet Altını']
        
        with get_db_cursor() as (conn, cur):
            placeholders = ','.join(['%s'] * len(popular_golds))
            cur.execute(f"""
                SELECT name, rate, change_percent, updated_at
                FROM golds
                WHERE name IN ({placeholders})
                ORDER BY 
                    CASE name
                        WHEN 'Gram Altın' THEN 1
                        WHEN 'Çeyrek Altın' THEN 2
                        WHEN 'Yarım Altın' THEN 3
                        WHEN 'Tam Altın' THEN 4
                        WHEN 'Cumhuriyet Altını' THEN 5
                    END
            """, popular_golds)
            
            rows = cur.fetchall()
            
            data = {
                "success": True,
                "count": len(rows),
                "data": [
                    {
                        "name": row[0],
                        "rate": float(row[1]),
                        "change_percent": float(row[2]),
                        "updated_at": row[3].isoformat() if row[3] else None
                    }
                    for row in rows
                ]
            }
        
        set_cache(cache_key, data, CACHE_TTL)
        logger.info(f"✅ {len(rows)} popüler altın döndürüldü")
        
        return jsonify(data), 200
        
    except Exception as e:
        logger.error(f"❌ Popular gold API hatası: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ✅ Gümüş (değişmedi - zaten 1 adet)
@api_bp.route('/currency/silver/all', methods=['GET'])
def get_all_silvers():
    try:
        cache_key = "kurabak:silvers:all"
        cached_data = get_cache(cache_key, CACHE_TTL)
        
        if cached_data:
            logger.debug("✅ Silver cache HIT")
            return jsonify(cached_data), 200
        
        logger.debug("❌ Silver cache MISS, DB'den çekiliyor")
        
        with get_db_cursor() as (conn, cur):
            cur.execute("""
                SELECT name, rate, change_percent, updated_at
                FROM silvers
                ORDER BY name
            """)
            
            rows = cur.fetchall()
            
            data = {
                "success": True,
                "count": len(rows),
                "data": [
                    {
                        "name": row[0],
                        "rate": float(row[1]),
                        "change_percent": float(row[2]),
                        "updated_at": row[3].isoformat() if row[3] else None
                    }
                    for row in rows
                ]
            }
        
        set_cache(cache_key, data, CACHE_TTL)
        
        return jsonify(data), 200
        
    except Exception as e:
        logger.error(f"❌ Silver API hatası: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ❌ ESKİ ENDPOINT'LER - GERİYE UYUMLULUK İÇİN KALSIN (opsiyonel)
@api_bp.route('/currency/all', methods=['GET'])
def get_all_currencies():
    """ESKİ ENDPOINT - Artık kullanılmıyor ama geriye uyumluluk için"""
    try:
        cache_key = "kurabak:currencies:all"
        cached_data = get_cache(cache_key, CACHE_TTL)
        
        if cached_data:
            logger.debug("✅ Currency cache HIT")
            return jsonify(cached_data), 200
        
        logger.debug("❌ Currency cache MISS, DB'den çekiliyor")
        
        with get_db_cursor() as (conn, cur):
            cur.execute("""
                SELECT code, name, rate, change_percent, updated_at
                FROM currencies
                ORDER BY code
            """)
            
            rows = cur.fetchall()
            
            data = {
                "success": True,
                "count": len(rows),
                "data": [
                    {
                        "code": row[0],
                        "name": row[1],
                        "rate": float(row[2]),
                        "change_percent": float(row[3]),
                        "updated_at": row[4].isoformat() if row[4] else None
                    }
                    for row in rows
                ]
            }
        
        set_cache(cache_key, data, CACHE_TTL)
        
        return jsonify(data), 200
        
    except Exception as e:
        logger.error(f"❌ Currency API hatası: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/currency/gold/all', methods=['GET'])
def get_all_golds():
    """ESKİ ENDPOINT - Artık kullanılmıyor ama geriye uyumluluk için"""
    try:
        cache_key = "kurabak:golds:all"
        cached_data = get_cache(cache_key, CACHE_TTL)
        
        if cached_data:
            logger.debug("✅ Gold cache HIT")
            return jsonify(cached_data), 200
        
        logger.debug("❌ Gold cache MISS, DB'den çekiliyor")
        
        with get_db_cursor() as (conn, cur):
            cur.execute("""
                SELECT name, rate, change_percent, updated_at
                FROM golds
                ORDER BY 
                    CASE name
                        WHEN 'Gram Altın' THEN 1
                        WHEN 'Çeyrek Altın' THEN 2
                        WHEN 'Yarım Altın' THEN 3
                        WHEN 'Tam Altın' THEN 4
                        WHEN 'Cumhuriyet Altını' THEN 5
                        ELSE 6
                    END
            """)
            
            rows = cur.fetchall()
            
            data = {
                "success": True,
                "count": len(rows),
                "data": [
                    {
                        "name": row[0],
                        "rate": float(row[1]),
                        "change_percent": float(row[2]),
                        "updated_at": row[3].isoformat() if row[3] else None
                    }
                    for row in rows
                ]
            }
        
        set_cache(cache_key, data, CACHE_TTL)
        
        return jsonify(data), 200
        
    except Exception as e:
        logger.error(f"❌ Gold API hatası: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
