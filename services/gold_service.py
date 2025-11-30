import requests
import logging
from datetime import datetime, time
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


def save_daily_opening_prices():
    """
    Her gün saat 00:00'da çalışacak
    Günlük açılış fiyatlarını kaydeder
    """
    conn = None
    cur = None
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Bugünkü tüm altın fiyatlarını açılış fiyatı olarak kaydet
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


def calculate_change_from_opening(conn, cur, name, current_rate):
    """
    Bugünkü açılış fiyatından yüzde değişimi hesapla
    """
    try:
        cur.execute("""
            SELECT opening_rate 
            FROM gold_daily_opening 
            WHERE name = %s AND date = CURRENT_DATE
        """, (name,))
        
        result = cur.fetchone()
        
        if result and result[0] > 0:
            opening_rate = float(result[0])
            change_percent = ((current_rate - opening_rate) / opening_rate) * 100
            return round(change_percent, 2)
        else:
            # Bugün için açılış fiyatı yoksa, şu anki fiyatı açılış olarak kaydet
            cur.execute("""
                INSERT INTO gold_daily_opening (name, opening_rate, date)
                VALUES (%s, %s, CURRENT_DATE)
                ON CONFLICT (name, date) DO NOTHING
            """, (name, current_rate))
            logger.info(f"📌 {name} için açılış fiyatı kaydedildi: {current_rate}")
            return 0.0
            
    except Exception as e:
        logger.error(f"❌ Yüzde hesaplama hatası ({name}): {e}")
        return 0.0


def fetch_golds():
    """
    Altın fiyatlarını API'den çeker ve günceller
    """
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
            
            if selling <= 0:
                continue
            
            rate = selling
            
            # ⭐ Günlük açılış fiyatından yüzde değişimi hesapla
            change_percent = calculate_change_from_opening(conn, cur, db_name, rate)
            
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
