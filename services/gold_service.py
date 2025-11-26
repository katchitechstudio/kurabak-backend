import requests
import logging
from models.db import get_db, put_db

logger = logging.getLogger(__name__)

def get_safe_float(value):
    try:
        if isinstance(value, (int, float)): return float(value)
        return float(str(value).replace(",", "."))
    except: return 0.0

def fetch_golds():
    conn = None
    cur = None
    try:
        logger.info("🥇 Altınlar Bigpara üzerinden çekiliyor...")
        
        # Bigpara Altın API'si (Genelde headerlist içinde de vardır ama burası daha detaylı olabilir)
        # Şimdilik headerlist/anasayfa kullanıyoruz, en güvenli ve hızlısı.
        url = "https://api.bigpara.hurriyet.com.tr/doviz/headerlist/anasayfa"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()

        conn = get_db()
        cur = conn.cursor()
        added = 0

        for item in data:
            aciklama = item.get("ACIKLAMA", "").upper()
            sembol = item.get("SEMBOL", "")
            
            # Bigpara'daki isimleri bizimkilere eşle
            db_name = None
            if "GRAM ALTIN" in aciklama: db_name = "Gram Altın"
            elif "ÇEYREK ALTIN" in aciklama: db_name = "Çeyrek Altın"
            elif "YARIM ALTIN" in aciklama: db_name = "Yarım Altın"
            elif "TAM ALTIN" in aciklama: db_name = "Tam Altın"
            elif "CUMHURİYET" in aciklama: db_name = "Cumhuriyet Altını"
            elif "ONS" in aciklama or sembol == "GLD": db_name = "Ons Altın"
            
            if db_name:
                selling = get_safe_float(item.get("SATIS"))
                percent = get_safe_float(item.get("YUZDEDEGISIM"))
                
                if selling <= 0: continue
                
                rate = selling

                cur.execute("""
                    INSERT INTO golds (name, buying, selling, rate, change_percent, updated_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (name) DO UPDATE SET
                        rate=EXCLUDED.rate,
                        change_percent=EXCLUDED.change_percent,
                        updated_at=CURRENT_TIMESTAMP
                """, (db_name, 0, 0, rate, percent)) 
                # Not: buying/selling 0 geçiyoruz çünkü DB yapısı buying/selling istiyor ama
                # Bigpara anasayfa listesinde bazen sadece tek fiyat olabiliyor veya
                # senin DB yapınla uyumlu olsun diye rate'i önceliklendirdik.
                
                cur.execute("INSERT INTO gold_history (name, rate) VALUES (%s, %s)", (db_name, rate))
                added += 1

        conn.commit()
        try: from utils.cache import clear_cache; clear_cache()
        except: pass
        
        logger.info(f"✅ Bigpara: {added} altın güncellendi.")
        return True

    except Exception as e:
        logger.error(f"Bigpara Altın Hatası: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if cur: cur.close()
        if conn: put_db(conn)
