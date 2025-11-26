import requests
import logging
from models.db import get_db, put_db
import json # JSONDecodeError yakalamak için eklendi

logger = logging.getLogger(__name__)

def get_safe_float(value):
    try:
        if isinstance(value, (int, float)): return float(value)
        return float(str(value).replace(",", "."))
    except: return 0.0

def fetch_golds():
    conn = None
    cur = None
    response_text = "" 
    
    try:
        logger.info("🥇 Altınlar Bigpara üzerinden çekiliyor...")
        
        url = "https://api.bigpara.hurriyet.com.tr/doviz/headerlist/anasayfa"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://bigpara.hurriyet.com.tr/",
            "Origin": "https://bigpara.hurriyet.com.tr",
            "Accept": "application/json, text/plain, */*"
        }
        
        r = requests.get(url, headers=headers, timeout=15)
        response_text = r.text
        
        # 1. HTTP Status Code Kontrolü
        r.raise_for_status()

        # 2. JSON Çözümleme Kontrolü
        try:
            raw_data = r.json()
        except json.JSONDecodeError as json_e:
            logger.error(f"Bigpara Altın Hatası: JSON Çözümleme Başarısız. Hata: {json_e}")
            logger.error(f"Yanıt İçeriği (İlk 200 karakter): {response_text[:200]}")
            return False
            
        # 🔥 DEĞİŞİKLİK: Veri listesini 'Data' anahtarından çek
        if isinstance(raw_data, dict) and "Data" in raw_data:
            data = raw_data.get("Data", [])
        else:
            data = raw_data
        
        # Verinin bir liste olup olmadığını kontrol et
        if not isinstance(data, list):
             logger.error(f"Bigpara Altın Hatası: 'Data' anahtarından sonra bile beklenen Liste formatı gelmedi. Gelen tip: {type(data)}")
             return False

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
                
                cur.execute("INSERT INTO gold_history (name, rate) VALUES (%s, %s)", (db_name, rate))
                added += 1

        conn.commit()
        try: from utils.cache import clear_cache; clear_cache()
        except: pass
        
        logger.info(f"✅ Bigpara: {added} altın güncellendi.")
        return True

    except requests.exceptions.RequestException as req_e:
        logger.error(f"Bigpara Altın Hatası (Request): {req_e}")
        if conn: conn.rollback()
        return False

    except Exception as e:
        logger.error(f"Bigpara Altın Hatası (Genel): {e}")
        if response_text and "json" not in str(e).lower():
            logger.error(f"Yanıt İçeriği (İlk 200 karakter): {response_text[:200]}")
            
        if conn: conn.rollback()
        return False
        
    finally:
        if cur: cur.close()
        if conn: put_db(conn)
