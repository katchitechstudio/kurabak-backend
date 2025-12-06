import requests
import logging
from models.db import get_db_cursor

logger = logging.getLogger(__name__)

def get_safe_float(value):
    try:
        if isinstance(value, (int, float)):
            return float(value)
        
        value_str = str(value).strip()
        
        if '.' in value_str and ',' in value_str:
            value_str = value_str.replace(".", "").replace(",", ".")
        else:
            value_str = value_str.replace(",", ".")
        
        value_str = value_str.replace("%", "")
        
        return float(value_str)
    except:
        return 0.0


def save_daily_opening_prices():
    try:
        with get_db_cursor() as (conn, cur):
            cur.execute("""
                INSERT INTO gold_daily_opening (name, opening_rate, date)
                SELECT name, rate, CURRENT_DATE
                FROM golds
                ON CONFLICT (name, date) DO NOTHING
            """)
            conn.commit()
            
        logger.info("✅ Günlük açılış fiyatları kaydedildi")
        return True
        
    except Exception as e:
        logger.error(f"❌ Açılış fiyatları kaydetme hatası: {e}")
        return False


def fetch_golds():
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
        
        with get_db_cursor() as (conn, cur):
            added = 0
            
            for api_code, db_name in gold_mapping.items():
                if api_code not in data or data[api_code].get("Type") != "Gold":
                    continue
                
                item = data[api_code]
                selling = get_safe_float(item.get("Selling", 0))
                
                if selling <= 0:
                    continue
                
                rate = selling
                change_percent = get_safe_float(item.get("Change", 0))
                
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
        
        logger.info(f"✅ {added} altın fiyatı güncellendi")
        
        try:
            from utils.cache import clear_cache
            clear_cache()
        except:
            pass
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Altın çekme hatası: {e}")
        return False
