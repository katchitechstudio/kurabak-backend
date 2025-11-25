import requests
import logging
from models.db import get_db, put_db

logger = logging.getLogger(__name__)

def get_safe_float(item, keys):
    for key in keys:
        if key in item:
            try:
                val = str(item[key]).replace(",", ".")
                return float(val)
            except:
                continue
    return 0.0

def fetch_silvers():
    conn = None
    cur = None
    
    try:
        logger.info("🥈 Gümüş Truncgil API üzerinden çekiliyor...")
        
        url = "https://finans.truncgil.com/today.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        
        # Gümüş bazen "GUMUS", bazen "gumus" olarak gelir
        item = data.get("GUMUS") or data.get("gumus") or data.get("GUMUS-TL")
        
        if not item:
            logger.warning("Gümüş verisi API'de bulunamadı.")
            return False

        buying = get_safe_float(item, ["Buying", "buying", "Alış", "alis"])
        selling = get_safe_float(item, ["Selling", "selling", "Satış", "satis"])
        
        name = "Gümüş"
        rate = selling
        
        if rate <= 0: return False
        
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("SELECT rate FROM silvers WHERE name = %s", (name,))
        old_data = cur.fetchone()
        
        change_percent = 0.0
        if old_data and old_data[0]:
            old_rate = float(old_data[0])
            if old_rate > 0:
                change_percent = ((rate - old_rate) / old_rate) * 100

        cur.execute("""
            INSERT INTO silvers (name, buying, selling, rate, change_percent, updated_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE SET
                buying=EXCLUDED.buying,
                selling=EXCLUDED.selling,
                rate=EXCLUDED.rate,
                change_percent=EXCLUDED.change_percent,
                updated_at=CURRENT_TIMESTAMP
        """, (name, buying, selling, rate, change_percent))
        
        cur.execute("INSERT INTO silver_history (name, rate) VALUES (%s, %s)", (name, rate))
        
        conn.commit()
        
        try:
            from utils.cache import clear_cache
            clear_cache()
        except: pass
        
        logger.info("✅ Gümüş verisi güncellendi.")
        return True
        
    except Exception as e:
        logger.error(f"Gümüş çekme hatası: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if cur: cur.close()
        if conn: put_db(conn)
