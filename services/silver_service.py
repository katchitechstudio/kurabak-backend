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

def fetch_silvers():
    conn = None
    cur = None
    
    # Yanıt içeriğini tutmak için eklendi
    response_text = ""
    
    try:
        logger.info("🥈 Gümüş Bigpara üzerinden çekiliyor...")
        
        url = "https://api.bigpara.hurriyet.com.tr/doviz/headerlist/anasayfa"
        headers = {
            # User-Agent başlığı güncellendi
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://bigpara.hurriyet.com.tr/",
            "Origin": "https://bigpara.hurriyet.com.tr",
            "Accept": "application/json, text/plain, */*"
        }
        
        r = requests.get(url, headers=headers, timeout=15)
        response_text = r.text # Yanıtı dize olarak kaydet
        
        # 1. HTTP Status Code Kontrolü
        r.raise_for_status() # 4xx veya 5xx ise HTTPError fırlatır

        # 2. JSON Çözümleme Kontrolü
        try:
            data = r.json()
        except json.JSONDecodeError as json_e:
            # Yanıt JSON değilse bu hatayı yakalarız
            logger.error(f"Bigpara Gümüş Hatası: JSON Çözümleme Başarısız. Kaynak: {url}. Hata: {json_e}")
            logger.error(f"Yanıt İçeriği (İlk 200 karakter): {response_text[:200]}")
            return False
        
        # Verinin bir liste olup olmadığını kontrol et
        if not isinstance(data, list):
             logger.error(f"Bigpara Gümüş Hatası: Beklenen Liste formatı gelmedi. Gelen tip: {type(data)}")
             return False

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

    except requests.exceptions.RequestException as req_e:
        # requests kütüphanesinden kaynaklanan hatalar (Timeout, HTTPError, ConnectionError vb.)
        logger.error(f"Bigpara Gümüş Hatası (Request): {req_e}")
        if conn: conn.rollback()
        return False

    except Exception as e:
        # Diğer tüm hatalar
        logger.error(f"Bigpara Gümüş Hatası (Genel): {e}")
        if response_text and "json" not in str(e).lower():
            logger.error(f"Yanıt İçeriği (İlk 200 karakter): {response_text[:200]}")
            
        if conn: conn.rollback()
        return False
        
    finally:
        if cur: cur.close()
        if conn: put_db(conn)
