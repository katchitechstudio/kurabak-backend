from flask import Blueprint, jsonify
import logging
from models.db import get_db_cursor
from utils.cache import get_cache, set_cache

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

CACHE_TTL = 300

@api_bp.route('/currency/all', methods=['GET'])
def get_all_currencies():
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
