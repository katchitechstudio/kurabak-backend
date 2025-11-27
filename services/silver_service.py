import requests
import logging
from models.db import get_db, put_db

logger = logging.getLogger(__name__)

def get_safe_float(value):
    try:
        if isinstance(value, (int, float)): 
            return float(value)
        return float(str(value).replace(",", "."))
    except: 
        return 0.0

def fetch_silvers():
    conn = None
    cur = None
    
    try:
        logger.info("🥈 Gümüş Truncgil API üzerinden çekiliyor...")
        
        url = "https://finans.truncgil.com/v4/today.json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        # Gümüş kontrolü
        if "GUMUS" in data and data["GUMUS"].get("Type") == "Gold":
            item = data["GUMUS"]
            
            selling = get_safe_float(item.get("Selling", 0))
            change = get_safe_float(item.get("Change", 0))
            
            if selling > 0:
                name = "Gümüş"
                rate = selling
                
                conn = get_db()
                cur = conn.cursor()
                
                cur.execute("""
                    INSERT INTO silvers (name, buying, selling, rate, change_percent, updated_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (name) DO UPDATE SET
                        rate=EXCLUDED.rate,
                        change_percent=EXCLUDED.change_percent,
                        updated_at=CURRENT_TIMESTAMP
                """, (name, 0, 0, rate, change))
                
                cur.execute("INSERT INTO silver_history (name, rate) VALUES (%s, %s)", (name, rate))
                
                conn.commit()
                
                try: 
                    from utils.cache import clear_cache
                    clear_cache()
                except: 
                    pass
                
                logger.info("✅ Truncgil: Gümüş güncellendi.")
                return True
            else:
                logger.warning("⚠️ Truncgil: Gümüş fiyatı 0 veya negatif.")
                return False
        else:
            logger.warning("⚠️ Truncgil: Gümüş bulunamadı.")
            return False

    except requests.exceptions.RequestException as req_e:
        logger.error(f"Truncgil Gümüş Hatası (Request): {req_e}")
        if conn: conn.rollback()
        return False

    except Exception as e:
        logger.error(f"Truncgil Gümüş Hatası (Genel): {e}")
        if conn: conn.rollback()
        return False
        
    finally:
        if cur: cur.close()
        if conn:
            from models.db import put_db
            put_db(conn)
