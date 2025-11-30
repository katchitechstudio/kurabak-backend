from flask import Blueprint, jsonify, request
from models.db import get_db_cursor
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
        with get_db_cursor() as (conn, cur):
            # Tabloya göre sütun seçimi
            if table_name == 'currencies':
                select_cols = 'code, name, rate, COALESCE(change_percent, 0.0) as change_percent,'
                name_alias = 'code'
            else:
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

            cur.execute(query, params)
            columns = [col[0] for col in cur.description]
            rows = cur.fetchall()
            
            # Veriyi dict'e çevir ve float'a dönüştür
            data = []
            for row in rows:
                row_dict = dict(zip(columns, row))
                
                if 'rate' in row_dict:
                    row_dict['rate'] = float(row_dict['rate']) if row_dict['rate'] else 0.0
                if 'change_percent' in row_dict:
                    row_dict['change_percent'] = float(row_dict['change_percent']) if row_dict['change_percent'] is not None else 0.0
                if 'buying' in row_dict:
                    row_dict['buying'] = float(row_dict['buying']) if row_dict['buying'] else 0.0
                if 'selling' in row_dict:
                    row_dict['selling'] = float(row_dict['selling']) if row_dict['selling'] else 0.0
                    
                data.append(row_dict)

        # Connection otomatik kapandı ✅

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
    """
    try:
        days = request.args.get('days', 7, type=int)
        since = datetime.utcnow() - timedelta(days=days)
        history_table = f"{table_name}_history"

        with get_db_cursor() as (conn, cur):
            cur.execute(f'''
                SELECT {name_col}, rate,
                to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as timestamp
                FROM {history_table} 
                WHERE {name_col} = %s AND created_at >= %s
                ORDER BY created_at ASC
            ''', (name_value.upper() if name_col == 'code' else name_value, since))

            columns = [col[0] for col in cur.description]
            history = [dict(zip(columns, row)) for row in cur.fetchall()]

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
# CURRENCY ENDPOINTS
# ==========================================

@api_bp.route('/currency/all', methods=['GET'])
def get_all_currencies():
    return _get_data('currencies', 'code')

@api_bp.route('/currency/<code>', methods=['GET'])
def get_currency(code):
    return _get_data('currencies', 'code', code)

@api_bp.route('/currency/history/<code>', methods=['GET'])
def get_currency_history(code):
    return _get_history('currency', 'code', code)


# ==========================================
# GOLD ENDPOINTS
# ==========================================

@api_bp.route('/currency/gold/all', methods=['GET'])
def get_all_golds_android():
    return _get_data('golds', 'name')

@api_bp.route('/gold/all', methods=['GET'])
def get_all_golds():
    return _get_data('golds', 'name')

@api_bp.route('/gold/<name>', methods=['GET'])
def get_gold(name):
    return _get_data('golds', 'name', name)

@api_bp.route('/gold/history/<name>', methods=['GET'])
def get_gold_history(name):
    return _get_history('gold', 'name', name)


# ==========================================
# SILVER ENDPOINTS
# ==========================================

@api_bp.route('/currency/silver/all', methods=['GET'])
def get_all_silvers_android():
    return _get_data('silvers', 'name')

@api_bp.route('/silver/all', methods=['GET'])
def get_all_silvers():
    return _get_data('silvers', 'name')

@api_bp.route('/silver/<name>', methods=['GET'])
def get_silver(name):
    return _get_data('silvers', 'name', name)

@api_bp.route('/silver/history/<name>', methods=['GET'])
def get_silver_history(name):
    return _get_history('silver', 'name', name)


# ==========================================
# DEBUG ENDPOINTS
# ==========================================

@api_bp.route('/debug/gold-opening', methods=['GET'])
def debug_gold_opening():
    try:
        with get_db_cursor() as (conn, cur):
            cur.execute("""
                SELECT name, opening_rate, date, 
                       to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at
                FROM gold_daily_opening
                WHERE date = CURRENT_DATE
                ORDER BY name
            """)
            
            columns = [col[0] for col in cur.description]
            data = [dict(zip(columns, row)) for row in cur.fetchall()]
        
        return jsonify({
            'success': True,
            'count': len(data),
            'data': data,
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Debug endpoint hatası: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
