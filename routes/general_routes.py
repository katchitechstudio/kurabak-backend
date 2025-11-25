from flask import Blueprint, jsonify, request
from models.db import get_db, put_db
from datetime import datetime, timedelta
from utils.cache import get_cache, set_cache

# Blueprint adını genel bir isim yaptım
api_bp = Blueprint('api', __name__, url_prefix='/api')

def _get_data(table_name, name_col, name_value=None):
    """Veritabanından döviz/altın/gümüş verilerini çeker (CACHE DESTEKLİ)"""

    # CACHE KEY (Örn: golds_all veya currencies_USD)
    cache_key = f"{table_name}_{name_value or 'all'}"

    # 60 saniyelik RAM CACHE
    cached = get_cache(cache_key, 60)
    if cached is not None:
        return jsonify({
            'success': True,
            'source': 'cache', # Test için ekledim
            'count': len(cached) if isinstance(cached, list) else 1,
            'data': cached
        }), 200

    # Cache yoksa DB'den oku
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 🔥 DÜZELTME: Hem Altın hem Döviz için Alış/Satış çekiyoruz
        if table_name in ['golds', 'silvers']:
            select_cols = 'name, buying, selling, rate, COALESCE(change_percent, 0.0) as change_percent,'
            name_alias = 'name'
        else:
            # Döviz tablosunda code, name, buying, selling var
            select_cols = 'code, name, buying, selling, rate, COALESCE(change_percent, 0.0) as change_percent,'
            name_alias = 'code'

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
        
        # Sütun isimlerini dinamik olarak almak için (Dict çevrimi)
        columns = [col[0] for col in cursor.description]
        data = [dict(zip(columns, row)) for row in cursor.fetchall()]

        cursor.close()
        put_db(conn)

        if name_value and not data:
            return jsonify({'success': False, 'message': f'{name_value} bulunamadı'}), 404

        # Cache'e yaz
        # Eğer tek veri istendiyse liste değil obje dönelim
        final_data = data[0] if name_value else data
        set_cache(cache_key, final_data)

        return jsonify({
            'success': True,
            'source': 'db',
            'count': len(data),
            'data': final_data
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def _get_history(table_name, name_col, name_value):
    """Geçmiş verilerini çeker"""
    try:
        days = request.args.get('days', 7, type=int)
        since = datetime.utcnow() - timedelta(days=days)

        conn = get_db()
        cursor = conn.cursor()

        # NOT: Tablo isimlerin history için şöyledir diye varsayıyorum:
        # currencies -> currency_history
        # golds -> gold_history
        # silvers -> silver_history
        
        history_table = f"{table_name}_history"

        cursor.execute(f'''
            SELECT {name_col}, rate,
            to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as timestamp
            FROM {history_table} 
            WHERE {name_col} = %s AND created_at >= %s
            ORDER BY created_at ASC
        ''', (name_value.upper() if name_col == 'code' else name_value, since))

        # Dict formatına çevirme
        columns = [col[0] for col in cursor.description]
        history = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        put_db(conn)

        if not history:
            return jsonify({
                'success': False,
                'message': f'No history found for {name_value}',
                'data': []
            }), 404

        return jsonify({
            'success': True,
            'name_code': name_value,
            'count': len(history),
            'data': history
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ================== ENDPOINTS ==================

# --- DÖVİZLER ---
@api_bp.route('/currency/all', methods=['GET'])
def get_all_currencies():
    return _get_data('currencies', 'code')

@api_bp.route('/currency/<code>', methods=['GET'])
def get_currency(code):
    return _get_data('currencies', 'code', code)

@api_bp.route('/currency/history/<code>', methods=['GET'])
def get_currency_history(code):
    return _get_history('currency', 'code', code)

# --- ALTINLAR ---
@api_bp.route('/gold/all', methods=['GET'])
def get_all_golds():
    return _get_data('golds', 'name')

@api_bp.route('/gold/<name>', methods=['GET'])
def get_gold(name):
    return _get_data('golds', 'name', name)

@api_bp.route('/gold/history/<name>', methods=['GET'])
def get_gold_history(name):
    return _get_history('gold', 'name', name)

# --- GÜMÜŞ ---
@api_bp.route('/silver/all', methods=['GET'])
def get_all_silvers():
    return _get_data('silvers', 'name')

@api_bp.route('/silver/<name>', methods=['GET'])
def get_silver(name):
    return _get_data('silvers', 'name', name)

@api_bp.route('/silver/history/<name>', methods=['GET'])
def get_silver_history(name):
    return _get_history('silver', 'name', name)

# --- GÜNCELLEME TETİKLEYİCİLERİ (İsteğe Bağlı) ---
# Eğer manuel güncelleme butonu koyacaksan bunları da ekleyebilirsin
from services.gold_service import fetch_golds
from services.currency_service import fetch_currencies
from services.silver_service import fetch_silvers

@api_bp.route('/system/update-all', methods=['GET'])
def update_system():
    g = fetch_golds()
    c = fetch_currencies()
    s = fetch_silvers()
    return jsonify({"golds": g, "currencies": c, "silvers": s})
