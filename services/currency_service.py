import requests
import logging
from models.db import get_db, put_db
import json

logger = logging.getLogger(__name__)

def get_safe_float(value):
    try:
        if isinstance(value, (int, float)): return float(value)
        return float(str(value).replace(",", "."))
    except: return 0.0

def fetch_currencies():
    conn = None
    cur = None
    response_text = ""
    
    try:
        logger.info("🌍 Dövizler Bigpara üzerinden çekiliyor...")
        
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
            logger.error(f"Bigpara Döviz Hatası: JSON Çözümleme Başarısız. Hata: {json_e}")
            logger.error(f"Yanıt İçeriği (İlk 200 karakter): {response_text[:200]}")
            return False
        
        # ✅ DÜZELTİLDİ: Küçük harf "data" kullanıldı
        if isinstance(raw_data, dict) and "data" in raw_data:
            data = raw_data.get("data", [])
        else:
            data = raw_data

        # Verinin bir liste olup olmadığını kontrol et
        if not isinstance(data, list):
             logger.error(f"Bigpara Döviz Hatası: Beklenen Liste formatı gelmedi. Gelen tip: {type(data)}")
             return False
            
        # Bigpara Kodları -> Bizim Kodlar
        mapping = {
            "USDTRY": "USD", 
            "EURTRY": "EUR", 
            "GBPTRY": "GBP"
        }
        
        # İsimler
        names = {
            "USD": "Amerikan Doları", 
            "EUR": "Euro", 
            "GBP": "İngiliz Sterlini"
        }

        conn = get_db()
        cur = conn.cursor()
        added = 0

        for item in data:
            symbol = item.get("SEMBOL")
            
            if symbol in mapping:
                my_code = mapping[symbol]
                my_name = names[my_code]
                
                selling = get_safe_float(item.get("SATIS"))
                percent_change = get_safe_float(item.get("YUZDEDEGISIM"))
                
                if selling <= 0: continue
                
                rate = selling

                # --- VERİTABANI KAYDI ---
                cur.execute("""
                    INSERT INTO currencies (code, name, rate, change_percent, updated_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (code) DO UPDATE SET
                        name=EXCLUDED.name,
                        rate=EXCLUDED.rate,
                        change_percent=EXCLUDED.change_percent,
                        updated_at=CURRENT_TIMESTAMP
                """, (my_code, my_name, rate, percent_change))
                
                cur.execute("INSERT INTO currency_history (code, rate) VALUES (%s, %s)", (my_code, rate))
                added += 1

        conn.commit()
        
        try: 
            from utils.cache import clear_cache
            clear_cache()
        except: 
            pass
            
        logger.info(f"✅ Bigpara: {added} döviz güncellendi.")
        return True

    except requests.exceptions.RequestException as req_e:
        logger.error(f"Bigpara Döviz Hatası (Request): {req_e}")
        if conn: conn.rollback()
        return False

    except Exception as e:
        logger.error(f"Bigpara Döviz Hatası (Genel): {e}")
        if response_text and "json" not in str(e).lower():
            logger.error(f"Yanıt İçeriği (İlk 200 karakter): {response_text[:200]}")
            
        if conn: conn.rollback()
        return False
        
    finally:
        if cur: cur.close()
        if conn: put_db(conn)
