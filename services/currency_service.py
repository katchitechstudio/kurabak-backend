import requests
import logging
from models.db import get_db, put_db
from config import Config

logger = logging.getLogger(__name__)

def fetch_currencies():
    conn = None
    cur = None
    
    try:
        logger.info("💱 Dövizler Truncgil API üzerinden çekiliyor...")
        
        # HTML parse etmek yerine direkt JSON alıyoruz (Çok daha sağlam)
        url = "https://finans.truncgil.com/today.json"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json() # HTML yok, direkt JSON var!
        
        # Hedef Dövizler: (Bizim Kod, API'deki Adı, Bizim Adımız)
        target_currencies = [
            ("USD", "USD", "Amerikan Doları"),
            ("EUR", "EUR", "Euro"),
            ("GBP", "GBP", "İngiliz Sterlini")
        ]
        
        conn = get_db()
        cur = conn.cursor()
        added = 0
        
        for my_code, api_key, my_name in target_currencies:
            item = data.get(api_key)
            
            if not item:
                continue

            try:
                # API'den veriler String gelir, float'a çevirelim
                buying = float(item["Buying"])
                selling = float(item["Selling"])
                
                # Fiyat 0 ise atla
                if buying <= 0: continue
                
                rate = selling
                
                # --- DB İŞLEMLERİ ---
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
                
                # Geçmiş
                cur.execute("INSERT INTO currency_history (code, rate) VALUES (%s, %s)", (my_code, rate))
                
                added += 1

            except Exception as e:
                logger.error(f"{my_code} hatası: {e}")
                continue

        conn.commit()
        
        # Cache Temizle
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
