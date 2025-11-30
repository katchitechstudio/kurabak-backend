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

def fetch_currencies():
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
        
        currency_codes = [
            "USD", "EUR", "GBP", "JPY", "CHF",
            "CNY", "CAD", "AUD", "DKK", "SEK",
            "NOK", "SAR", "QAR", "KWD", "AED"
        ]
        
        conn = get_db()
        cur = conn.cursor()
        added = 0
        
        for code in currency_codes:
            if code not in data or data[code].get("Type") != "Currency":
                continue
            
            item = data[code]
            name = item.get("Name", code)
            selling = get_safe_float(item.get("Selling", 0))
            change_percent = get_safe_float(item.get("Change", 0))
            
            if code == "JPY":
                selling = selling * 100
            
            if selling <= 0:
                continue
            
            cur.execute("""
                INSERT INTO currencies (code, name, rate, change_percent, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (code) DO UPDATE SET
                    name=EXCLUDED.name,
                    rate=EXCLUDED.rate,
                    change_percent=EXCLUDED.change_percent,
                    updated_at=CURRENT_TIMESTAMP
            """, (code, name, selling, change_percent))
            
            cur.execute(
                "INSERT INTO currency_history (code, rate) VALUES (%s, %s)",
                (code, selling)
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
            conn.rollback()
        return False
        
    finally:
        if cur:
            cur.close()
        if conn:
            put_db(conn)
