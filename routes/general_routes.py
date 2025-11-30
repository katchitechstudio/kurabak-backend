from flask import Blueprint, jsonify, request
from models.db import get_db, put_db
from datetime import datetime, timedelta
from utils.cache import get_cache, set_cache
import logging

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

def _get_data(table_name, name_col, name_value=None):
    """
    Genel veri çekme fonksiyonu
    Cache kontrolü yapar, yoksa veritabanından çeker
    """
    cache_key = f"{table_name}_{name_value or 'all'}"
    cached = get_cache(cache_key, 60)
    
    if cached is not None:
        return jsonify({
            'success': True,
            'source': 'cache',
            'count': len(cached) if isinstance(cached, list) else 1,
            'data': cached
        }), 200

    try:
        conn = get_db()
        cursor = conn.cursor()

        # 🔥 Tabloya göre sütun seçimi
        if table_name == 'currencies':
            # Döviz tablosunda buying/selling yok, sadece RATE var
            select_cols = 'code, name, rate, COALESCE(change_percent, 0.0) as change_percent,'
            name_alias = 'code'
        else:
            # Altın ve Gümüş tablosunda buying/selling VAR
            # ⭐ change_percent NULL ise 0.0 döndür (önemli!)
            select_cols = 'name, buying, selling, rate, COALESCE(change_percent, 0.0) as change_percent,'
            name_alias = 'name'

        query = f'''
            SELECT {select_cols}
            to_char(updated_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
            FROM {table_name}
        '''

        params = []
        if name_value:
            query += f" WHERE {name_col} = %s"
            params.append(name_value.upper() if name_col == 'code' else name_value)

        query += f" ORDER BY {name_alias} ASC"

        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        
        # ⭐ Veriyi dict'e çevir ve float'a dönüştür
        data = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            
            # Float dönüşümlerini garanti altına al
            if 'rate' in row_dict:
                row_dict['rate'] = float(row_dict['rate']) if row_dict['rate'] else 0.0
            if 'change_percent' in row_dict:
                row_dict['change_percent'] = float(row_dict['change_percent']) if row_dict['change_percent'] is not None else 0.0
            if 'buying' in row_dict:
                row_dict['buying'] = float(row_dict['buying']) if row_dict['buying'] else 0.0
            if 'selling' in row_dict:
                row_dict['selling'] = float(row_dict['selling']) if row_dict['selling'] else 0.0
                
            data.append(row_dict)

        cursor.close()
        put_db(conn)

        if name_value and not data:
            return jsonify({
                'success': False,
                'message': f'{name_value} bulunamadı'
            }), 404

        final_data = data[0] if name_value else data
        set_cache(cache_key, final_data)

        return jsonify({
            'success': True,
            'source': 'db',
            'count': len(data),
            'data': final_data
        }), 200

    except Exception as e:
        logger.error(f"❌ _get_data hatası ({table_name}): {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


def _get_history(table_name, name_col, name_value):
    """
    Geçmiş veri çekme fonksiyonu
    Son X günün verilerini döndürür
    """
    try:
        days = request.args.get('days', 7, type=int)
        since = datetime.utcnow() - timedelta(days=days)
        conn = get_db()
        cursor = conn.cursor()
        history_table = f"{table_name}_history"

        cursor.execute(f'''
            SELECT {name_col}, rate,
            to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as timestamp
            FROM {history_table} 
            WHERE {name_col} = %s AND created_at >= %s
            ORDER BY created_at ASC
        ''', (name_value.upper() if name_col == 'code' else name_value, since))

        columns = [col[0] for col in cursor.description]
        history = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        put_db(conn)

        if not history:
            return jsonify({
                'success': False,
                'message': 'Geçmiş veri bulunamadı',
                'data': []
            }), 404

        return jsonify({
            'success': True,
            'count': len(history),
            'data': history
        }), 200

    except Exception as e:
        logger.error(f"❌ _get_history hatası ({table_name}): {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


# ==========================================
# CURRENCY ENDPOINTS (Dövizler)
# ==========================================

@api_bp.route('/currency/all', methods=['GET'])
def get_all_currencies():
    """
    Tüm dövizleri döndürür
    GET /api/currency/all
    """
    return _get_data('currencies', 'code')


@api_bp.route('/currency/<code>', methods=['GET'])
def get_currency(code):
    """
    Belirli bir dövizi döndürür
    GET /api/currency/USD
    """
    return _get_data('currencies', 'code', code)


@api_bp.route('/currency/history/<code>', methods=['GET'])
def get_currency_history(code):
    """
    Döviz geçmişi
    GET /api/currency/history/USD?days=7
    """
    return _get_history('currency', 'code', code)


# ==========================================
# GOLD ENDPOINTS (Altın)
# ==========================================

@api_bp.route('/currency/gold/all', methods=['GET'])
def get_all_golds_android():
    """
    ✅ ANDROID UYGULAMASININ KULLANDIĞI ANA ENDPOINT
    Tüm altın fiyatlarını döndürür (yüzde değişimi ile)
    GET /api/currency/gold/all
    
    Response:
    {
      "success": true,
      "source": "db",
      "count": 5,
      "data": [
        {
          "name": "Gram Altın",
          "buying": 0.0,
          "selling": 0.0,
          "rate": 5547.0,
          "change_percent": 0.15,
          "updated_at": "2025-11-30T17:15:40Z"
        }
      ]
    }
    """
    return _get_data('golds', 'name')


@api_bp.route('/gold/all', methods=['GET'])
def get_all_golds():
    """
    Alternatif endpoint: /api/gold/all
    Android app bunu kullanmıyor ama uyumluluk için var
    """
    return _get_data('golds', 'name')


@api_bp.route('/gold/<name>', methods=['GET'])
def get_gold(name):
    """
    Belirli bir altın türünü döndürür
    GET /api/gold/Gram%20Altın
    """
    return _get_data('golds', 'name', name)


@api_bp.route('/gold/history/<name>', methods=['GET'])
def get_gold_history(name):
    """
    Altın geçmişi
    GET /api/gold/history/Gram%20Altın?days=30
    """
    return _get_history('gold', 'name', name)


# ==========================================
# SILVER ENDPOINTS (Gümüş)
# ==========================================

@api_bp.route('/currency/silver/all', methods=['GET'])
def get_all_silvers_android():
    """
    ✅ ANDROID UYGULAMASININ KULLANDIĞI ANA ENDPOINT
    Tüm gümüş fiyatlarını döndürür (yüzde değişimi ile)
    GET /api/currency/silver/all
    
    Response:
    {
      "success": true,
      "source": "db",
      "count": 1,
      "data": [
        {
          "name": "Gümüş",
          "buying": 0.0,
          "selling": 0.0,
          "rate": 77.12,
          "change_percent": 5.76,
          "updated_at": "2025-11-30T17:15:40Z"
        }
      ]
    }
    """
    return _get_data('silvers', 'name')


@api_bp.route('/silver/all', methods=['GET'])
def get_all_silvers():
    """
    Alternatif endpoint: /api/silver/all
    Android app bunu kullanmıyor ama uyumluluk için var
    """
    return _get_data('silvers', 'name')


@api_bp.route('/silver/<name>', methods=['GET'])
def get_silver(name):
    """
    Belirli bir gümüş türünü döndürür
    GET /api/silver/Gümüş
    """
    return _get_data('silvers', 'name', name)


@api_bp.route('/silver/history/<name>', methods=['GET'])
def get_silver_history(name):
    """
    Gümüş geçmişi
    GET /api/silver/history/Gümüş?days=30
    """
    return _get_history('silver', 'name', name)


# ==========================================
# DEBUG ENDPOINTS (Geliştirme için)
# ==========================================

@api_bp.route('/debug/gold-opening', methods=['GET'])
def debug_gold_opening():
    """
    Bugünkü açılış fiyatlarını kontrol etmek için debug endpoint
    GET /api/debug/gold-opening
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name, opening_rate, date, created_at
            FROM gold_daily_opening
            WHERE date = CURRENT_DATE
            ORDER BY name
        """)
        
        columns = [col[0] for col in cursor.description]
        data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        put_db(conn)
        
        return jsonify({
            'success': True,
            'count': len(data),
            'data': data
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Debug endpoint hatası: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
