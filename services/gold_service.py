import requests
import logging
from models.db import get_db, put_db

logger = logging.getLogger(__name__)

def get_safe_float(value):
    try:
        if isinstance(value, (int, float)):
            return float(value)
        value_str = str(value).replace(",", ".").replace("%", "").strip()
        return float(value_str)
    except:
        return 0.0

def fetch_golds():
    conn = None
    cur = None
    
    try:
        url = "https://finans.truncgil.com/v3/today.json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        gold_mapping = {
            "gram-altin": "Gram Altın",
            "ceyrek-altin": "Çeyrek Altın",
            "yarim-altin": "Yarım Altın",
            "tam-altin": "Tam Altın",
            "cumhuriyet-altini": "Cumhuriyet Altını"
        }
        
        conn = get_db()
        cur = conn.cursor()
        added = 0
        
        for api_code, db_name in gold_mapping.items():
            if api_code not in data or data[api_code].get("Type") != "Gold":
                continue
            
            item = data[api_code]
            selling = get_safe_float(item.get("Selling", 0))
            change_percent = get_safe_float(item.get("Change", 0))
            
            if selling <= 0:
                continue
            
            rate = selling
            
            cur.execute("""
                INSERT INTO golds (name, buying, selling, rate, change_percent, updated_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (name) DO UPDATE SET
                    rate=EXCLUDED.rate,
                    change_percent=EXCLUDED.change_percent,
                    updated_at=CURRENT_TIMESTAMP
            """, (db_name, 0, 0, rate, change_percent))
            
            cur.execute(
                "INSERT INTO gold_history (name, rate) VALUES (%s, %s)",
                (db_name, rate)
            )
            
            added += 1
        
        conn.commit()
        
        try:
            from utils.cache import clear_cache
            clear_cache()
        except:
            pass
        
        return True
        
    except:
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
        
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            try:
                put_db(conn)
            except:
                pass
