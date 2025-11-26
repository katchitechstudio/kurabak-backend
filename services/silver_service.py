import requests
import logging
from models.db import get_db, put_db

logger = logging.getLogger(__name__)

def get_safe_float(value):
    try:
        if isinstance(value, (int, float)): return float(value)
        return float(str(value).replace(",", "."))
    except: return 0.0

def fetch_silvers():
    conn = None
    cur = None
    try:
        logger.info("🥈 Gümüş Bigpara üzerinden çekiliyor...")
        
        url = "https://api.bigpara.hurriyet.com.tr/doviz/headerlist/anasayfa"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()

        conn = get_db()
        cur = conn.cursor()
        
        # Gümüşü bul (Genelde "GÜMÜŞ" veya "SILVER" yazar)
        found = False
        for item in data:
            if "GÜMÜŞ" in item.get("ACIKLAMA", "").upper():
                selling = get_safe_float(item.get("SATIS"))
                percent = get_safe_float(item.get("YUZDEDEGISIM"))
                
                if selling > 0:
                    name = "Gümüş"
                    rate = selling
                    
                    cur.execute("""
                        INSERT INTO silvers (name, buying, selling, rate, change_percent, updated_at)
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (name) DO UPDATE SET
                            rate=EXCLUDED.rate,
                            change_percent=EXCLUDED.change_percent,
                            updated_at=CURRENT_TIMESTAMP
                    """, (name, 0, 0, rate, percent))
                    
                    cur.execute("INSERT INTO silver_history (name, rate) VALUES (%s, %s)", (name, rate))
                    found = True
                    break
        
        conn.commit()
        try: from utils.cache import clear_cache; clear_cache()
        except: pass
        
        if found:
            logger.info("✅ Bigpara: Gümüş güncellendi.")
            return True
        else:
            logger.warning("⚠️ Bigpara listesinde Gümüş bulunamadı.")
            return False

    except Exception as e:
        logger.error(f"Bigpara Gümüş Hatası: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if cur: cur.close()
        if conn: put_db(conn)
