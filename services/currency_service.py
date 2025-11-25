import requests
import logging
from models.db import get_db, put_db

logger = logging.getLogger(__name__)

def get_safe_float(item, keys):
    """Verilen anahtarlardan hangisi varsa onu float'a çevirip döndürür."""
    for key in keys:
        if key in item:
            try:
                val = str(item[key]).replace(",", ".") # Virgül varsa nokta yap
                return float(val)
            except:
                continue
    return 0.0

def fetch_currencies():
    conn = None
    cur = None
    
    try:
        logger.info("💱 Dövizler Truncgil API üzerinden çekiliyor...")
        
        url = "https://finans.truncgil.com/today.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        target_currencies = [
            ("USD", "USD", "Amerikan Doları"),
            ("EUR", "EUR", "Euro"),
            ("GBP", "GBP", "İngiliz Sterlini")
        ]
        
        conn = get_db()
        cur = conn.cursor()
        added = 0
        
        for my_code, api_key, my_name in target_currencies:
            # Hem büyük hem küçük harf ile API key ara (Örn: USD veya usd)
            item = data.get(api_key) or data.get(api_key.lower())
            
            # Eğer veri yoksa veya dictionary değilse atla
            if not item or not isinstance(item, dict):
                continue

            try:
                # 🔥 ESNEK OKUMA: Buying, buying, Alış... Hepsini dene
                buying = get_safe_float(item, ["Buying", "buying", "Alış", "alis"])
                selling = get_safe_float(item, ["Selling", "selling", "Satış", "satis"])
                
                if buying <= 0: continue
                rate = selling
                
                # --- DB ---
                cur.execute("SELECT rate FROM currencies WHERE code = %s", (my_code,))
                old_data = cur.fetchone()
                
                change_percent = 0.0
                if old_data and old_data[0]:
                    old_rate = float(old_data[0])
                    if old_rate > 0:
                        change_percent = ((rate - old_rate) / old_rate) * 100

                cur.execute("""
                    INSERT INTO currencies (code, name, buying, selling, rate, change_percent, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (code) DO UPDATE SET
                        name=EXCLUDED.name,
                        buying=EXCLUDED.buying,
                        selling=EXCLUDED.selling,
                        rate=EXCLUDED.rate,
                        change_percent=EXCLUDED.change_percent,
                        updated_at=CURRENT_TIMESTAMP
                """, (my_code, my_name, buying, selling, rate, change_percent))
                
                cur.execute("INSERT INTO currency_history (code, rate) VALUES (%s, %s)", (my_code, rate))
                added += 1

            except Exception as e:
                logger.error(f"{my_code} hatası: {e}")
                continue

        conn.commit()
        
        try:
            from utils.cache import clear_cache
            clear_cache()
        except: pass
            
        logger.info(f"✅ {added} döviz güncellendi.")
        return True
        
    except Exception as e:
        logger.error(f"Döviz çekme hatası: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if cur: cur.close()
        if conn: put_db(conn)
