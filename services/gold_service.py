import requests
import logging
from models.db import get_db, put_db
from config import Config

logger = logging.getLogger(__name__)

def fetch_golds():
    conn = None
    cur = None
    
    try:
        logger.info("🥇 Altınlar Truncgil API üzerinden çekiliyor...")
        
        url = "https://finans.truncgil.com/today.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # Eşleştirme: (Veritabanı Adı, API'deki Key)
        target_golds = {
            "Gram Altın": "GRAM-ALTIN",
            "Çeyrek Altın": "CEYREK-ALTIN",
            "Yarım Altın": "YARIM-ALTIN",
            "Tam Altın": "TAM-ALTIN",
            "Cumhuriyet Altını": "CUMHURIYET-ALTINI",
            "Ata Altın": "ATA-ALTIN",
            "Ons Altın": "ONS",
            "Dolar": "USD",  # Altın sayfasında dolar da görünsün istenirse
            "Euro": "EUR"
        }

        conn = get_db()
        cur = conn.cursor()
        added = 0
        
        for db_name, api_key in target_golds.items():
            item = data.get(api_key)
            if not item: continue

            try:
                buying = float(item["Buying"])
                selling = float(item["Selling"])
                
                if buying <= 0: continue
                rate = selling

                # --- DB İŞLEMLERİ ---
                cur.execute("SELECT rate FROM golds WHERE name = %s", (db_name,))
                old_data = cur.fetchone()
                
                change_percent = 0.0
                if old_data and old_data[0]:
                    old_rate = float(old_data[0])
                    if old_rate > 0:
                        change_percent = ((rate - old_rate) / old_rate) * 100

                cur.execute("""
                    INSERT INTO golds (name, buying, selling, rate, change_percent, updated_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (name) DO UPDATE SET
                        buying=EXCLUDED.buying,
                        selling=EXCLUDED.selling,
                        rate=EXCLUDED.rate,
                        change_percent=EXCLUDED.change_percent,
                        updated_at=CURRENT_TIMESTAMP
                """, (db_name, buying, selling, rate, change_percent))
                
                cur.execute("INSERT INTO gold_history (name, rate) VALUES (%s, %s)", (db_name, rate))
                added += 1

            except Exception as e:
                logger.error(f"{db_name} hatası: {e}")
                continue

        conn.commit()
        
        try:
            from utils.cache import clear_cache
            clear_cache()
        except: pass
        
        logger.info(f"✅ {added} altın verisi güncellendi.")
        return True
        
    except Exception as e:
        logger.error(f"Altın çekme hatası: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if cur: cur.close()
        if conn: put_db(conn)
